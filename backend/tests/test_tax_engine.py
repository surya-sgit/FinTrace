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


def _dividend_event(ticker, per_share, ex_date):
    return CorporateActionEvent(
        id=uuid.uuid4(), ticker=ticker, ex_date=ex_date,
        action_type="DIVIDEND", adjustment_factor=Decimal(str(per_share)),
    )
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


def _buy(pid, ticker, qty, price, d, fee=0, chk=None, asset_class="EQUITY"):
    return TransactionLedger(
        id=uuid.uuid4(), portfolio_id=pid, ticker=ticker, transaction_type="BUY",
        quantity=Decimal(str(qty)), price_per_unit=Decimal(str(price)),
        brokerage_fees=Decimal(str(fee)), asset_class=asset_class, execution_date=d,
        settlement_date=d + datetime.timedelta(days=1), checksum=chk or str(uuid.uuid4()),
    )


def _sell(pid, ticker, qty, price, d, fee=0, chk=None, asset_class="EQUITY"):
    return TransactionLedger(
        id=uuid.uuid4(), portfolio_id=pid, ticker=ticker, transaction_type="SELL",
        quantity=Decimal(str(qty)), price_per_unit=Decimal(str(price)),
        brokerage_fees=Decimal(str(fee)), asset_class=asset_class, execution_date=d,
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


def test_dividend_amount_is_quantity_times_price(db_session):
    """Regression for the silent-zero dividend bug: 20 shares x Rs.8.50/share = 170,
    surfaced in the same FY as a realized sell."""
    pid = _pid()
    db_session.add_all([
        _buy(pid, "INFY.NS", 100, 1000, datetime.date(2022, 1, 1)),
        _div(pid, "INFY.NS", 20, "8.50", datetime.date(2024, 6, 1)),  # 170 dividend
        _sell(pid, "INFY.NS", 100, 1500, datetime.date(2024, 9, 1)),
    ])
    db_session.flush()

    report = FIFOTaxEngine(db_session, pid).compute_tax_report()
    assert report["dividends"]["2024-25"] == Decimal("170.00")
    assert _fy(report, "2024-25")["dividend_income"] == Decimal("170.00")


def test_zero_value_dividend_rejected_by_schema():
    """A DIVIDEND row with price_per_unit=0 must fail validation, not record Rs.0."""
    from pydantic import ValidationError
    from domain import schemas

    with pytest.raises(ValidationError, match="dividend-per-share"):
        schemas.TransactionCreate(
            ticker="INFY", transaction_type="DIVIDEND",
            quantity=Decimal("20"), price_per_unit=Decimal("0"),
            execution_date=datetime.date(2024, 3, 1),
        )


def test_auto_dividend_from_holdings_times_per_share(db_session):
    """Dividend auto-derived from holdings on the ex-date, no manual row needed.
    Hold 100 INFY on ex-date 2024-06-01, Rs.7/share -> Rs.700 dividend (FY2024-25)."""
    pid = _pid()
    db_session.add_all([
        _buy(pid, "INFY.NS", 100, 1000, datetime.date(2022, 1, 1)),
        _dividend_event("INFY.NS", 7, datetime.date(2024, 6, 1)),
    ])
    db_session.flush()

    report = FIFOTaxEngine(db_session, pid).compute_tax_report()
    assert report["dividends"]["2024-25"] == Decimal("700")


def test_auto_dividend_uses_shares_held_on_ex_date(db_session):
    """Only shares held on the ex-date earn the dividend. Buy 100, sell 60 before the
    ex-date -> 40 held x Rs.5 = Rs.200."""
    pid = _pid()
    db_session.add_all([
        _buy(pid, "TCS.NS", 100, 1000, datetime.date(2023, 1, 1)),
        _sell(pid, "TCS.NS", 60, 1200, datetime.date(2024, 5, 1)),
        _dividend_event("TCS.NS", 5, datetime.date(2024, 6, 1)),
    ])
    db_session.flush()

    report = FIFOTaxEngine(db_session, pid).compute_tax_report()
    assert report["dividends"]["2024-25"] == Decimal("200")


def test_auto_dividend_not_double_counted_with_manual_row(db_session):
    """If the user also entered a manual dividend for the same ticker+date, the auto
    event is skipped (manual wins) — no double counting."""
    pid = _pid()
    db_session.add_all([
        _buy(pid, "WIPRO.NS", 100, 500, datetime.date(2022, 1, 1)),
        _div(pid, "WIPRO.NS", 100, "6.00", datetime.date(2024, 6, 1)),   # manual Rs.600
        _dividend_event("WIPRO.NS", 6, datetime.date(2024, 6, 1)),        # auto, same day
    ])
    db_session.flush()

    report = FIFOTaxEngine(db_session, pid).compute_tax_report()
    assert report["dividends"]["2024-25"] == Decimal("600.00")


# ----------------------------------------------------- mutual fund tax (all types)

def test_debt_mf_post_2023_taxed_at_slab(db_session):
    """Debt fund acquired on/after 01-Apr-2023 (Sec 50AA): gain always slab-taxed,
    regardless of holding period. Reported, not rupee-taxed. Gain 5000."""
    pid = _pid()
    db_session.add_all([
        _buy(pid, "INF123D01010", 100, 100, datetime.date(2024, 1, 1), asset_class="DEBT_MF"),
        _sell(pid, "INF123D01010", 100, 150, datetime.date(2024, 9, 1), asset_class="DEBT_MF"),
    ])
    db_session.flush()

    report = FIFOTaxEngine(db_session, pid).compute_tax_report()
    fy = _fy(report, "2024-25")
    assert fy["slab_taxable_gain"] == Decimal("5000.00")
    assert fy["total_tax"] == Decimal("0.00")
    assert report["total_tax_payable"] == Decimal("0.00")
    assert report["slab_taxable_gain"] == Decimal("5000.00")


def test_debt_mf_pre_2023_long_term_12_5_no_exemption(db_session):
    """Debt fund acquired before 01-Apr-2023, held > 36 months -> LTCG @12.5%, NO
    Rs.1.25L exemption (that is equity-only). Gain 200000 -> tax 25000."""
    pid = _pid()
    db_session.add_all([
        _buy(pid, "INF123D01010", 100, 1000, datetime.date(2020, 1, 1), asset_class="DEBT_MF"),
        _sell(pid, "INF123D01010", 100, 3000, datetime.date(2024, 9, 1), asset_class="DEBT_MF"),
    ])
    db_session.flush()

    report = FIFOTaxEngine(db_session, pid).compute_tax_report()
    fy = _fy(report, "2024-25")
    assert fy["noneq_ltcg_gain"] == Decimal("200000.00")
    assert fy["noneq_ltcg_tax"] == Decimal("25000.00")
    assert report["total_tax_payable"] == Decimal("25000.00")


def test_hybrid_mf_over_24_months_is_ltcg(db_session):
    """Hybrid/other fund acquired >= 01-Apr-2023, held > 24 months -> LTCG @12.5%.
    Gain 100000 -> tax 12500."""
    pid = _pid()
    db_session.add_all([
        _buy(pid, "INF456H01010", 100, 1000, datetime.date(2023, 5, 1), asset_class="HYBRID_MF"),
        _sell(pid, "INF456H01010", 100, 2000, datetime.date(2025, 6, 1), asset_class="HYBRID_MF"),
    ])
    db_session.flush()

    report = FIFOTaxEngine(db_session, pid).compute_tax_report()
    fy = _fy(report, "2025-26")
    assert fy["noneq_ltcg_tax"] == Decimal("12500.00")


def test_hybrid_mf_under_24_months_is_slab(db_session):
    """Hybrid fund held < 24 months -> slab (reported, no rupee tax)."""
    pid = _pid()
    db_session.add_all([
        _buy(pid, "INF456H01010", 100, 1000, datetime.date(2024, 1, 1), asset_class="HYBRID_MF"),
        _sell(pid, "INF456H01010", 100, 1500, datetime.date(2025, 1, 1), asset_class="HYBRID_MF"),
    ])
    db_session.flush()

    report = FIFOTaxEngine(db_session, pid).compute_tax_report()
    fy = _fy(report, "2024-25")
    assert fy["slab_taxable_gain"] == Decimal("50000.00")
    assert fy["total_tax"] == Decimal("0.00")


def test_equity_mf_taxed_like_equity(db_session):
    """Equity-oriented MF uses Sec 112A incl. the Rs.1.25L exemption (same as stocks).
    Gain 200000 -> taxable 75000 @12.5% = 9375."""
    pid = _pid()
    db_session.add_all([
        _buy(pid, "INF789E01010", 100, 1000, datetime.date(2022, 1, 1), asset_class="EQUITY_MF"),
        _sell(pid, "INF789E01010", 100, 3000, datetime.date(2024, 8, 1), asset_class="EQUITY_MF"),
    ])
    db_session.flush()

    report = FIFOTaxEngine(db_session, pid).compute_tax_report()
    assert report["total_tax_payable"] == Decimal("9375.00")
    assert report["slab_taxable_gain"] == Decimal("0.00")


def test_fund_classifier():
    from engine.ingestion.fund_classifier import (
        classify_asset_class, classify_fund_type, is_mutual_fund,
    )
    assert is_mutual_fund("INF204K01XYZ") is True
    assert is_mutual_fund("INE002A01018") is False
    assert is_mutual_fund("TCS.NS") is False

    assert classify_asset_class("TCS.NS") == "EQUITY"
    assert classify_asset_class("INE002A01018") == "EQUITY"
    assert classify_fund_type(scheme_name="HDFC Liquid Fund") == "DEBT_MF"
    assert classify_fund_type(scheme_name="ICICI Aggressive Hybrid Fund") == "HYBRID_MF"
    assert classify_fund_type(scheme_name="Nippon Gold Savings FoF") == "OTHER_MF"
    assert classify_fund_type(scheme_name="Axis Large Cap Fund") == "EQUITY_MF"
    assert classify_fund_type(scheme_category="Equity Scheme", scheme_name="Whatever") == "EQUITY_MF"
    assert classify_fund_type() == "EQUITY_MF"  # unknown defaults to equity


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
