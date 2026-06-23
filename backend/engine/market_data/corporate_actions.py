import os
import requests
import datetime
from decimal import Decimal
from typing import List
from sqlalchemy.orm import Session

from domain.models import CorporateActionEvent

class CorporateActionService:
    def __init__(self, db_session: Session):
        self.db = db_session
        self.api_key = os.getenv("ALPHA_VANTAGE_API_KEY", "demo") # Free tier placeholder
        self.base_url = "https://www.alphavantage.co/query"

    def _translate_ticker_for_alpha_vantage(self, ticker: str) -> str:
        """
        Translates Yahoo Finance style tickers to Alpha Vantage style tickers.
        e.g., RELIANCE.NS -> NSE:RELIANCE
        """
        if ticker.endswith(".NS"):
            return f"NSE:{ticker[:-3]}"
        elif ticker.endswith(".BO") or ticker.endswith(".BSE"):
            suffix_len = len(ticker.split('.')[-1]) + 1
            return f"BSE:{ticker[:-suffix_len]}"
        return ticker

    def sync_splits_for_ticker(self, ticker: str) -> None:
        """
        Fetches historical split data from Alpha Vantage and upserts it into the CorporateActionEvent table.
        """
        try:
            av_ticker = self._translate_ticker_for_alpha_vantage(ticker)
            params = {
                "function": "SPLITS",
                "symbol": av_ticker,
                "apikey": self.api_key
            }
            response = requests.get(self.base_url, params=params, timeout=10)
            if response.status_code != 200:
                return

            data = response.json()
            
            # Alpha Vantage returns an Information or Note string when the API key is restricted
            if "Information" in data or "Note" in data:
                return

            if "data" not in data:
                return

            splits = data["data"]
            for split in splits:
                ex_date = datetime.datetime.strptime(split["effective_date"], "%Y-%m-%d").date()
                factor = Decimal(str(split["split_factor"]))

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
            
        except Exception as e:
            self.db.rollback()
            # Fail silently for MVP if network fails or rate limited
            pass

    def sync_splits_for_tickers(self, tickers: List[str]) -> None:
        """
        Batch sync splits for a list of tickers.
        """
        for ticker in tickers:
            self.sync_splits_for_ticker(ticker)
