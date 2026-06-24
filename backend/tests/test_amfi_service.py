"""
Tests for the AMFI mutual-fund NAV service: NAVAll.txt parsing, category-driven
classification, and NAV caching into MarketPrice/AssetPrices (so existing valuation
consumers price MFs unchanged). The HTTP layer is mocked — no network.
"""

import os
import sys
import datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from domain.models import Base, MarketPrice, AssetPrices
from engine.market_data.amfi_service import AMFIService, parse_navall
from engine.market_data.market_service import MarketDataService
from engine.ingestion.fund_classifier import classify_fund_type


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"


engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


SAMPLE_NAVALL = """Scheme Code;ISIN Div Payout/ ISIN Growth;ISIN Div Reinvestment;Scheme Name;Net Asset Value;Date

Open Ended Schemes(Equity Scheme - Large Cap Fund)

Axis Mutual Fund

120503;INF846K01EW2;INF846K01EX0;Axis Bluechip Fund - Direct Plan - Growth;65.5000;24-Jun-2026

Open Ended Schemes(Debt Scheme - Liquid Fund)

HDFC Mutual Fund

119551;INF179KA1Z00;-;HDFC Liquid Fund - Growth;4800.2500;24-Jun-2026
"""


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


def test_parse_navall_extracts_isins_navs_and_category():
    schemes = parse_navall(SAMPLE_NAVALL)

    # Both ISIN columns of the equity fund resolve to the same scheme.
    assert "INF846K01EW2" in schemes and "INF846K01EX0" in schemes
    eq = schemes["INF846K01EW2"]
    assert eq["nav"] == Decimal("65.5000")
    assert "Equity Scheme" in eq["category"]

    debt = schemes["INF179KA1Z00"]
    assert debt["nav"] == Decimal("4800.2500")
    assert "Debt Scheme" in debt["category"]
    # The "-" reinvestment ISIN is not added.
    assert "-" not in schemes


def test_category_drives_classification():
    schemes = parse_navall(SAMPLE_NAVALL)
    eq = schemes["INF846K01EW2"]
    debt = schemes["INF179KA1Z00"]
    assert classify_fund_type(eq["category"], eq["scheme_name"]) == "EQUITY_MF"
    assert classify_fund_type(debt["category"], debt["scheme_name"]) == "DEBT_MF"


def test_fetch_and_cache_nav_populates_prices(db_session, monkeypatch):
    svc = AMFIService(db_session)
    monkeypatch.setattr(svc, "_fetch_navall_text", lambda: SAMPLE_NAVALL)

    nav = svc.fetch_and_cache_nav("INF846K01EW2")
    assert nav == Decimal("65.5000")

    mp = db_session.query(MarketPrice).filter(MarketPrice.ticker == "INF846K01EW2").first()
    assert mp is not None and mp.data_source == "AMFI"
    assert float(mp.current_price) == 65.5

    ap = db_session.query(AssetPrices).filter(AssetPrices.ticker == "INF846K01EW2").first()
    assert ap is not None
    assert ap.price_date == datetime.date(2026, 6, 24)

    # The existing valuation path resolves the NAV unchanged.
    price = MarketDataService(db_session).get_price("INF846K01EW2", datetime.date(2026, 6, 24))
    assert price == 65.5


def test_fetch_and_cache_nav_unknown_isin_returns_none(db_session, monkeypatch):
    svc = AMFIService(db_session)
    monkeypatch.setattr(svc, "_fetch_navall_text", lambda: SAMPLE_NAVALL)
    assert svc.fetch_and_cache_nav("INF000X00X00") is None
