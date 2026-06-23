import hashlib
import uuid
import logging
from datetime import date
from typing import Optional, List, Tuple
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from fastapi import UploadFile

from domain import models
from engine.ingestion.factory import ParserFactory
from engine.ingestion.base import IngestionValidationError
from engine.market_data.market_service import MarketDataService
from engine.market_data.corporate_actions import CorporateActionService

logger = logging.getLogger(__name__)

class TransactionService:
    def __init__(self, db_session: Session):
        self.db = db_session
        self.market_service = MarketDataService(db_session)
        self.corp_service = CorporateActionService(db_session)

    def _generate_row_checksum(self, portfolio_id: str, row_data: dict) -> str:
        """Creates a deterministic SHA-256 hash for a transaction row."""
        raw_string = f"{portfolio_id}_{row_data.get('ticker')}_{row_data.get('transaction_type')}_{row_data.get('quantity')}_{row_data.get('price_per_unit')}_{row_data.get('execution_date')}"
        return hashlib.sha256(raw_string.encode('utf-8')).hexdigest()

    def process_upload(self, portfolio: models.Portfolio, file_bytes: bytes, file_name: str, password: Optional[str] = None) -> int:
        """
        Parses a transaction file, validates it, immutably inserts rows into the ledger,
        and triggers necessary market data syncs.
        Returns the number of rows inserted.
        Raises ValueError or IngestionValidationError on failure.
        """
        logger.info(f"Processing transaction upload for portfolio {portfolio.id} ({file_name})")

        # Mock a file object for the parser factory since it expects UploadFile
        # The parser factory currently expects UploadFile. We will adapt it slightly.
        # Actually, ParserFactory.get_parser takes an UploadFile, but checks file.filename.
        # We can just pass a dummy object with a filename attribute.
        class DummyFile:
            def __init__(self, name):
                self.filename = name
                self.content_type = "text/csv" if name.lower().endswith(".csv") else "application/pdf"
        
        parser = ParserFactory.get_parser(DummyFile(file_name), password=password)

        transaction_objs = parser.parse(file_bytes)

        if not transaction_objs:
            raise ValueError("No valid transaction rows found in the uploaded file.")

        # Sync corporate actions BEFORE validating the ledger
        unique_tickers = {t.ticker.upper() for t in transaction_objs if t.ticker and t.ticker.strip()}
        for ticker in unique_tickers:
            try:
                self.corp_service.sync_splits_for_ticker(ticker)
            except Exception as e:
                logger.error(f"Error syncing splits for {ticker}: {str(e)}")

        # --- BEGIN STATEFUL LEDGER INTEGRITY VALIDATION ---
        from engine.ingestion.ledger_validator import LedgerValidator
        
        existing_txs = self.db.query(
            models.TransactionLedger.ticker, 
            models.TransactionLedger.transaction_type, 
            models.TransactionLedger.quantity, 
            models.TransactionLedger.execution_date
        ).filter(
            models.TransactionLedger.portfolio_id == portfolio.id
        ).all()

        LedgerValidator(self.db).validate(existing_txs, transaction_objs)
        # --- END STATEFUL LEDGER INTEGRITY VALIDATION ---

        db_transactions = []
        for txn in transaction_objs:
            row_dict = txn.model_dump()
            checksum = self._generate_row_checksum(str(portfolio.id), row_dict)
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

        try:
            self.db.add_all(db_transactions)
            self.db.commit()
            logger.info(f"Successfully inserted {len(db_transactions)} transactions for portfolio {portfolio.id}")
        except IntegrityError:
            self.db.rollback()
            logger.warning(f"Duplicate upload detected for portfolio {portfolio.id}")
            raise ValueError("One or more records in this file have already been processed (Duplicate Checksum).")

        # Market data synchronization
        earliest_date = min(t.execution_date for t in transaction_objs)
        today = date.today()

        for ticker in unique_tickers:
            try:
                self.market_service.fetch_and_cache_metadata(ticker)
            except Exception as e:
                logger.error(f"Error fetching metadata for {ticker}: {str(e)}")
            
            try:
                self.market_service.fetch_historical_prices(ticker, earliest_date, today)
            except Exception as e:
                logger.error(f"Error fetching historical prices for {ticker}: {str(e)}")

        return len(db_transactions)
