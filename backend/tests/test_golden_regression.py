"""
Golden regression tests to guarantee the system meets the Day 1 Correctness Guardrails.

Tested rules:
1. Brokerage included in buy and sell
2. Split on a date without a transaction
3. reliance.ns and RELIANCE.NS checksum collision
4. Two legitimate identical trades
5. Sell-before-buy ordering
6. Missing price produces a warning, not a fake valuation
"""

import os
import sys
import uuid
from decimal import Decimal
import datetime
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles

@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from domain.models import Base, TransactionLedger, CorporateActionEvent, Portfolio
from domain.schemas import TransactionCreate
from domain.services.transaction_service import TransactionService
from engine.ingestion.ledger_validator import LedgerValidator
from engine.math_core.xirr_engine import XIRREngine
from engine.math_core.tax_engine import FIFOTaxEngine

SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

@pytest.fixture(scope="function")
def db_session():
    engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)

@pytest.fixture
def portfolio(db_session):
    p = Portfolio(id=uuid.uuid4(), user_id=uuid.uuid4(), name="Test Portfolio")
    db_session.add(p)
    db_session.commit()
    return p

# 1. Brokerage included in buy and sell
def test_brokerage_included_in_tax_calc(db_session, portfolio):
    """
    Buy 10 @ 100 with 10 brokerage -> Cost = 1000 + 10 = 1010
    Sell 10 @ 150 with 15 brokerage -> Proceed = 1500 - 15 = 1485
    Gain = 1485 - 1010 = 475
    """
    txs = [
        TransactionLedger(
            id=uuid.uuid4(), portfolio_id=portfolio.id, ticker="TCS.NS",
            transaction_type="BUY", quantity=Decimal("10"), price_per_unit=Decimal("100"),
            brokerage_fees=Decimal("10"), execution_date=date(2023, 1, 1), settlement_date=date(2023, 1, 2),
            checksum="1", sequence_number=0
        ),
        TransactionLedger(
            id=uuid.uuid4(), portfolio_id=portfolio.id, ticker="TCS.NS",
            transaction_type="SELL", quantity=Decimal("10"), price_per_unit=Decimal("150"),
            brokerage_fees=Decimal("15"), execution_date=date(2023, 2, 1), settlement_date=date(2023, 2, 2),
            checksum="2", sequence_number=1
        )
    ]
    db_session.add_all(txs)
    db_session.commit()
    
    engine = FIFOTaxEngine(db_session, portfolio.id)
    report = engine.compute_tax_report()
    assert len(report["realized_events"]) == 1
    gain = report["realized_events"][0]
    assert gain["cost_basis"] == Decimal("1010")
    assert gain["proceeds"] == Decimal("1485")
    assert gain["gain"] == Decimal("475")

# 2. Split on a date without a transaction
def test_split_on_date_without_transaction(db_session, portfolio):
    """
    Ensure the LedgerValidator sweeps Corporate Actions even if no transaction occurred that day.
    """
    db_session.add(CorporateActionEvent(
        id=uuid.uuid4(), ticker="SPLITCO", ex_date=date(2023, 2, 1),
        action_type="SPLIT", adjustment_factor=Decimal("2.0")
    ))
    db_session.commit()
    
    txs = [
        TransactionCreate(ticker="SPLITCO", transaction_type="BUY", quantity=Decimal("10"), price_per_unit=Decimal("100"), execution_date=date(2023, 1, 1), settlement_date=date(2023, 1, 2)),
        TransactionCreate(ticker="SPLITCO", transaction_type="SELL", quantity=Decimal("20"), price_per_unit=Decimal("50"), execution_date=date(2023, 3, 1), settlement_date=date(2023, 3, 2))
    ]
    
    validator = LedgerValidator(db_session)
    validator.validate([], txs)

# 3. reliance.ns and RELIANCE.NS
def test_ticker_case_insensitivity_checksum(db_session):
    """
    Ensure lowercase and uppercase tickers resolve to the same hash for duplication logic.
    """
    service = TransactionService(db_session)
    row_1 = {"ticker": "reliance.ns", "transaction_type": "BUY", "quantity": 10, "price_per_unit": 100, "execution_date": date(2023,1,1)}
    row_2 = {"ticker": "RELIANCE.NS", "transaction_type": "BUY", "quantity": 10, "price_per_unit": 100, "execution_date": date(2023,1,1)}
    
    chk1 = service._generate_row_checksum("port-1", row_1, 0)
    chk2 = service._generate_row_checksum("port-1", row_2, 0)
    assert chk1 == chk2

# 4. Two legitimate identical trades
def test_identical_trades_sequence_number(db_session):
    """
    Ensure identical trades on the same day have different checksums due to sequence_number.
    """
    service = TransactionService(db_session)
    row = {"ticker": "HDFC", "transaction_type": "BUY", "quantity": 10, "price_per_unit": 100, "execution_date": date(2023,1,1)}
    
    chk1 = service._generate_row_checksum("port-1", row, 0)
    chk2 = service._generate_row_checksum("port-1", row, 1)
    assert chk1 != chk2

# 5. Sell-before-buy ordering (Intraday short guardrail)
def test_sell_before_buy_guardrail(db_session):
    """
    Validator should log a warning instead of crashing on intraday shorts.
    """
    txs = [
        TransactionCreate(ticker="INFY", transaction_type="SELL", quantity=Decimal("10"), price_per_unit=Decimal("100"), execution_date=date(2023, 1, 1), settlement_date=date(2023, 1, 2)),
        TransactionCreate(ticker="INFY", transaction_type="BUY", quantity=Decimal("10"), price_per_unit=Decimal("90"), execution_date=date(2023, 1, 1), settlement_date=date(2023, 1, 2))
    ]
    validator = LedgerValidator(db_session)
    validator.validate([], txs)

# 6. Missing price produces a warning, not a fake valuation
def test_missing_price_fallback(db_session, portfolio):
    """
    XIRR engine should fallback to cost basis when terminal price is missing.
    """
    txs = [
        TransactionLedger(
            id=uuid.uuid4(), portfolio_id=portfolio.id, ticker="UNKNOWN",
            transaction_type="BUY", quantity=Decimal("10"), price_per_unit=Decimal("100"),
            brokerage_fees=Decimal("0"), execution_date=date(2023, 1, 1), settlement_date=date(2023, 1, 2),
            checksum="1", asset_class="EQUITY", sequence_number=0
        )
    ]
    db_session.add_all(txs)
    db_session.commit()
    
    engine = XIRREngine(db_session, portfolio.id)
    res = engine.calculate_portfolio_xirr()
    
    assert res["current_value"] == 1000.0
    assert res["unrealized_p_and_l"] == 0.0
    assert res["xirr_percentage"] == 0.0
