"""
AMFI mutual-fund NAV service.

AMFI publishes the latest NAV of every Indian mutual fund as a single semicolon-
delimited file (``NAVAll.txt``). We parse it to:
  * price mutual-fund holdings (NAV -> MarketPrice + AssetPrices, so the existing
    XIRR / holdings / risk consumers value MFs unchanged via ``get_price``); and
  * read each scheme's CATEGORY (the section headers in the file, e.g.
    "Open Ended Schemes(Equity Scheme - Large Cap Fund)") to classify a fund as
    equity / debt / hybrid / other for tax routing.

Network access is isolated in ``_fetch_navall_text`` and fully guarded, so failures
degrade gracefully (no NAV cached, classification falls back to the default). Unit
tests exercise the pure ``parse_navall`` parser and mock the HTTP layer.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Dict, Optional

from sqlalchemy.orm import Session

from domain.models import MarketPrice, AssetPrices

logger = logging.getLogger(__name__)

AMFI_NAVALL_URL = "https://www.amfiindia.com/spages/NAVAll.txt"


def parse_navall(text: str) -> Dict[str, dict]:
    """Parse AMFI ``NAVAll.txt`` into ``{ISIN: {scheme_code, scheme_name, nav,
    nav_date, category}}``. Pure function — no I/O.

    The file interleaves three line shapes:
      * section/category headers (no ``;``), e.g. "Open Ended Schemes(Debt Scheme...)"
      * AMC names (no ``;``)
      * NAV rows: ``Code;ISIN Growth;ISIN Reinvest;Name;NAV;Date``
    Both ISIN columns map to the same scheme; a holder's ISIN may be either.
    """
    schemes: Dict[str, dict] = {}
    current_category: Optional[str] = None

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue

        if ";" not in line:
            # Category headers mention "Scheme"; AMC names do not.
            if "scheme" in line.lower():
                current_category = line
            continue

        parts = line.split(";")
        if len(parts) < 6:
            continue
        code, isin_growth, isin_reinv, name, nav_str, nav_date = (p.strip() for p in parts[:6])

        if code.lower() == "scheme code":  # the header row
            continue
        try:
            nav_val = Decimal(nav_str)
        except (InvalidOperation, ValueError):
            continue

        entry = {
            "scheme_code": code,
            "scheme_name": name,
            "nav": nav_val,
            "nav_date": nav_date,
            "category": current_category,
        }
        for isin in (isin_growth, isin_reinv):
            iu = isin.upper()
            if iu.startswith("INF"):
                schemes[iu] = entry

    return schemes


class AMFIService:
    def __init__(self, db_session: Session):
        self.db = db_session
        self._master: Optional[Dict[str, dict]] = None

    # ---------------------------------------------------------------- network

    def _fetch_navall_text(self) -> str:
        import httpx

        resp = httpx.get(AMFI_NAVALL_URL, timeout=30.0)
        resp.raise_for_status()
        return resp.text

    def load_master(self, force: bool = False) -> Dict[str, dict]:
        """Fetch + parse the scheme master once per service instance (cached)."""
        if self._master is not None and not force:
            return self._master
        try:
            self._master = parse_navall(self._fetch_navall_text())
        except Exception as e:
            logger.error(f"Failed to load AMFI NAV master: {e}", exc_info=True)
            self._master = {}
        return self._master

    # ------------------------------------------------------------- accessors

    def get_scheme(self, isin: str) -> Optional[dict]:
        return self.load_master().get(isin.strip().upper())

    def get_category(self, isin: str) -> Optional[str]:
        scheme = self.get_scheme(isin)
        return scheme.get("category") if scheme else None

    # --------------------------------------------------------------- caching

    def fetch_and_cache_nav(self, isin: str) -> Optional[Decimal]:
        """Upsert the latest NAV for an ISIN into MarketPrice and AssetPrices so the
        existing valuation consumers price the fund unchanged. Returns the NAV or None.
        """
        isin = isin.strip().upper()
        scheme = self.get_scheme(isin)
        if not scheme:
            logger.info(f"No AMFI scheme found for ISIN {isin}")
            return None

        nav = scheme["nav"]
        try:
            nav_date = datetime.strptime(scheme["nav_date"], "%d-%b-%Y").date()
        except (ValueError, KeyError):
            nav_date = date.today()

        # Latest price (MarketPrice, PK = ticker/isin)
        mp = self.db.query(MarketPrice).filter(MarketPrice.ticker == isin).first()
        if mp:
            mp.current_price = float(nav)
            mp.data_source = "AMFI"
        else:
            self.db.add(MarketPrice(ticker=isin, current_price=float(nav), data_source="AMFI"))

        # Historical point (AssetPrices) so get_price(isin, today) resolves the NAV.
        existing = self.db.query(AssetPrices).filter(
            AssetPrices.ticker == isin, AssetPrices.price_date == nav_date
        ).first()
        if not existing:
            self.db.add(AssetPrices(
                ticker=isin, price_date=nav_date,
                open_price=nav, high_price=nav, low_price=nav,
                close_price=nav, adjusted_close=nav, volume=0,
            ))

        self.db.commit()
        return nav
