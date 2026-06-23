import sys
import os
import uuid
import datetime
from decimal import Decimal
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from api.main import app
from api.dependencies import get_db, get_current_user
from domain.models import Base, TransactionLedger, User, Portfolio
from engine.analytics.attribution import PerformanceAttributionEngine
from engine.market_data.market_service import MarketDataService

# 1. Foolproof Test Scaffolding & Shared Fixtures

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

@pytest.fixture
def freeze_time(monkeypatch):
    class MockDate(datetime.date):
        @classmethod
        def today(cls):
            return datetime.date(2026, 6, 22)
            
    monkeypatch.setattr("engine.analytics.attribution.date", MockDate)

# 2. Mocking the Pricing Service Interface
@pytest.fixture(autouse=True)
def mock_market_data(monkeypatch):
    def mock_get_prices_bulk(self, tickers, target_dates):
        result = {d: {} for d in target_dates}
        for d in target_dates:
            for ticker in tickers:
                if ticker == "TCS.NS":
                    if d == datetime.date(2026, 6, 22):
                        result[d][ticker] = 4000.00
                    elif d == datetime.date(2026, 6, 21):
                        result[d][ticker] = 4050.00
        return result
        
    monkeypatch.setattr(MarketDataService, "get_prices_bulk", mock_get_prices_bulk)


# 3. Strict Deterministic Vector Assertions

def test_attribution_legacy_drift_success(db_session, freeze_time):
    port_id = uuid.uuid4()
    tx = TransactionLedger(
        id=uuid.uuid4(),
        portfolio_id=port_id,
        ticker="TCS.NS",
        transaction_type="BUY",
        quantity=Decimal("100.0"),
        price_per_unit=Decimal("3800.00"),
        execution_date=datetime.date(2026, 6, 15),
        settlement_date=datetime.date(2026, 6, 17),
        checksum="chk_1"
    )
    db_session.add(tx)
    db_session.flush()
    
    attribution_engine = PerformanceAttributionEngine(db_session, port_id)
    result = attribution_engine.identify_top_drags(datetime.date(2026, 6, 22))
    
    matrix = result["full_contribution_matrix"]
    assert len(matrix) == 1
    assert matrix[0]["legacy_drift"] == -5000.00
    assert matrix[0]["intraday_impact"] == 0.00


def test_attribution_intraday_impact_success(db_session, freeze_time):
    port_id = uuid.uuid4()
    tx = TransactionLedger(
        id=uuid.uuid4(),
        portfolio_id=port_id,
        ticker="TCS.NS",
        transaction_type="BUY",
        quantity=Decimal("50.0"),
        price_per_unit=Decimal("3980.00"),
        execution_date=datetime.date(2026, 6, 22),
        settlement_date=datetime.date(2026, 6, 24),
        checksum="chk_2"
    )
    db_session.add(tx)
    db_session.flush()
    
    attribution_engine = PerformanceAttributionEngine(db_session, port_id)
    result = attribution_engine.identify_top_drags(datetime.date(2026, 6, 22))
    
    matrix = result["full_contribution_matrix"]
    assert len(matrix) == 1
    assert matrix[0]["legacy_drift"] == 0.00
    assert matrix[0]["intraday_impact"] == 1000.00


def test_attribution_corporate_dividend_shield(db_session, freeze_time):
    port_id = uuid.uuid4()
    tx1 = TransactionLedger(
        id=uuid.uuid4(),
        portfolio_id=port_id,
        ticker="TCS.NS",
        transaction_type="BUY",
        quantity=Decimal("100.0"),
        price_per_unit=Decimal("3800.00"),
        execution_date=datetime.date(2026, 6, 15),
        settlement_date=datetime.date(2026, 6, 17),
        checksum="chk_3"
    )
    tx2 = TransactionLedger(
        id=uuid.uuid4(),
        portfolio_id=port_id,
        ticker="TCS.NS",
        transaction_type="DIVIDEND",
        quantity=Decimal("100.0"),
        price_per_unit=Decimal("50.00"),
        execution_date=datetime.date(2026, 6, 22),
        settlement_date=datetime.date(2026, 6, 24),
        checksum="chk_4"
    )
    db_session.add_all([tx1, tx2])
    db_session.flush()
    
    attribution_engine = PerformanceAttributionEngine(db_session, port_id)
    result = attribution_engine.identify_top_drags(datetime.date(2026, 6, 22))
    
    matrix = result["full_contribution_matrix"]
    assert len(matrix) == 1
    assert matrix[0]["legacy_drift"] == -5000.00
    assert matrix[0]["corporate_shield"] == 5000.00
    assert matrix[0]["net_contribution"] == 0.00


def test_attribution_ledger_corruption_blocks(db_session, freeze_time):
    port_id = uuid.uuid4()
    tx = TransactionLedger(
        id=uuid.uuid4(),
        portfolio_id=port_id,
        ticker="TCS.NS",
        transaction_type="SELL",
        quantity=Decimal("100.0"),
        price_per_unit=Decimal("4000.00"),
        execution_date=datetime.date(2026, 6, 20),
        settlement_date=datetime.date(2026, 6, 22),
        checksum="chk_5"
    )
    db_session.add(tx)
    db_session.flush()
    
    attribution_engine = PerformanceAttributionEngine(db_session, port_id)
    result = attribution_engine.identify_top_drags(datetime.date(2026, 6, 22))
    assert result["primary_drag_ticker"] is None
    assert result["absolute_impact"] == Decimal("0.0000")


# 4. Protected API Route Request Validations

@pytest.fixture
def test_client(db_session):
    def override_get_db():
        yield db_session
        
    def override_get_current_user():
        return User(id=uuid.UUID("11111111-1111-1111-1111-111111111111"), email="test@test.com", hashed_password="hashed", created_at=datetime.datetime.now())
        
    original_overrides = app.dependency_overrides.copy()
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    
    with TestClient(app) as client:
        yield client
        
    app.dependency_overrides.clear()
    app.dependency_overrides.update(original_overrides)


def test_api_attribution_future_date_rejected(test_client, freeze_time):
    port_id = uuid.uuid4()
    future_date = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
    response = test_client.get(f"/api/v1/analytics/{port_id}/attribution?target_date={future_date}")
    assert response.status_code == 400


def test_api_attribution_tenant_isolation_enforced(test_client, db_session, freeze_time):
    user_b_id = uuid.UUID("22222222-2222-2222-2222-222222222222")
    port_id = uuid.uuid4()
    portfolio = Portfolio(
        id=port_id, 
        user_id=user_b_id, 
        name="User B Portfolio", 
        tax_jurisdiction="IN", 
        created_at=datetime.datetime.now()
    )
    db_session.add(portfolio)
    db_session.flush()
    
    today = "2026-06-22"
    response = test_client.get(f"/api/v1/analytics/{port_id}/attribution?target_date={today}")
    assert response.status_code == 404
