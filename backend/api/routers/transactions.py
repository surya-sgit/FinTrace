
import hashlib
import uuid
from datetime import date
from typing import Optional
from engine.ingestion.factory import ParserFactory
from engine.ingestion.base import IngestionValidationError

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from pydantic import ValidationError

from db.session import get_db
from domain import models, schemas
from engine.market_data.market_service import MarketDataService
from api.dependencies import get_current_user

router = APIRouter()

def generate_row_checksum(portfolio_id: str, row_data: dict) -> str:
    """Creates a deterministic SHA-256 hash for a transaction row."""
    raw_string = f"{portfolio_id}_{row_data.get('ticker')}_{row_data.get('transaction_type')}_{row_data.get('quantity')}_{row_data.get('price_per_unit')}_{row_data.get('execution_date')}"
    return hashlib.sha256(raw_string.encode('utf-8')).hexdigest()

@router.post(
    "/{portfolio_id}/upload",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload a Transaction Ledger CSV",
    description="Ingests a raw broker CSV file. Validates rows, stores them immutably, and triggers historical market data synchronization."
)
async def upload_transaction_ledger(
    portfolio_id: uuid.UUID,
    file: UploadFile = File(...),
    password: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # 1. Verify Portfolio Exists
    portfolio = db.query(models.Portfolio).filter(models.Portfolio.id == portfolio_id, models.Portfolio.user_id == current_user.id).first()
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found or access denied.")

    # 2. Determine parser based on MIME type
    try:
        parser = ParserFactory.get_parser(file, password=password)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))

    # 3. Read file bytes (async)
    file_bytes = await file.read()

    # 4. Parse into TransactionCreate objects – any validation issue raises IngestionValidationError
    try:
        transaction_objs = parser.parse(file_bytes)
    except IngestionValidationError as ive:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": "File validation failed.", "errors": ive.errors},
        )

    if not transaction_objs:
        raise HTTPException(status_code=400, detail="No valid transaction rows found in the uploaded file.")

    # 5. Convert to DB models with checksum generation
    db_transactions = []
    for txn in transaction_objs:
        row_dict = txn.model_dump()
        checksum = generate_row_checksum(str(portfolio_id), row_dict)
        db_txn = models.TransactionLedger(
            portfolio_id=portfolio.id,
            ticker=txn.ticker.upper(),
            transaction_type=txn.transaction_type.value,
            quantity=txn.quantity,
            price_per_unit=txn.price_per_unit,
            brokerage_fees=txn.brokerage_fees,
            execution_date=txn.execution_date,
            settlement_date=txn.settlement_date,
            checksum=checksum,
        )
        db_transactions.append(db_txn)

    # 6. Atomic DB insertion
    try:
        db.add_all(db_transactions)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="One or more records in this file have already been processed (Duplicate Checksum).",
        )

    # 7. Market data synchronization (same as before)
    unique_tickers = {t.ticker.upper() for t in transaction_objs}
    earliest_date = min(t.execution_date for t in transaction_objs)
    today = date.today()
    market_service = MarketDataService(db)
    for ticker in unique_tickers:
        market_service.fetch_historical_prices(ticker, earliest_date, today)

    return {
        "status": "success",
        "message": f"Successfully ingested {len(db_transactions)} transactions into the ledger and synced market data.",
        "portfolio_id": str(portfolio_id),
    }
