"""
Classify a holding's asset class for tax routing.

Two stages:
  1. ``classify_asset_class(ticker)`` — coarse: is this an equity instrument or a
     mutual fund? Indian MF ISINs start with ``INF``; equity company ISINs start with
     ``INE``; exchange-suffixed tickers (``TCS.NS``) are equities.
  2. ``classify_fund_type(scheme_category, scheme_name)`` — for mutual funds, refine
     into the tax buckets EQUITY_MF / DEBT_MF / HYBRID_MF / OTHER_MF using AMFI's
     scheme category when available, falling back to scheme-name heuristics.

Both are pure functions so they are trivially unit-tested without any network/DB.
"""

from __future__ import annotations

from typing import Optional

# Tax-relevant asset classes (also stored on TransactionLedger.asset_class).
EQUITY = "EQUITY"
EQUITY_MF = "EQUITY_MF"
DEBT_MF = "DEBT_MF"
HYBRID_MF = "HYBRID_MF"
OTHER_MF = "OTHER_MF"

MUTUAL_FUND_CLASSES = {EQUITY_MF, DEBT_MF, HYBRID_MF, OTHER_MF}


def is_mutual_fund(ticker: str) -> bool:
    """True if the identifier looks like an Indian mutual-fund ISIN (``INF...``)."""
    if not ticker:
        return False
    return ticker.strip().upper().startswith("INF")


# Scheme-name keyword heuristics, checked in priority order. Debt/hybrid keywords are
# matched before defaulting an unknown fund to equity-oriented.
_DEBT_KEYWORDS = (
    "LIQUID", "DEBT", "GILT", "BOND", "MONEY MARKET", "OVERNIGHT", "ULTRA SHORT",
    "SHORT DURATION", "LOW DURATION", "CORPORATE BOND", "CREDIT RISK", "BANKING AND PSU",
    "DYNAMIC BOND", "FLOATER", "INCOME", "FIXED MATURITY", "FMP", "TREASURY",
)
_HYBRID_KEYWORDS = (
    "HYBRID", "BALANCED", "ARBITRAGE", "MULTI ASSET", "MULTI-ASSET", "ASSET ALLOCATION",
    "EQUITY SAVINGS", "CONSERVATIVE", "AGGRESSIVE HYBRID",
)
_OTHER_KEYWORDS = (
    "GOLD", "SILVER", "INTERNATIONAL", "GLOBAL", "US ", "NASDAQ", "OVERSEAS",
    "FUND OF FUND", "FUND OF FUNDS", "FOF", "COMMODITY",
)
_EQUITY_KEYWORDS = (
    "EQUITY", "ELSS", "TAX SAVER", "FLEXI CAP", "FLEXICAP", "LARGE CAP", "MID CAP",
    "SMALL CAP", "MULTI CAP", "MULTICAP", "BLUECHIP", "BLUE CHIP", "FOCUSED", "INDEX",
    "NIFTY", "SENSEX", "VALUE", "DIVIDEND YIELD", "CONTRA", "SECTORAL", "THEMATIC",
)


def classify_fund_type(scheme_category: Optional[str] = None, scheme_name: Optional[str] = None) -> str:
    """Map an MF to a tax bucket using AMFI category first, then name heuristics.

    Defaults to EQUITY_MF when nothing is recognisable (most MFs by AUM are equity, and
    the assumed class is surfaced in the report so users can correct it).
    """
    text = f"{scheme_category or ''} {scheme_name or ''}".upper()

    if not text.strip():
        return EQUITY_MF

    # Hybrid is checked before debt/equity because names often contain both words.
    if any(k in text for k in _HYBRID_KEYWORDS):
        return HYBRID_MF
    if any(k in text for k in _OTHER_KEYWORDS):
        return OTHER_MF
    if any(k in text for k in _DEBT_KEYWORDS):
        return DEBT_MF
    if any(k in text for k in _EQUITY_KEYWORDS):
        return EQUITY_MF

    return EQUITY_MF


def classify_asset_class(
    ticker: str,
    scheme_category: Optional[str] = None,
    scheme_name: Optional[str] = None,
) -> str:
    """Full classification: EQUITY for stocks, or an MF tax bucket for ``INF`` ISINs."""
    if is_mutual_fund(ticker):
        return classify_fund_type(scheme_category, scheme_name)
    return EQUITY
