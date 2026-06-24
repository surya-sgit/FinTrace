"""
Tests for ingesting Groww's mutual-fund order-history CSV: preamble skipping, the
PURCHASE/REDEEM transaction vocabulary, scheme-name identifiers, DD-Mon-YYYY dates,
and name-based fund classification.
"""

import os
import sys
import datetime
from decimal import Decimal

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.ingestion.parsers.csv_parser import BrokerCSVParser, _normalize_txn_type


GROWW_MF_CSV = """Personal Details
Name,abc
Mobile Number,0
PAN,ABCDE1234F


TRANSACTIONS FROM Jan 01 2021 TO Jun 24 2026


Scheme Name,Transaction Type,Units,NAV,Amount,Date

Mirae Asset Gold Silver Passive FoF Direct Growth,PURCHASE,28.17,17.75,499,16 Jan 2026
Bandhan Small Cap Fund Direct Growth,PURCHASE,9.78,51.14,499,04 Dec 2025
ICICI Prudential Technology Direct Plan Growth,REDEEM,24.43,223.31,5455,16 Sep 2025
UTI Nifty 50 Index Fund Direct Growth,PURCHASE,99.25,100.76,9999,18 Feb 2021
"""


def test_normalize_txn_type_handles_mf_vocabulary():
    assert _normalize_txn_type("PURCHASE") == "BUY"
    assert _normalize_txn_type("REDEEM") == "SELL"
    assert _normalize_txn_type("Redemption") == "SELL"
    assert _normalize_txn_type("SWITCH IN") == "BUY"
    assert _normalize_txn_type("SWITCH OUT") == "SELL"
    assert _normalize_txn_type("IDCW Payout") == "DIVIDEND"
    assert _normalize_txn_type("BUY") == "BUY"


def test_parse_groww_mf_export():
    txns = BrokerCSVParser().parse(GROWW_MF_CSV.encode("utf-8"))
    assert len(txns) == 4

    by_scheme = {t.ticker: t for t in txns}

    gold = by_scheme["Mirae Asset Gold Silver Passive FoF Direct Growth"]
    assert gold.transaction_type.value == "BUY"
    assert gold.quantity == Decimal("28.17")
    assert gold.price_per_unit == Decimal("17.75")
    assert gold.execution_date == datetime.date(2026, 1, 16)
    assert gold.asset_class == "OTHER_MF"   # Gold / FoF

    icici = by_scheme["ICICI Prudential Technology Direct Plan Growth"]
    assert icici.transaction_type.value == "SELL"   # REDEEM -> SELL (not DIVIDEND)
    assert icici.execution_date == datetime.date(2025, 9, 16)

    bandhan = by_scheme["Bandhan Small Cap Fund Direct Growth"]
    assert bandhan.asset_class == "EQUITY_MF"        # Small Cap -> equity

    uti = by_scheme["UTI Nifty 50 Index Fund Direct Growth"]
    assert uti.asset_class == "EQUITY_MF"            # Nifty 50 Index -> equity
    assert uti.transaction_type.value == "BUY"
