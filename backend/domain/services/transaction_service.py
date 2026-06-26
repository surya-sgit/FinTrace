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

    def _generate_row_checksum(self, portfolio_id: str, row_data: dict, sequence_number: int) -> str:
        """Creates a deterministic SHA-256 hash for a transaction row."""
        ticker = str(row_data.get('ticker', '')).strip().upper()
        raw_string = f"{portfolio_id}_{ticker}_{row_data.get('transaction_type')}_{row_data.get('quantity')}_{row_data.get('price_per_unit')}_{row_data.get('execution_date')}_{sequence_number}"
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

        from engine.ingestion.fund_classifier import is_mutual_fund, classify_fund_type, MUTUAL_FUND_CLASSES

        unique_tickers = {t.ticker.upper() for t in transaction_objs if t.ticker and t.ticker.strip()}

        # A ticker is a mutual fund if the parser flagged it (Groww MF scheme name) or
        # it is an INF ISIN (CAS PDF). Track the parser's coarse class as a fallback.
        parsed_mf_class = {}
        for t in transaction_objs:
            tk = t.ticker.upper()
            if t.asset_class in MUTUAL_FUND_CLASSES:
                parsed_mf_class[tk] = t.asset_class
            elif is_mutual_fund(tk):
                parsed_mf_class.setdefault(tk, "EQUITY_MF")
        mf_tickers = set(parsed_mf_class.keys())

        # AMFI gives both the scheme CATEGORY (for tax classification) and the NAV (for
        # pricing). Resolve by ISIN (CAS) or by scheme name (Groww). Load master once.
        amfi = None
        asset_class_by_ticker = {t: "EQUITY" for t in unique_tickers}
        if mf_tickers:
            from engine.market_data.amfi_service import AMFIService
            amfi = AMFIService(self.db)
            for t in mf_tickers:
                try:
                    scheme = amfi.get_scheme(t) if is_mutual_fund(t) else amfi.get_scheme_by_name(t)
                except Exception as e:
                    logger.error(f"Error classifying MF {t}: {str(e)}")
                    scheme = None
                if scheme:
                    asset_class_by_ticker[t] = classify_fund_type(scheme.get("category"), scheme.get("scheme_name"))
                else:
                    asset_class_by_ticker[t] = parsed_mf_class.get(t, "EQUITY_MF")

        # Sync corporate actions (equities only — MFs have no yfinance splits/dividends).
        for ticker in unique_tickers - mf_tickers:
            try:
                self.corp_service.sync_splits_for_ticker(ticker)
            except Exception as e:
                logger.error(f"Error syncing splits for {ticker}: {str(e)}")
            try:
                # Auto-derive dividends from public corporate-action data so users
                # don't have to enter them manually (and can't get them wrong).
                self.corp_service.sync_dividends_for_ticker(ticker)
            except Exception as e:
                logger.error(f"Error syncing dividends for {ticker}: {str(e)}")

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
        for idx, txn in enumerate(transaction_objs):
            row_dict = txn.model_dump()
            checksum = self._generate_row_checksum(str(portfolio.id), row_dict, idx)
            # Mutual funds: prefer the AMFI-resolved class (falls back to the parser's
            # name heuristic). Stocks: EQUITY.
            tk = txn.ticker.upper()
            if tk in mf_tickers:
                asset_class = asset_class_by_ticker.get(tk) or txn.asset_class
            else:
                asset_class = txn.asset_class if txn.asset_class != "EQUITY" else "EQUITY"
            db_txn = models.TransactionLedger(
                portfolio_id=portfolio.id,
                ticker=txn.ticker.upper(),
                transaction_type=txn.transaction_type.value,
                quantity=txn.quantity,
                price_per_unit=txn.price_per_unit,
                brokerage_fees=txn.brokerage_fees,
                asset_class=asset_class,
                execution_date=txn.execution_date,
                settlement_date=txn.settlement_date,
                sequence_number=idx,
                checksum=checksum,
            )
            db_transactions.append(db_txn)

        try:
            self.db.add_all(db_transactions)
            
            # Invalidate risk metrics cache
            self.db.query(models.PortfolioRiskSnapshot).filter(
                models.PortfolioRiskSnapshot.portfolio_id == portfolio.id
            ).delete()

            self.db.commit()
            logger.info(f"Successfully inserted {len(db_transactions)} transactions for portfolio {portfolio.id}")
        except IntegrityError:
            self.db.rollback()
            logger.warning(f"Duplicate upload detected for portfolio {portfolio.id}")
            raise ValueError("One or more records in this file have already been processed (Duplicate Checksum).")

        # Market data synchronization
        earliest_date = min(t.execution_date for t in transaction_objs)
        today = date.today()

        for ticker in unique_tickers - mf_tickers:
            try:
                self.market_service.fetch_and_cache_metadata(ticker)
            except Exception as e:
                logger.error(f"Error fetching metadata for {ticker}: {str(e)}")

            try:
                self.market_service.fetch_historical_prices(ticker, earliest_date, today)
            except Exception as e:
                logger.error(f"Error fetching historical prices for {ticker}: {str(e)}")

        # Mutual funds: price from AMFI NAV (yfinance doesn't cover Indian MFs).
        for ticker in mf_tickers:
            try:
                if amfi is not None:
                    amfi.fetch_and_cache_nav(ticker)
            except Exception as e:
                logger.error(f"Error fetching AMFI NAV for {ticker}: {str(e)}")

        return len(db_transactions)
