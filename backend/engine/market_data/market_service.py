import yfinance as yf
import pandas as pd
import logging
from datetime import date, timedelta
from typing import List
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert

from domain.models import AssetPrices

logger = logging.getLogger(__name__)

class MarketDataService:
    def __init__(self, db_session: Session):
        self.db = db_session


    def fetch_historical_prices(self, ticker: str, start_date: date, end_date: date) -> None:
        """
        Fetches EOD pricing data from Yahoo Finance and caches it in PostgreSQL.
        Uses PostgreSQL 'UPSERT' (ON CONFLICT DO NOTHING) to safely ignore duplicates.
        """
        start_str = start_date.strftime('%Y-%m-%d')
        end_str = (end_date + timedelta(days=1)).strftime('%Y-%m-%d')

        logger.info(f"Fetching market data for {ticker} from {start_str} to {end_str}...")

        try:
            ticker_data = yf.download(ticker, start=start_str, end=end_str, progress=False)

            if ticker_data.empty:
                logger.warning(f"No data returned from yfinance for {ticker}.")
                return

            # Flatten the MultiIndex columns returned by newer versions of yfinance
            if isinstance(ticker_data.columns, pd.MultiIndex):
                ticker_data.columns = ticker_data.columns.get_level_values(0)
            # ------------------------------

            records = []
            for timestamp, row in ticker_data.iterrows():
                price_date = timestamp.date()

                # Safely get the Close price
                close_price = float(row['Close']) if 'Close' in row else 0.0
                if close_price == 0.0 or pd.isna(close_price):
                    continue

                # Fallback: Use Close if 'Adj Close' is missing from the DataFrame
                adj_close = float(row['Adj Close']) if 'Adj Close' in row else close_price

                record = {
                    'ticker': ticker.upper(),
                    'price_date': price_date,
                    'open_price': float(row['Open']) if 'Open' in row else close_price,
                    'high_price': float(row['High']) if 'High' in row else close_price,
                    'low_price': float(row['Low']) if 'Low' in row else close_price,
                    'close_price': close_price,
                    'adjusted_close': adj_close,
                    'volume': int(row['Volume']) if 'Volume' in row else 0
                }
                records.append(record)

            if not records:
                return

            stmt = insert(AssetPrices).values(records)
            stmt = stmt.on_conflict_do_update(
                index_elements=['ticker', 'price_date'],
                set_={
                    'open_price': stmt.excluded.open_price,
                    'high_price': stmt.excluded.high_price,
                    'low_price': stmt.excluded.low_price,
                    'close_price': stmt.excluded.close_price,
                    'adjusted_close': stmt.excluded.adjusted_close,
                    'volume': stmt.excluded.volume
                }
            )

            self.db.execute(stmt)
            self.db.commit()
            logger.info(f"Successfully cached {len(records)} days of pricing for {ticker}.")

        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to fetch market data for {ticker}: {str(e)}", exc_info=True)
            raise e

    def get_price(self, ticker: str, target_date: date) -> float:
        """
        Retrieves the adjusted close price from the local cache.
        If the exact date is missing (e.g., a weekend or holiday),
        it searches backward for the nearest preceding trading day.
        """
        price_record = self.db.query(AssetPrices).filter(
            AssetPrices.ticker == ticker,
            AssetPrices.price_date <= target_date
        ).order_by(AssetPrices.price_date.desc()).first()

        if price_record:
            return float(price_record.adjusted_close)

        raise ValueError(f"No historical price found for {ticker} on or before {target_date}")

    def get_prices_bulk(self, tickers: List[str], target_dates: List[date]) -> dict[date, dict[str, float]]:
        """
        Retrieves adjusted close prices for multiple tickers across multiple dates efficiently.
        Returns a dictionary mapping: { date: { ticker: price } }
        """
        from sqlalchemy import func
        result = {d: {} for d in target_dates}
        
        if not tickers or not target_dates:
            return result
            
        for d in target_dates:
            # Subquery to find the most recent trading date on or before target date for each ticker
            subq = self.db.query(
                AssetPrices.ticker,
                func.max(AssetPrices.price_date).label('max_date')
            ).filter(
                AssetPrices.ticker.in_(tickers),
                AssetPrices.price_date <= d
            ).group_by(AssetPrices.ticker).subquery()
            
            # Join back to get the actual adjusted close price
            records = self.db.query(AssetPrices).join(
                subq,
                (AssetPrices.ticker == subq.c.ticker) & (AssetPrices.price_date == subq.c.max_date)
            ).all()
            
            for r in records:
                result[d][r.ticker] = float(r.adjusted_close)
                
        return result
