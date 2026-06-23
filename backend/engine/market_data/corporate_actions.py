import yfinance as yf
import pandas as pd
import datetime
import logging
from decimal import Decimal
from typing import List
from sqlalchemy.orm import Session

from domain.models import CorporateActionEvent

logger = logging.getLogger(__name__)

class CorporateActionService:
    def __init__(self, db_session: Session):
        self.db = db_session

    def sync_splits_for_ticker(self, ticker: str) -> None:
        """
        Fetches historical split data from yfinance and upserts it into the CorporateActionEvent table.
        """
        try:
            ticker_obj = yf.Ticker(ticker)
            splits = ticker_obj.splits
            
            if splits is None or splits.empty:
                logger.info(f"No split data found for {ticker}")
                return

            for timestamp, split_factor in splits.items():
                # timestamp is a pandas Timestamp
                ex_date = timestamp.date() if hasattr(timestamp, 'date') else timestamp
                factor = Decimal(str(split_factor))

                # Check if it already exists
                existing = self.db.query(CorporateActionEvent).filter(
                    CorporateActionEvent.ticker == ticker,
                    CorporateActionEvent.ex_date == ex_date,
                    CorporateActionEvent.action_type == "SPLIT"
                ).first()

                if not existing:
                    new_event = CorporateActionEvent(
                        ticker=ticker,
                        ex_date=ex_date,
                        action_type="SPLIT",
                        adjustment_factor=factor
                    )
                    self.db.add(new_event)

            self.db.commit()
            logger.info(f"Successfully synced corporate actions for {ticker}")
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to sync corporate actions for {ticker}: {str(e)}", exc_info=True)

    def sync_splits_for_tickers(self, tickers: List[str]) -> None:
        """
        Batch sync splits for a list of tickers.
        """
        for ticker in tickers:
            self.sync_splits_for_ticker(ticker)
