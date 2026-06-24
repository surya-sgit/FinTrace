"""
Tests for cross-portfolio consolidation: exact summed invested/current value, merged
holdings, and the Equity vs Mutual-Fund value split.
"""

import os
import sys
import uuid
import datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from domain.models import Base, User, Portfolio, TransactionLedger, AssetPrices
from engine.math_core.consolidation_engine import ConsolidationEngine


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"


engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="module", autouse=True)
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


def _price(ticker, value, d):
    v = Decimal(str(value))
    return AssetPrices(
        ticker=ticker, price_date=d, open_price=v, high_price=v, low_price=v,
        close_price=v, adjusted_close=v, volume=0,
    )


def _buy(pid, ticker, qty, price, d, asset_class="EQUITY"):
    return TransactionLedger(
        id=uuid.uuid4(), portfolio_id=pid, ticker=ticker, transaction_type="BUY",
        quantity=Decimal(str(qty)), price_per_unit=Decimal(str(price)),
        brokerage_fees=Decimal("0"), asset_class=asset_class, execution_date=d,
        settlement_date=d + datetime.timedelta(days=1), checksum=str(uuid.uuid4()),
    )


def test_consolidation_sums_and_asset_split(db_session):
    today = datetime.date.today()
    uid = uuid.uuid4()
    db_session.add(User(id=uid, email="x@y.com", hashed_password="h", created_at=datetime.datetime.now()))

    p1 = uuid.uuid4()
    p2 = uuid.uuid4()
    db_session.add_all([
        Portfolio(id=p1, user_id=uid, name="Equities", tax_jurisdiction="IN", created_at=datetime.datetime.now()),
        Portfolio(id=p2, user_id=uid, name="Funds", tax_jurisdiction="IN", created_at=datetime.datetime.now()),
    ])
    # P1: 100 TCS @1000 invested=100000, priced @1500 -> 150000 equity
    db_session.add_all([
        _buy(p1, "TCS.NS", 100, 1000, datetime.date(2023, 1, 1)),
        _price("TCS.NS", 1500, today),
    ])
    # P2: 50 debt-MF units @100 invested=5000, NAV 120 -> 6000 mutual fund
    db_session.add_all([
        _buy(p2, "INF123D01010", 50, 100, datetime.date(2023, 1, 1), asset_class="DEBT_MF"),
        _price("INF123D01010", 120, today),
    ])
    db_session.flush()

    result = ConsolidationEngine(db_session, uid).aggregate()

    assert result["portfolio_count"] == 2
    assert result["total_invested"] == 105000.0
    assert result["equity_value"] == 150000.0
    assert result["mutual_fund_value"] == 6000.0
    assert result["total_current_value"] == 156000.0
    assert result["total_net_worth"] == 156000.0
    assert result["unrealized_pl"] == 51000.0
    assert {p["name"] for p in result["portfolios"]} == {"Equities", "Funds"}


def test_consolidation_empty_user(db_session):
    uid = uuid.uuid4()
    db_session.add(User(id=uid, email="z@y.com", hashed_password="h", created_at=datetime.datetime.now()))
    db_session.flush()

    result = ConsolidationEngine(db_session, uid).aggregate()
    assert result["portfolio_count"] == 0
    assert result["total_net_worth"] == 0.0
    assert result["blended_xirr"] == 0.0
