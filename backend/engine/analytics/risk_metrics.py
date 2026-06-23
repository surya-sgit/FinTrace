import logging
import math
from datetime import date, timedelta, datetime
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

import yfinance as yf
from sqlalchemy.orm import Session

from domain.models import AssetPrices, TransactionLedger, PortfolioRiskSnapshot

logger = logging.getLogger(__name__)

RISK_FREE_RATE_ANNUAL = 0.065
TRADING_DAYS_PER_YEAR = 252
NIFTY_SYMBOL = "^NSEI"
CACHE_TTL_HOURS = 24


def _flatten_close(data):
    if data.empty:
        return None
    close = data["Close"]
    if hasattr(close, "columns"):
        close = close.iloc[:, 0]
    return close


class RiskMetricsEngine:
    """
    Computes risk and performance metrics for a portfolio.

    Metrics:
      - Alpha & Beta vs NIFTY 50 (OLS regression on daily returns)
      - Maximum Drawdown
      - Annualised Volatility
      - Sharpe Ratio  (risk-free rate: 6.5% Indian T-bill)
      - Sortino Ratio (downside deviation)
      - Holding Period Analysis per ticker (FIFO lot matching)
    """

    def __init__(self, db_session: Session, portfolio_id: str):
        self.db = db_session
        self.portfolio_id = portfolio_id

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def compute(self, start_date: Optional[date] = None, end_date: Optional[date] = None) -> Dict:
        if end_date is None:
            end_date = date.today()
        if start_date is None:
            first_tx = (
                self.db.query(TransactionLedger)
                .filter(TransactionLedger.portfolio_id == self.portfolio_id)
                .order_by(TransactionLedger.execution_date.asc())
                .first()
            )
            start_date = first_tx.execution_date if first_tx else end_date

        # 1. Check for valid cached snapshot
        snapshot = self.db.query(PortfolioRiskSnapshot).filter_by(portfolio_id=self.portfolio_id).first()
        if snapshot:
            age = datetime.utcnow() - snapshot.computed_at
            # Use cache if not expired and dates match exactly
            if age < timedelta(hours=CACHE_TTL_HOURS) and snapshot.start_date == start_date and snapshot.end_date == end_date:
                logger.info(f"Using cached risk metrics for portfolio {self.portfolio_id}")
                return {
                    "portfolio_id": self.portfolio_id,
                    "start_date": snapshot.start_date.isoformat(),
                    "end_date": snapshot.end_date.isoformat(),
                    "alpha": float(snapshot.alpha),
                    "beta": float(snapshot.beta),
                    "max_drawdown": float(snapshot.max_drawdown),
                    "annualised_volatility": float(snapshot.annualised_volatility),
                    "sharpe_ratio": float(snapshot.sharpe_ratio),
                    "sortino_ratio": float(snapshot.sortino_ratio),
                    "holding_periods": snapshot.holding_periods,
                }

        transactions = (
            self.db.query(TransactionLedger)
            .filter(
                TransactionLedger.portfolio_id == self.portfolio_id,
                TransactionLedger.execution_date <= end_date,
            )
            .order_by(TransactionLedger.execution_date.asc())
            .all()
        )

        if not transactions:
            return self._empty_result(start_date, end_date)

        nav_series = self._build_daily_nav(transactions, start_date, end_date)

        if len(nav_series) < 2:
            return self._empty_result(start_date, end_date)

        portfolio_returns = self._daily_returns(nav_series)
        nifty_returns = self._fetch_nifty_returns(start_date, end_date)

        alpha, beta = self._compute_alpha_beta(portfolio_returns, nifty_returns)
        max_drawdown = self._compute_max_drawdown(nav_series)
        volatility = self._compute_annualised_volatility(portfolio_returns)
        sharpe = self._compute_sharpe(portfolio_returns, volatility)
        sortino = self._compute_sortino(portfolio_returns)
        holding_periods = self._compute_holding_periods(transactions, end_date)

        # 3. Save snapshot to cache
        if snapshot:
            snapshot.computed_at = datetime.utcnow()
            snapshot.start_date = start_date
            snapshot.end_date = end_date
            snapshot.alpha = Decimal(str(alpha))
            snapshot.beta = Decimal(str(beta))
            snapshot.max_drawdown = Decimal(str(max_drawdown))
            snapshot.annualised_volatility = Decimal(str(volatility))
            snapshot.sharpe_ratio = Decimal(str(sharpe))
            snapshot.sortino_ratio = Decimal(str(sortino))
            snapshot.holding_periods = holding_periods
        else:
            snapshot = PortfolioRiskSnapshot(
                portfolio_id=self.portfolio_id,
                computed_at=datetime.utcnow(),
                start_date=start_date,
                end_date=end_date,
                alpha=Decimal(str(alpha)),
                beta=Decimal(str(beta)),
                max_drawdown=Decimal(str(max_drawdown)),
                annualised_volatility=Decimal(str(volatility)),
                sharpe_ratio=Decimal(str(sharpe)),
                sortino_ratio=Decimal(str(sortino)),
                holding_periods=holding_periods,
            )
            self.db.add(snapshot)
        
        try:
            self.db.commit()
        except Exception as e:
            logger.warning(f"Failed to save risk snapshot to DB: {e}")
            self.db.rollback()

        return {
            "portfolio_id": self.portfolio_id,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "alpha": alpha,
            "beta": beta,
            "max_drawdown": max_drawdown,
            "annualised_volatility": volatility,
            "sharpe_ratio": sharpe,
            "sortino_ratio": sortino,
            "holding_periods": holding_periods,
        }


    # ------------------------------------------------------------------
    # NAV reconstruction
    # ------------------------------------------------------------------

    def _build_daily_nav(
        self,
        transactions: List[TransactionLedger],
        start_date: date,
        end_date: date,
    ) -> List[Tuple[date, float]]:
        tickers = {tx.ticker for tx in transactions if tx.ticker}

        trading_dates = (
            self.db.query(AssetPrices.price_date)
            .filter(
                AssetPrices.ticker.in_(tickers),
                AssetPrices.price_date >= start_date,
                AssetPrices.price_date <= end_date,
            )
            .group_by(AssetPrices.price_date)
            .order_by(AssetPrices.price_date.asc())
            .all()
        )
        trading_dates = [r.price_date for r in trading_dates]

        if not trading_dates:
            return []

        tx_by_date: Dict[date, list] = {}
        for tx in transactions:
            tx_by_date.setdefault(tx.execution_date, []).append(tx)

        positions: Dict[str, Decimal] = {}
        nav_series: List[Tuple[date, float]] = []
        pending_dates = sorted(tx_by_date.keys())
        pending_idx = 0

        for nav_date in trading_dates:
            while pending_idx < len(pending_dates) and pending_dates[pending_idx] <= nav_date:
                tx_date = pending_dates[pending_idx]
                for tx in tx_by_date.get(tx_date, []):
                    if tx.transaction_type in ("DEPOSIT", "WITHDRAWAL", "DIVIDEND"):
                        continue
                    qty = Decimal(str(tx.quantity))
                    ticker = tx.ticker.upper()
                    if tx.transaction_type == "BUY":
                        positions[ticker] = positions.get(ticker, Decimal("0")) + qty
                    elif tx.transaction_type == "SELL":
                        positions[ticker] = positions.get(ticker, Decimal("0")) - qty
                pending_idx += 1

            total_value = 0.0
            for ticker, qty in positions.items():
                if qty <= Decimal("0"):
                    continue
                price_rec = (
                    self.db.query(AssetPrices)
                    .filter(
                        AssetPrices.ticker == ticker,
                        AssetPrices.price_date <= nav_date,
                    )
                    .order_by(AssetPrices.price_date.desc())
                    .first()
                )
                if price_rec:
                    total_value += float(qty) * float(price_rec.adjusted_close)

            nav_series.append((nav_date, total_value))

        return nav_series

    # ------------------------------------------------------------------
    # Return series helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _daily_returns(nav_series: List[Tuple[date, float]]) -> List[float]:
        returns = []
        for i in range(1, len(nav_series)):
            prev = nav_series[i - 1][1]
            curr = nav_series[i][1]
            if prev > 0:
                returns.append((curr - prev) / prev)
        return returns

    def _fetch_nifty_returns(self, start_date: date, end_date: date) -> List[float]:
        try:
            data = yf.download(
                NIFTY_SYMBOL,
                start=start_date.strftime("%Y-%m-%d"),
                end=(end_date + timedelta(days=1)).strftime("%Y-%m-%d"),
                auto_adjust=True,
                progress=False,
            )
            close = _flatten_close(data)
            if close is None or len(close) < 2:
                return []
            vals = close.tolist()
            return [(vals[i] - vals[i - 1]) / vals[i - 1] for i in range(1, len(vals)) if vals[i - 1] > 0]
        except Exception as exc:
            logger.warning(f"Failed to fetch NIFTY 50 returns: {exc}")
            return []

    # ------------------------------------------------------------------
    # Metric computations
    # ------------------------------------------------------------------

    def _compute_alpha_beta(
        self,
        portfolio_returns: List[float],
        nifty_returns: List[float],
    ) -> Tuple[float, float]:
        n = min(len(portfolio_returns), len(nifty_returns))
        if n < 5:
            return 0.0, 1.0

        x = nifty_returns[:n]
        y = portfolio_returns[:n]
        mean_x = sum(x) / n
        mean_y = sum(y) / n

        cov_xy = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
        var_x = sum((x[i] - mean_x) ** 2 for i in range(n))

        if var_x == 0:
            return 0.0, 1.0

        beta = cov_xy / var_x
        alpha_daily = mean_y - beta * mean_x
        alpha_annual = (1 + alpha_daily) ** TRADING_DAYS_PER_YEAR - 1
        return round(alpha_annual, 6), round(beta, 6)

    @staticmethod
    def _compute_max_drawdown(nav_series: List[Tuple[date, float]]) -> float:
        if len(nav_series) < 2:
            return 0.0
        peak = nav_series[0][1]
        max_dd = 0.0
        for _, val in nav_series:
            if val > peak:
                peak = val
            if peak > 0:
                dd = (peak - val) / peak
                if dd > max_dd:
                    max_dd = dd
        return round(max_dd, 6)

    @staticmethod
    def _compute_annualised_volatility(returns: List[float]) -> float:
        if len(returns) < 2:
            return 0.0
        mean = sum(returns) / len(returns)
        variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
        return round(math.sqrt(variance) * math.sqrt(TRADING_DAYS_PER_YEAR), 6)

    @staticmethod
    def _compute_sharpe(returns: List[float], annualised_volatility: float) -> float:
        if len(returns) < 2 or annualised_volatility == 0:
            return 0.0
        mean_daily = sum(returns) / len(returns)
        annualised_return = (1 + mean_daily) ** TRADING_DAYS_PER_YEAR - 1
        excess_return = annualised_return - RISK_FREE_RATE_ANNUAL
        return round(excess_return / annualised_volatility, 4)

    @staticmethod
    def _compute_sortino(returns: List[float]) -> float:
        if len(returns) < 2:
            return 0.0
        rf_daily = RISK_FREE_RATE_ANNUAL / TRADING_DAYS_PER_YEAR
        downside = [min(r - rf_daily, 0) for r in returns]
        downside_var = sum(d ** 2 for d in downside) / len(downside)
        downside_std = math.sqrt(downside_var) * math.sqrt(TRADING_DAYS_PER_YEAR)
        if downside_std == 0:
            return 0.0
        mean_daily = sum(returns) / len(returns)
        annualised_return = (1 + mean_daily) ** TRADING_DAYS_PER_YEAR - 1
        return round((annualised_return - RISK_FREE_RATE_ANNUAL) / downside_std, 4)

    # ------------------------------------------------------------------
    # Holding period analysis (FIFO lot matching)
    # ------------------------------------------------------------------

    def _compute_holding_periods(
        self,
        transactions: List[TransactionLedger],
        as_of_date: date,
    ) -> List[Dict]:
        ticker_lots: Dict[str, List[Tuple[date, Decimal]]] = {}
        completed_days: Dict[str, List[int]] = {}

        for tx in sorted(transactions, key=lambda t: t.execution_date):
            ticker = tx.ticker
            if not ticker or tx.transaction_type in ("DEPOSIT", "WITHDRAWAL", "DIVIDEND"):
                continue
            qty = Decimal(str(tx.quantity))

            if tx.transaction_type == "BUY":
                ticker_lots.setdefault(ticker, []).append((tx.execution_date, qty))

            elif tx.transaction_type == "SELL":
                remaining = qty
                lots = ticker_lots.get(ticker, [])
                completed_days.setdefault(ticker, [])
                while remaining > 0 and lots:
                    buy_date, lot_qty = lots[0]
                    matched = min(lot_qty, remaining)
                    completed_days[ticker].append((tx.execution_date - buy_date).days)
                    remaining -= matched
                    if lot_qty > matched:
                        lots[0] = (buy_date, lot_qty - matched)
                    else:
                        lots.pop(0)

        results = []
        for ticker in sorted(set(ticker_lots) | set(completed_days)):
            open_lots = ticker_lots.get(ticker, [])
            closed = completed_days.get(ticker, [])
            open_days = [(as_of_date - buy_date).days for buy_date, _ in open_lots]
            all_days = closed + open_days
            if not all_days:
                continue
            open_qty = sum(float(q) for _, q in open_lots)
            results.append({
                "ticker": ticker,
                "avg_holding_days": round(sum(all_days) / len(all_days), 1),
                "max_holding_days": max(all_days),
                "open_position_qty": open_qty,
                "is_still_held": open_qty > 0,
            })

        return results

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _empty_result(start_date: date, end_date: date) -> Dict:
        return {
            "portfolio_id": "",
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "alpha": 0.0,
            "beta": 1.0,
            "max_drawdown": 0.0,
            "annualised_volatility": 0.0,
            "sharpe_ratio": 0.0,
            "sortino_ratio": 0.0,
            "holding_periods": [],
        }
