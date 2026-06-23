import pytest
import uuid
import datetime
from decimal import Decimal
from unittest.mock import MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB

from domain.models import Base, Portfolio, TransactionLedger, AssetMetadata
from domain.services.transaction_service import TransactionService
from engine.market_data.market_service import MarketDataService

@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"

SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="session", autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

@pytest.fixture
def db_session():
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)
    session.begin_nested()
    yield session
    session.close()
    transaction.rollback()
    connection.close()

def test_metadata_ingestion_success(db_session, monkeypatch):
    # Mock yfinance Ticker info
    mock_ticker = MagicMock()
    mock_ticker.info = {
        "sector": "Technology",
        "industry": "Software-Application"
    }
    
    # We monkeypatch yfinance.Ticker to return our mock
    import yfinance as yf
    monkeypatch.setattr(yf, "Ticker", lambda symbol: mock_ticker)
    
    # Mock market service fetch_historical_prices and corp action sync to avoid actual API calls
    monkeypatch.setattr(MarketDataService, "fetch_historical_prices", lambda *args, **kwargs: None)
    from engine.market_data.corporate_actions import CorporateActionService
    monkeypatch.setattr(CorporateActionService, "sync_splits_for_ticker", lambda *args, **kwargs: None)
    
    # Create test portfolio
    portfolio = Portfolio(id=uuid.uuid4(), user_id=uuid.uuid4(), name="Test Portfolio")
    db_session.add(portfolio)
    db_session.flush()
    
    # Create transaction service
    tx_service = TransactionService(db_session)
    
    # Simulating upload of csv contents with ticker "MSFT"
    csv_content = (
        "ticker,transaction_type,quantity,price_per_unit,execution_date\n"
        "MSFT,BUY,10,350.00,2026-06-20\n"
    ).encode("utf-8")
    
    tx_service.process_upload(portfolio, csv_content, "test.csv")
    
    # Verify transaction got created
    tx = db_session.query(TransactionLedger).filter(TransactionLedger.ticker == "MSFT").first()
    assert tx is not None
    
    # Verify metadata got cached in AssetMetadata
    metadata = db_session.query(AssetMetadata).filter(AssetMetadata.ticker == "MSFT").first()
    assert metadata is not None
    assert metadata.sector == "Technology"
    assert metadata.industry == "Software-Application"

def test_metadata_ingestion_failure_fallback(db_session, monkeypatch):
    # Mock yfinance to raise an exception
    import yfinance as yf
    def mock_ticker_raise(symbol):
        raise Exception("YFinance rate limited or offline")
    monkeypatch.setattr(yf, "Ticker", mock_ticker_raise)
    
    # Mock other services
    monkeypatch.setattr(MarketDataService, "fetch_historical_prices", lambda *args, **kwargs: None)
    from engine.market_data.corporate_actions import CorporateActionService
    monkeypatch.setattr(CorporateActionService, "sync_splits_for_ticker", lambda *args, **kwargs: None)
    
    # Create test portfolio
    portfolio = Portfolio(id=uuid.uuid4(), user_id=uuid.uuid4(), name="Test Portfolio")
    db_session.add(portfolio)
    db_session.flush()
    
    # Create transaction service
    tx_service = TransactionService(db_session)
    
    csv_content = (
        "ticker,transaction_type,quantity,price_per_unit,execution_date\n"
        "AAPL,BUY,5,180.00,2026-06-21\n"
    ).encode("utf-8")
    
    tx_service.process_upload(portfolio, csv_content, "test2.csv")
    
    # Verify metadata falls back to "Unknown" rather than crashing the ingestion
    metadata = db_session.query(AssetMetadata).filter(AssetMetadata.ticker == "AAPL").first()
    assert metadata is not None
    assert metadata.sector == "Unknown"
    assert metadata.industry == "Unknown"

def test_metadata_cache_hit_prevents_network_call(db_session, monkeypatch):
    # Pre-populate cache
    cached_meta = AssetMetadata(
        ticker="MSFT",
        sector="Technology",
        industry="Software"
    )
    db_session.add(cached_meta)
    db_session.flush()

    # Mock yfinance to raise an AssertionError if called, to prove it was not called
    import yfinance as yf
    def mock_ticker_error(symbol):
        raise AssertionError("yfinance Ticker was called when data should be cached!")
    monkeypatch.setattr(yf, "Ticker", mock_ticker_error)

    # Initialize market data service
    market_service = MarketDataService(db_session)
    # This should return immediately because of cache hit
    market_service.fetch_and_cache_metadata("MSFT")

    # Verify no new record was created (still 1 record, matching the cached one)
    records = db_session.query(AssetMetadata).filter(AssetMetadata.ticker == "MSFT").all()
    assert len(records) == 1
    assert records[0].sector == "Technology"
