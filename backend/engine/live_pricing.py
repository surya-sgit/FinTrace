import yfinance as yf
import httpx
import logging
from sqlalchemy.orm import Session
from domain.models import MarketPrice

logger = logging.getLogger(__name__)

# Replace with your actual free API key later
ALPHA_VANTAGE_API_KEY = "YOUR_FREE_API_KEY"

async def fetch_tier2_alphavantage(ticker: str) -> float:
    """Fetches price from Alpha Vantage REST API."""
    url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={ticker}&apikey={ALPHA_VANTAGE_API_KEY}"

    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        data = response.json()

        # Alpha Vantage returns an empty dictionary or an error message if rate-limited
        if "Global Quote" not in data or not data["Global Quote"]:
            raise ValueError(f"Alpha Vantage Rate Limit or Missing Data for {ticker}")

        return float(data["Global Quote"]["05. price"])

async def fetch_tier3_yfinance(ticker: str) -> float:
    """Fetches price using the free Yahoo Finance scraper."""
    # yfinance is synchronous, but we can wrap it if needed. For now, basic call.
    stock = yf.Ticker(ticker)

    # fast_info is much faster and less likely to be blocked than downloading full history
    current_price = stock.fast_info.get('last_price')

    if current_price is None:
        raise ValueError(f"yfinance failed to retrieve price for {ticker}")

    return float(current_price)

async def update_ticker_price(ticker: str, db: Session):
    """The Waterfall Execution Engine."""
    price = None
    source = None

    try:
        # 1. Attempt the REST API
        price = await fetch_tier2_alphavantage(ticker)
        source = "ALPHA_VANTAGE"
        logger.info(f"[{ticker}] Tier 2 Success: ₹{price}")

    except Exception as e:
        logger.warning(f"[{ticker}] Tier 2 Failed: {str(e)}. Falling back to Tier 3.")

        try:
            # 2. Fallback to the Scraper
            price = await fetch_tier3_yfinance(ticker)
            source = "YFINANCE"
            logger.info(f"[{ticker}] Tier 3 Success: ₹{price}")

        except Exception as e:
            logger.error(f"[{ticker}] ALL TIERS FAILED: {str(e)}")
            return # Exit without updating DB so we keep the last known good price

    # 3. Upsert the price into the PostgreSQL database
    if price is not None:
        db_price = db.query(MarketPrice).filter(MarketPrice.ticker == ticker).first()
        if db_price:
            db_price.current_price = price
            db_price.data_source = source
        else:
            db_price = MarketPrice(ticker=ticker, current_price=price, data_source=source)
            db.add(db_price)

        db.commit()

async def scheduled_market_data_update():
    """Scheduled task to update all active tickers across portfolios."""
    from db.session import SessionLocal
    from domain.models import TransactionLedger
    
    from engine.ingestion.fund_classifier import is_mutual_fund

    logger.info("Starting scheduled market data update...")
    db = SessionLocal()
    try:
        # Get all distinct tickers from the ledger
        tickers = db.query(TransactionLedger.ticker).distinct().all()
        ticker_list = [t[0] for t in tickers]

        equities = [t for t in ticker_list if not is_mutual_fund(t)]
        mf_isins = [t for t in ticker_list if is_mutual_fund(t)]

        for ticker in equities:
            await update_ticker_price(ticker, db)

        # Mutual funds: refresh NAVs from AMFI (master loaded once).
        if mf_isins:
            from engine.market_data.amfi_service import AMFIService
            amfi = AMFIService(db)
            for isin in mf_isins:
                try:
                    amfi.fetch_and_cache_nav(isin)
                except Exception as e:
                    logger.error(f"AMFI NAV update failed for {isin}: {str(e)}")

        logger.info(f"Scheduled update completed for {len(ticker_list)} distinct tickers.")
    except Exception as e:
        logger.error(f"Scheduled market data update failed: {str(e)}")
    finally:
        db.close()
