"""
Cross-portfolio consolidation.

Aggregates every portfolio a user owns into a single net-worth view: exact summed
invested / current value / unrealised P&L, merged holdings, a capital-weighted blended
XIRR, and an Equity vs Mutual-Fund value split.

Reuses the existing per-portfolio engines (no new valuation logic):
  * ``XIRREngine.calculate_portfolio_xirr`` for invested / XIRR per portfolio;
  * ``FIFOTaxEngine.compute_realized_gains`` for current holdings (qty per ticker);
  * ``MarketDataService.get_price`` for the latest price/NAV (equities via yfinance
    cache, mutual funds via AMFI NAV — both already land in AssetPrices).
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from domain import models
from engine.math_core.xirr_engine import XIRREngine
from engine.math_core.tax_engine import FIFOTaxEngine
from engine.market_data.market_service import MarketDataService
from engine.math_core import tax_rules

logger = logging.getLogger(__name__)


class ConsolidationEngine:
    def __init__(self, db_session: Session, user_id):
        self.db = db_session
        self.user_id = user_id
        self.market_service = MarketDataService(db_session)

    def aggregate(self) -> Dict[str, Any]:
        portfolios = (
            self.db.query(models.Portfolio)
            .filter(models.Portfolio.user_id == self.user_id)
            .all()
        )

        total_invested = 0.0
        weighted_xirr_num = 0.0
        equity_value = 0.0
        mf_value = 0.0
        merged_holdings: Dict[str, float] = {}
        per_portfolio: List[Dict[str, Any]] = []
        today = date.today()

        for p in portfolios:
            try:
                xirr = XIRREngine(db_session=self.db, portfolio_id=p.id).calculate_portfolio_xirr()
            except Exception as e:
                logger.error(f"Consolidation: XIRR failed for portfolio {p.id}: {e}")
                continue

            invested = float(xirr.get("current_cost_basis", 0.0))
            xirr_pct = float(xirr.get("xirr_percentage", 0.0))

            # Value current holdings per ticker so we can split by asset class. Uses the
            # same price source and zero-fallback as the XIRR engine, so the split sums
            # to the same current value.
            ac_map = {
                t.ticker: (getattr(t, "asset_class", None) or "EQUITY")
                for t in self.db.query(models.TransactionLedger)
                .filter(models.TransactionLedger.portfolio_id == p.id)
                .all()
            }
            try:
                holdings = FIFOTaxEngine(self.db, p.id).compute_realized_gains()["current_holdings"]
            except Exception as e:
                logger.error(f"Consolidation: holdings failed for portfolio {p.id}: {e}")
                holdings = {}

            portfolio_current = 0.0
            for ticker, qty in holdings.items():
                qty_f = float(qty)
                try:
                    price = float(self.market_service.get_price(ticker, today))
                except Exception:
                    price = 0.0
                value = qty_f * price
                portfolio_current += value
                merged_holdings[ticker] = merged_holdings.get(ticker, 0.0) + qty_f
                if ac_map.get(ticker, "EQUITY") in tax_rules.EQUITY_TAX_CLASSES:
                    equity_value += value
                else:
                    mf_value += value

            total_invested += invested
            weighted_xirr_num += xirr_pct * invested
            per_portfolio.append({
                "portfolio_id": str(p.id),
                "name": p.name,
                "invested": round(invested, 2),
                "current_value": round(portfolio_current, 2),
                "xirr_percentage": round(xirr_pct, 2),
            })

        total_current = equity_value + mf_value
        blended_xirr = (weighted_xirr_num / total_invested) if total_invested > 0 else 0.0

        return {
            "total_net_worth": round(total_current, 2),
            "total_invested": round(total_invested, 2),
            "total_current_value": round(total_current, 2),
            "unrealized_pl": round(total_current - total_invested, 2),
            "blended_xirr": round(blended_xirr, 2),
            "equity_value": round(equity_value, 2),
            "mutual_fund_value": round(mf_value, 2),
            "portfolio_count": len(per_portfolio),
            "portfolios": per_portfolio,
        }
