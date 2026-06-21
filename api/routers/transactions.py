import csv
import io
import hashlib
import uuid
from datetime import date
from typing import List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
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
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # 1. Verify Portfolio Exists
    portfolio = db.query(models.Portfolio).filter(models.Portfolio.id == portfolio_id,models.Portfolio.user_id == current_user.id).first()
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found or access denied.")

    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="Invalid file type. Only CSV files are accepted.")

    # 2. Read and Decode File Stream
    contents = await file.read()
    decoded_file = contents.decode('utf-8')
    csv_reader = csv.DictReader(io.StringIO(decoded_file))

    if not csv_reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV file is empty or missing headers.")

    csv_reader.fieldnames = [name.strip().lower() for name in csv_reader.fieldnames]

    valid_records = []
    error_log = []

    # 3. Row-by-Row Validation Pipeline
    for row_number, row in enumerate(csv_reader, start=2):
        try:
            validated_data = schemas.TransactionCreate(**row)
            # Explicitly cast UUID to string for the checksum generator
            checksum = generate_row_checksum(str(portfolio_id), row)

            db_transaction = models.TransactionLedger(
                portfolio_id=portfolio.id,
                ticker=validated_data.ticker.upper(),
                transaction_type=validated_data.transaction_type.value,
                quantity=validated_data.quantity,
                price_per_unit=validated_data.price_per_unit,
                brokerage_fees=validated_data.brokerage_fees,
                execution_date=validated_data.execution_date,
                settlement_date=validated_data.settlement_date,
                checksum=checksum
            )
            valid_records.append(db_transaction)

        except ValidationError as e:
            error_log.append({"row": row_number, "errors": e.errors()})
        except Exception as e:
            error_log.append({"row": row_number, "errors": str(e)})

    if error_log:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": "File validation failed.", "errors": error_log}
        )

    if not valid_records:
        raise HTTPException(status_code=400, detail="The uploaded CSV contained no valid transaction rows.")

    # 4. Safe Database Insertion
    try:
        db.add_all(valid_records)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="One or more records in this file have already been processed (Duplicate Checksum)."
        )

    # 5. Trigger Market Data Synchronization
    unique_tickers = set([record.ticker for record in valid_records])

    earliest_date = min([record.execution_date for record in valid_records])
    today = date.today()

    market_service = MarketDataService(db)

    for ticker in unique_tickers:
        market_service.fetch_historical_prices(ticker, earliest_date, today)

    return {
        "status": "success",
        "message": f"Successfully ingested {len(valid_records)} transactions into the ledger and synced market data.",
        "portfolio_id": str(portfolio_id)
    }
