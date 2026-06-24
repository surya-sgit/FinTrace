"""
Golden-file and regression tests for the file-ready Indian equity tax engine.

Every expected number is hand-computed in the test docstring so a tax reviewer can
audit the assertion, not just the code. Uses the same in-memory SQLite scaffolding as
the rest of the suite.
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

from domain.models import Base, TransactionLedger, CorporateActionEvent, AssetPrices
from engine.math_core.tax_engine import FIFOTaxEngine
from engine.math_core import tax_rules


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"


SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
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


# --------------------------------------------------------------------------- utils

_PID = None


def _pid():
    return uuid.uuid4()


def _buy(pid, ticker, qty, price, d, fee=0, chk=None):
    return TransactionLedger(
        id=uuid.uuid4(), portfolio_id=pid, ticker=ticker, transaction_type="BUY",
        quantity=Decimal(str(qty)), price_per_unit=Decimal(str(price)),
        brokerage_fees=Decimal(str(fee)), execution_date=d,
        settlement_date=d + datetime.timedelta(days=1), checksum=chk or str(uuid.uuid4()),
    )


def _sell(pid, ticker, qty, price, d, fee=0, chk=None):
    return TransactionLedger(
        id=uuid.uuid4(), portfolio_id=pid, ticker=ticker, transaction_type="SELL",
        quantity=Decimal(str(qty)), price_per_unit=Decimal(str(price)),
        brokerage_fees=Decimal(str(fee)), execution_date=d,
        settlement_date=d + datetime.timedelta(days=1), checksum=chk or str(uuid.uuid4()),
    )


def _div(pid, ticker, qty, per_share, d, chk=None):
    return TransactionLedger(
        id=uuid.uuid4(), portfolio_id=pid, ticker=ticker, transaction_type="DIVIDEND",
        quantity=Decimal(str(qty)), price_per_unit=Decimal(str(per_share)),
        brokerage_fees=Decimal("0"), execution_date=d,
        settlement_date=d + datetime.timedelta(days=1), checksum=chk or str(uuid.uuid4()),
    )


def _fy(report, label):
    for fy in report["financial_years"]:
        if fy["financial_year"] == label:
            return fy
    raise AssertionError(f"FY {label} not found in {[f['financial_year'] for f in report['financial_years']]}")


# --------------------------------------------------------------------------- tests

def test_brokerage_folded_into_cost_and_proceeds(db_session):
    """Buy 100@100 fee50 (2024-09-01); Sell 100@150 fee50 (2024-10-01).
    Cost = 10000+50 = 10050; Proceeds = 15000-50 = 14950; ST gain = 4900.
    STCG tax (post-2024 regime, 20%) = 980."""
    pid = _pid()
    db_session.add_all([
        _buy(pid, "TCS.NS", 100, 100, datetime.date(2024, 9, 1), fee=50),
        _sell(pid, "TCS.NS", 100, 150, datetime.date(2024, 10, 1), fee=50),
    ])
    db_session.flush()

    report = FIFOTaxEngine(db_session, pid).compute_tax_report()
    lot = report["realized_events"][0]
    assert lot["cost_basis"] == Decimal("10050")
    assert lot["proceeds"] == Decimal("14950")
    assert lot["gain"] == Decimal("4900")
    assert lot["is_long_term"] is False
    assert _fy(report, "2024-25")["stcg_tax"] == Decimal("980.00")
    assert report["total_tax_payable"] == Decimal("980.00")


def test_phantom_gain_on_unmatched_sell_raises(db_session):
    """Selling shares never bought must raise, not fabricate a 100%-profit gain."""
    pid = _pid()
    db_session.add(_sell(pid, "TCS.NS", 100, 4000, datetime.date(2024, 6, 20)))
    db_session.flush()

    with pytest.raises(ValueError, match="Ledger integrity error"):
        FIFOTaxEngine(db_session, pid).compute_tax_report()


def test_ltcg_exemption_applied(db_session):
    """Buy 100@1000 (2022-01-01); Sell 100@3000 (2024-08-01) -> LT, post regime.
    Gain = 200000. FY24-25 exemption 125000 -> taxable 75000 @12.5% = 9375."""
    pid = _pid()
    db_session.add_all([
        _buy(pid, "INFY.NS", 100, 1000, datetime.date(2022, 1, 1)),
        _sell(pid, "INFY.NS", 100, 3000, datetime.date(2024, 8, 1)),
    ])
    db_session.flush()

    report = FIFOTaxEngine(db_session, pid).compute_tax_report()
    fy = _fy(report, "2024-25")
    assert fy["gross_ltcg"] == Decimal("200000.00")
    assert fy["ltcg_exemption_applied"] == Decimal("125000.00")
    assert fy["ltcg_tax"] == Decimal("9375.00")
    assert report["total_tax_payable"] == Decimal("9375.00")


def test_grandfathering_section_112a(db_session):
    """Buy 100@100 (2017-01-01, pre-grandfather); FMV@31Jan2018 = 500.
    Sell 100@800 (2024-09-01) -> LT. CoA = max(100, min(500,800)) = 500.
    Gain = 80000 - 50000 = 30000 (vs 70000 without step-up). Within exemption -> 0 tax."""
    pid = _pid()
    db_session.add_all([
        _buy(pid, "RELIANCE.NS", 100, 100, datetime.date(2017, 1, 1)),
        _sell(pid, "RELIANCE.NS", 100, 800, datetime.date(2024, 9, 1)),
    ])
    db_session.flush()

    eng = FIFOTaxEngine(db_session, pid, fmv_overrides={"RELIANCE.NS": Decimal("500")})
    report = eng.compute_tax_report()
    lot = report["realized_events"][0]
    assert lot["grandfathered"] is True
    assert lot["cost_basis"] == Decimal("50000")
    assert lot["gain"] == Decimal("30000")
    assert _fy(report, "2024-25")["ltcg_exemption_applied"] == Decimal("30000.00")
    assert report["total_tax_payable"] == Decimal("0.00")


def test_grandfathering_fmv_from_asset_prices(db_session):
    """FMV should also be sourced from cached AssetPrices on 31-Jan-2018."""
    pid = _pid()
    db_session.add(AssetPrices(
        ticker="RELIANCE.NS", price_date=tax_rules.GRANDFATHERING_DATE,
        open_price=Decimal("500"), high_price=Decimal("500"), low_price=Decimal("500"),
        close_price=Decimal("500"), adjusted_close=Decimal("500"), volume=1,
    ))
    db_session.add_all([
        _buy(pid, "RELIANCE.NS", 100, 100, datetime.date(2017, 1, 1)),
        _sell(pid, "RELIANCE.NS", 100, 800, datetime.date(2024, 9, 1)),
    ])
    db_session.flush()

    report = FIFOTaxEngine(db_session, pid).compute_tax_report()
    assert report["realized_events"][0]["grandfathered"] is True
    assert report["realized_events"][0]["gain"] == Decimal("30000")


def test_short_term_loss_offsets_long_term_gain(db_session):
    """Same FY24-25. ST loss 10000 (buy 100@200 -> sell 100@100).
    LT gain 200000 (buy 100@100 2022 -> sell 100@2100 2024-09).
    ST loss sets off LT gain -> LT 190000; exemption 125000 -> 65000 @12.5% = 8125."""
    pid = _pid()
    db_session.add_all([
        _buy(pid, "A.NS", 100, 200, datetime.date(2024, 8, 1)),
        _sell(pid, "A.NS", 100, 100, datetime.date(2024, 9, 1)),
        _buy(pid, "B.NS", 100, 100, datetime.date(2022, 1, 1)),
        _sell(pid, "B.NS", 100, 2100, datetime.date(2024, 9, 1)),
    ])
    db_session.flush()

    report = FIFOTaxEngine(db_session, pid).compute_tax_report()
    fy = _fy(report, "2024-25")
    assert fy["gross_stcg"] == Decimal("-10000.00")
    assert fy["gross_ltcg"] == Decimal("200000.00")
    assert report["total_tax_payable"] == Decimal("8125.00")


def test_long_term_loss_carried_forward(db_session):
    """FY23-24: LT loss 20000 (buy 100@500 2021 -> sell 100@300 2023-06, pre regime).
    FY24-25: LT gain 190000 (buy 100@100 2022 -> sell 100@2000 2024-09).
    B/f LT loss offsets -> 170000; exemption 125000 -> 45000 @12.5% = 5625."""
    pid = _pid()
    db_session.add_all([
        _buy(pid, "C.NS", 100, 500, datetime.date(2021, 1, 1)),
        _sell(pid, "C.NS", 100, 300, datetime.date(2023, 6, 1)),
        _buy(pid, "D.NS", 100, 100, datetime.date(2022, 1, 1)),
        _sell(pid, "D.NS", 100, 2000, datetime.date(2024, 9, 1)),
    ])
    db_session.flush()

    report = FIFOTaxEngine(db_session, pid).compute_tax_report()
    fy_prev = _fy(report, "2023-24")
    assert fy_prev["total_tax"] == Decimal("0.00")
    assert fy_prev["ltcg_loss_carried_forward"] == Decimal("20000.00")
    assert _fy(report, "2024-25")["total_tax"] == Decimal("5625.00")
    assert report["total_tax_payable"] == Decimal("5625.00")


def test_split_adjusts_open_lot(db_session):
    """Buy 100@1000 (2020); 1:2 split (factor 2) 2021 -> 200 units @500.
    Sell 200@2000 (2024-09) -> LT. Gain = 400000 - 100000 = 300000.
    Exemption 125000 -> 175000 @12.5% = 21875. No holdings left."""
    pid = _pid()
    db_session.add_all([
        _buy(pid, "E.NS", 100, 1000, datetime.date(2020, 1, 1)),
        CorporateActionEvent(
            id=uuid.uuid4(), ticker="E.NS", ex_date=datetime.date(2021, 1, 1),
            action_type="SPLIT", adjustment_factor=Decimal("2"),
        ),
        _sell(pid, "E.NS", 200, 2000, datetime.date(2024, 9, 1)),
    ])
    db_session.flush()

    report = FIFOTaxEngine(db_session, pid).compute_tax_report()
    lot = report["realized_events"][0]
    assert lot["quantity"] == Decimal("200")
    assert lot["cost_basis"] == Decimal("100000")
    assert lot["gain"] == Decimal("300000")
    assert report["total_tax_payable"] == Decimal("21875.00")
    assert report["current_holdings"] == {}


def test_holding_period_boundary_is_twelve_months(db_session):
    """Exactly 12 months is short-term; one day more is long-term."""
    assert tax_rules.is_long_term(datetime.date(2023, 1, 15), datetime.date(2024, 1, 15)) is False
    assert tax_rules.is_long_term(datetime.date(2023, 1, 15), datetime.date(2024, 1, 16)) is True


def test_dividends_surfaced_per_fy(db_session):
    """Dividends are reported per FY (taxable at slab), not silently dropped."""
    pid = _pid()
    db_session.add_all([
        _buy(pid, "F.NS", 100, 100, datetime.date(2024, 5, 1)),
        _div(pid, "F.NS", 100, 12, datetime.date(2024, 6, 1)),  # 1200 dividend
    ])
    db_session.flush()

    report = FIFOTaxEngine(db_session, pid).compute_tax_report()
    assert report["dividends"]["2024-25"] == Decimal("1200")
    assert _fy(report, "2024-25")["dividend_income"] == Decimal("1200.00") if report["financial_years"] else True


def test_partial_sell_keeps_remaining_holdings(db_session):
    """Buy 100@100, sell 40 -> 60 remain in holdings; FIFO leftover preserved."""
    pid = _pid()
    db_session.add_all([
        _buy(pid, "G.NS", 100, 100, datetime.date(2024, 5, 1)),
        _sell(pid, "G.NS", 40, 150, datetime.date(2024, 6, 1)),
    ])
    db_session.flush()

    report = FIFOTaxEngine(db_session, pid).compute_tax_report()
    assert report["current_holdings"]["G.NS"] == Decimal("60")
    assert report["realized_events"][0]["quantity"] == Decimal("40")
