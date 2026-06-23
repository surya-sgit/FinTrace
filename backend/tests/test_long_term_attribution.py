import sys
import os
import pytest
import uuid
import datetime
from decimal import Decimal

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from domain.models import Base, Portfolio, TransactionLedger
from engine.analytics.long_term_attribution import LongTermAttributionEngine
from engine.market_data.market_service import MarketDataService

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB

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


# 1. Mocking the Pricing Service Interface
@pytest.fixture(autouse=True)
def mock_market_data(monkeypatch):
    def mock_get_prices_bulk(self, tickers, target_dates):
        result = {d: {} for d in target_dates}
        for d in target_dates:
            for ticker in tickers:
                if ticker == "RELIANCE.NS":
                    # Let's say it started at 2000 and ended at 3000
                    if d == datetime.date(2023, 1, 1):
                        result[d][ticker] = 2000.00
                    elif d == datetime.date(2025, 1, 1):
                        result[d][ticker] = 3000.00
                    else:
                        result[d][ticker] = 2500.00
        return result
        
    monkeypatch.setattr(MarketDataService, "get_prices_bulk", mock_get_prices_bulk)

def test_long_term_organic_variation(db_session):
    port_id = uuid.uuid4()
    
    # 1. Buy 10 shares at 2000 on Jan 1, 2023 (Cost: 20000)
    tx1 = TransactionLedger(
        id=uuid.uuid4(),
        portfolio_id=port_id,
        ticker="RELIANCE.NS",
        transaction_type="BUY",
        quantity=Decimal("10.0"),
        price_per_unit=Decimal("2000.00"),
        execution_date=datetime.date(2023, 1, 1),
        settlement_date=datetime.date(2023, 1, 2),
        checksum="tx1"
    )
    
    # 2. Buy 5 more shares at 2500 on Jan 1, 2024 (Cost: 12500)
    tx2 = TransactionLedger(
        id=uuid.uuid4(),
        portfolio_id=port_id,
        ticker="RELIANCE.NS",
        transaction_type="BUY",
        quantity=Decimal("5.0"),
        price_per_unit=Decimal("2500.00"),
        execution_date=datetime.date(2024, 1, 1),
        settlement_date=datetime.date(2024, 1, 2),
        checksum="tx2"
    )
    
    # 3. Dividend of 100/share on 15 shares on Dec 31, 2024 (Gain: 1500)
    tx3 = TransactionLedger(
        id=uuid.uuid4(),
        portfolio_id=port_id,
        ticker="RELIANCE.NS",
        transaction_type="DIVIDEND",
        quantity=Decimal("15.0"),
        price_per_unit=Decimal("100.00"),
        execution_date=datetime.date(2024, 12, 31),
        settlement_date=datetime.date(2024, 12, 31),
        checksum="tx3"
    )
    
    db_session.add_all([tx1, tx2, tx3])
    db_session.flush()
    
    engine = LongTermAttributionEngine(db_session, port_id)
    
    start_date = datetime.date(2023, 1, 1)
    end_date = datetime.date(2025, 1, 1)
    
    result = engine.execute_full_long_term_analysis(start_date, end_date)
    
    organic = next(item for item in result["organic_variation"] if item["ticker"] == "RELIANCE.NS")
    mwr = next(item for item in result["mwr_slicing"] if item["ticker"] == "RELIANCE.NS")
    
    # Let's manually calculate expected organic variation:
    # A_start = 0 (since tx1 is ON start_date, q_start is evaluated < start_date, which is 0)
    # A_end = 15 shares * 3000 = 45000
    # CF_T = 20000 + 12500 = 32500
    # Dividends = 1500
    # V = A_end - A_start - CF_T + Dividends = 45000 - 0 - 32500 + 1500 = 14000
    assert organic["net_organic_contribution"] == Decimal('14000.0000')
    
    # MWR should be positive
    assert mwr["standalone_xirr"] > 0.0

from domain.models import CorporateActionEvent

def test_corporate_action_split(db_session):
    port_id = uuid.uuid4()
    
    # Buy 10 shares at 4000 on Jan 1, 2024
    tx1 = TransactionLedger(
        id=uuid.uuid4(),
        portfolio_id=port_id,
        ticker="RELIANCE.NS",
        transaction_type="BUY",
        quantity=Decimal("10.0"),
        price_per_unit=Decimal("4000.00"),
        execution_date=datetime.date(2024, 1, 1),
        settlement_date=datetime.date(2024, 1, 2),
        checksum="split_tx1"
    )
    
    # 1:10 split on July 1, 2024
    split_event = CorporateActionEvent(
        ticker="RELIANCE.NS",
        ex_date=datetime.date(2024, 7, 1),
        action_type="SPLIT",
        adjustment_factor=Decimal("10.0")
    )
    
    db_session.add_all([tx1, split_event])
    db_session.flush()
    
    engine = LongTermAttributionEngine(db_session, port_id)
    # The mock market price on 2025-01-01 is 3000. 
    # With a 10x split, we hold 100 shares. 100 * 3000 = 300,000 terminal value.
    # Initial cost = 40,000. Organic variation should be 260,000
    
    result = engine.execute_full_long_term_analysis(datetime.date(2024, 1, 1), datetime.date(2025, 1, 1))
    organic = next(item for item in result["organic_variation"] if item["ticker"] == "RELIANCE.NS")
    
    assert organic["net_organic_contribution"] == Decimal('260000.0000')


def test_closed_loop_realization(db_session):
    port_id = uuid.uuid4()
    
    # Buy 10 shares at 2000
    tx1 = TransactionLedger(
        id=uuid.uuid4(),
        portfolio_id=port_id,
        ticker="RELIANCE.NS",
        transaction_type="BUY",
        quantity=Decimal("10.0"),
        price_per_unit=Decimal("2000.00"),
        execution_date=datetime.date(2023, 1, 1),
        settlement_date=datetime.date(2023, 1, 2),
        checksum="close_tx1"
    )
    
    # Sell all 10 shares at 2500
    tx2 = TransactionLedger(
        id=uuid.uuid4(),
        portfolio_id=port_id,
        ticker="RELIANCE.NS",
        transaction_type="SELL",
        quantity=Decimal("10.0"),
        price_per_unit=Decimal("2500.00"),
        execution_date=datetime.date(2024, 1, 1),
        settlement_date=datetime.date(2024, 1, 2),
        checksum="close_tx2"
    )
    
    db_session.add_all([tx1, tx2])
    db_session.flush()
    
    engine = LongTermAttributionEngine(db_session, port_id)
    # The terminal value in 2025 will be 0 because q_end = 0.
    # But it should STILL appear in the results.
    result = engine.execute_full_long_term_analysis(datetime.date(2023, 1, 1), datetime.date(2025, 1, 1))
    
    organic = next((item for item in result["organic_variation"] if item["ticker"] == "RELIANCE.NS"), None)
    assert organic is not None
    # Profit of 5000
    assert organic["net_organic_contribution"] == Decimal('5000.0000')


def test_cash_drag_mwr(db_session):
    port_id = uuid.uuid4()
    
    # Deposit 100,000 on Jan 1, 2023
    tx1 = TransactionLedger(
        id=uuid.uuid4(),
        portfolio_id=port_id,
        ticker="",
        transaction_type="DEPOSIT",
        quantity=Decimal("1.0"),
        price_per_unit=Decimal("100000.00"),
        execution_date=datetime.date(2023, 1, 1),
        settlement_date=datetime.date(2023, 1, 1),
        checksum="cash_tx1"
    )
    
    # Deploy only 20,000 of it into Reliance
    tx2 = TransactionLedger(
        id=uuid.uuid4(),
        portfolio_id=port_id,
        ticker="RELIANCE.NS",
        transaction_type="BUY",
        quantity=Decimal("10.0"),
        price_per_unit=Decimal("2000.00"),
        execution_date=datetime.date(2023, 1, 1),
        settlement_date=datetime.date(2023, 1, 2),
        checksum="cash_tx2"
    )
    
    db_session.add_all([tx1, tx2])
    db_session.flush()
    
    engine = LongTermAttributionEngine(db_session, port_id)
    result = engine.execute_full_long_term_analysis(datetime.date(2023, 1, 1), datetime.date(2025, 1, 1))
    
    # Reliance Standalone XIRR vs Cash Drag (Aggregate)
    reliance_mwr = next(item for item in result["mwr_slicing"] if item["ticker"] == "RELIANCE.NS")
    cash_drag_mwr = next(item for item in result["mwr_slicing"] if item["ticker"] == "CASH_DRAG")
    
    # Aggregate XIRR should be significantly lower because 80,000 is sitting un-deployed making 0%
    assert cash_drag_mwr["standalone_xirr"] < reliance_mwr["standalone_xirr"]
