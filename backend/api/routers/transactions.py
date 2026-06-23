import uuid
import hashlib
from typing import Optional
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status, BackgroundTasks
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from pydantic import ValidationError

from db.session import get_db, SessionLocal
from domain import models, schemas
from engine.market_data.market_service import MarketDataService
from engine.market_data.corporate_actions import CorporateActionService
from domain.services.transaction_service import TransactionService
from engine.ingestion.base import IngestionValidationError
from engine.analytics.behavioral import BehavioralAnalyticsEngine
from api.dependencies import get_current_user

router = APIRouter()

def get_transaction_service(db: Session = Depends(get_db)) -> TransactionService:
    return TransactionService(db)

def generate_row_checksum(portfolio_id: str, row_data: dict) -> str:
    """Creates a deterministic SHA-256 hash for a transaction row."""
    raw_string = f"{portfolio_id}_{row_data.get('ticker')}_{row_data.get('transaction_type')}_{row_data.get('quantity')}_{row_data.get('price_per_unit')}_{row_data.get('execution_date')}"
    return hashlib.sha256(raw_string.encode('utf-8')).hexdigest()

def trigger_behavioral_analytics(portfolio_id: uuid.UUID):
    """Isolated background execution context for behavioral analytics."""
    db = SessionLocal()
    try:
        engine = BehavioralAnalyticsEngine(db_session=db, portfolio_id=str(portfolio_id))
        engine.run_analysis()
    except Exception as e:
        print(f"Background task failed for portfolio {portfolio_id}: {str(e)}")
    finally:
        db.close()

@router.post(
    "/{portfolio_id}/upload",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload a Transaction Ledger CSV",
    description="Ingests a raw broker CSV file. Validates rows, stores them immutably, and triggers historical market data synchronization."
)
async def upload_transaction_ledger(
    portfolio_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    password: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    transaction_service: TransactionService = Depends(get_transaction_service)
):
    # 1. Verify Portfolio Exists
    portfolio = db.query(models.Portfolio).filter(
        models.Portfolio.id == portfolio_id, 
        models.Portfolio.user_id == current_user.id
    ).first()
    
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found or access denied.")

    # 2. Read file bytes (async IO)
    file_bytes = await file.read()
    
    # 3. Offload blocking parsing, DB operations, and sync network calls to a threadpool
    try:
        inserted_count = await run_in_threadpool(
            transaction_service.process_upload,
            portfolio,
            file_bytes,
            file.filename,
            password
        )
    except ValueError as ve:
        if "Duplicate Checksum" in str(ve):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(ve))
        raise HTTPException(status_code=400, detail=str(ve))
    except IngestionValidationError as ive:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": "File validation failed.", "errors": ive.errors},
        )

    # 8. Trigger Behavioral Analytics mathematically heavy computation in the background
    background_tasks.add_task(trigger_behavioral_analytics, portfolio_id)

    return {
        "status": "success",
        "message": f"Successfully ingested {inserted_count} transactions into the ledger and synced market data.",
        "portfolio_id": str(portfolio_id),
    }
