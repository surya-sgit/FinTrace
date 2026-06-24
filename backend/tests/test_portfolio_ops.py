"""
Tests for (1) the valued holdings breakdown that powers asset allocation by MARKET
VALUE (not quantity), and (2) the delete-portfolio endpoint.
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
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from api.main import app
from api.dependencies import get_db, get_current_user
from domain.models import Base, User, Portfolio, TransactionLedger, AssetPrices
from engine.math_core.xirr_engine import XIRREngine


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


def _buy(pid, ticker, qty, price, d, asset_class="EQUITY"):
    return TransactionLedger(
        id=uuid.uuid4(), portfolio_id=pid, ticker=ticker, transaction_type="BUY",
        quantity=Decimal(str(qty)), price_per_unit=Decimal(str(price)),
        brokerage_fees=Decimal("0"), asset_class=asset_class, execution_date=d,
        settlement_date=d + datetime.timedelta(days=1), checksum=str(uuid.uuid4()),
    )


def _price(ticker, value, d):
    v = Decimal(str(value))
    return AssetPrices(
        ticker=ticker, price_date=d, open_price=v, high_price=v, low_price=v,
        close_price=v, adjusted_close=v, volume=0,
    )


def test_holdings_breakdown_is_by_market_value(db_session):
    """A fund with many units must not dominate a high-priced stock — allocation is by
    market value. 100 TCS @1500 = 150000 > 200 fund units @120 = 24000."""
    today = datetime.date.today()
    pid = uuid.uuid4()
    db_session.add_all([
        _buy(pid, "TCS.NS", 100, 1000, datetime.date(2023, 1, 1)),
        _buy(pid, "INF123D01010", 200, 100, datetime.date(2023, 1, 1), asset_class="DEBT_MF"),
        _price("TCS.NS", 1500, today),
        _price("INF123D01010", 120, today),
    ])
    db_session.flush()

    result = XIRREngine(db_session=db_session, portfolio_id=pid).calculate_portfolio_xirr()
    holdings = result["holdings"]

    assert holdings[0]["ticker"] == "TCS.NS"          # largest by value, sorted first
    assert holdings[0]["market_value"] == 150000.0
    fund = next(h for h in holdings if h["ticker"] == "INF123D01010")
    assert fund["market_value"] == 24000.0
    assert fund["asset_class"] == "DEBT_MF"
    # The fund has MORE units but LESS value — the old quantity-based pie was wrong.
    assert fund["quantity"] > holdings[0]["quantity"]
    assert fund["market_value"] < holdings[0]["market_value"]


@pytest.fixture
def client(db_session):
    # NB: use a UUID with hex letters — an all-numeric UUID is stored with SQLite's
    # NUMERIC affinity and fails to round-trip through the UUID type in tests.
    user_id = uuid.UUID("a1b2c3d4-1111-2222-3333-444455556666")

    def override_get_db():
        yield db_session

    def override_get_current_user():
        return User(id=user_id, email="t@t.com", hashed_password="h", created_at=datetime.datetime.now())

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    with TestClient(app) as c:
        yield c, user_id
    app.dependency_overrides.clear()


def test_delete_portfolio_removes_it_and_ledger(client, db_session):
    c, user_id = client
    pid = uuid.uuid4()
    db_session.add(Portfolio(id=pid, user_id=user_id, name="Temp", tax_jurisdiction="IN", created_at=datetime.datetime.now()))
    db_session.add(_buy(pid, "TCS.NS", 10, 100, datetime.date(2024, 1, 1)))
    db_session.flush()

    resp = c.delete(f"/api/v1/portfolios/{pid}")
    assert resp.status_code == 204
    assert db_session.query(Portfolio).filter(Portfolio.id == pid).first() is None
    assert db_session.query(TransactionLedger).filter(TransactionLedger.portfolio_id == pid).count() == 0


def test_delete_other_users_portfolio_forbidden(client, db_session):
    c, _ = client
    other = uuid.uuid4()
    pid = uuid.uuid4()
    db_session.add(Portfolio(id=pid, user_id=other, name="NotMine", tax_jurisdiction="IN", created_at=datetime.datetime.now()))
    db_session.flush()

    resp = c.delete(f"/api/v1/portfolios/{pid}")
    assert resp.status_code == 404
    assert db_session.query(Portfolio).filter(Portfolio.id == pid).first() is not None
