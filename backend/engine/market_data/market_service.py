import yfinance as yf
import pandas as pd
import logging
from datetime import date, timedelta
from typing import List
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert

from domain.models import AssetPrices, AssetMetadata

logger = logging.getLogger(__name__)

class MarketDataService:
    def __init__(self, db_session: Session):
        self.db = db_session


    def fetch_historical_prices(self, ticker: str, start_date: date, end_date: date) -> None:
        """
        Fetches EOD pricing data from Yahoo Finance and caches it in PostgreSQL.
        Uses PostgreSQL 'UPSERT' (ON CONFLICT DO NOTHING) to safely ignore duplicates.
        """
        if not ticker or not isinstance(ticker, str):
            return
        ticker = ticker.upper().strip()[:32]

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

    def fetch_and_cache_metadata(self, ticker: str) -> None:
        """
        Fetches sector and industry metadata from Yahoo Finance and caches it in PostgreSQL/SQLite.
        Checks if metadata already exists in the database first to minimize network requests.
        """
        if not ticker or not isinstance(ticker, str):
            return
        ticker = ticker.upper().strip()[:32]

        # Check if already cached
        existing = self.db.query(AssetMetadata).filter(AssetMetadata.ticker == ticker).first()
        if existing:
            logger.info(f"Metadata for ticker {ticker} already cached.")
            return

        logger.info(f"Fetching metadata for {ticker} from Yahoo Finance...")

        sector = "Unknown"
        industry = "Unknown"

        try:
            ticker_obj = yf.Ticker(ticker)
            info = ticker_obj.info
            if isinstance(info, dict):
                raw_sector = info.get("sector")
                raw_industry = info.get("industry")
                
                if isinstance(raw_sector, str):
                    raw_sector = raw_sector.strip()
                    if raw_sector:
                        sector = raw_sector.title()
                
                if isinstance(raw_industry, str):
                    raw_industry = raw_industry.strip()
                    if raw_industry:
                        industry = raw_industry.title()
        except Exception as e:
            logger.warning(f"Failed to fetch metadata from yfinance for {ticker}: {str(e)}")

        # Ensure truncation to 64 chars
        sector = sector[:64]
        industry = industry[:64]

        try:
            new_metadata = AssetMetadata(
                ticker=ticker,
                sector=sector,
                industry=industry
            )
            self.db.add(new_metadata)
            self.db.commit()
            logger.info(f"Successfully cached metadata for {ticker}: Sector='{sector}', Industry='{industry}'")
        except IntegrityError as ie:
            self.db.rollback()
            existing_after_rollback = self.db.query(AssetMetadata).filter(AssetMetadata.ticker == ticker).first()
            if existing_after_rollback:
                logger.info(f"Concurrent ingestion handled: Metadata for {ticker} was committed by another thread.")
                return
            else:
                logger.error(f"IntegrityError raised but ticker {ticker} not found in database: {str(ie)}", exc_info=True)
                raise ie
        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to save metadata for {ticker}: {str(e)}", exc_info=True)
            raise e

    def fetch_and_cache_sector_metadata(self, ticker: str) -> None:
        self.fetch_and_cache_metadata(ticker)

