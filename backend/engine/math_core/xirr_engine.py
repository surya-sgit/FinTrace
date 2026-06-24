from datetime import date
from typing import List, Tuple, Dict
from decimal import Decimal
from sqlalchemy.orm import Session
import pyxirr

from domain.models import TransactionLedger
from engine.market_data.market_service import MarketDataService

class XIRREngine:
    """
    Computes the Extended Internal Rate of Return (XIRR) and verified portfolio metrics.
    Translates ledger transactions into an accurate chronological cash flow array,
    evaluating current unsold holdings at today's market price.
    """

    def __init__(self, db_session: Session, portfolio_id: str):
        self.db = db_session
        self.portfolio_id = portfolio_id
        self.market_service = MarketDataService(db_session)

    def calculate_portfolio_xirr(self) -> Dict[str, any]:
        # 1. Fetch all transactions sorted by date
        transactions = self.db.query(TransactionLedger).filter(
            TransactionLedger.portfolio_id == self.portfolio_id
        ).order_by(TransactionLedger.execution_date.asc(), TransactionLedger.transaction_type.asc()).all()

        if not transactions:
            return {
                "xirr_percentage": 0.0,
                "net_deployed_capital": 0.0,
                "current_cost_basis": 0.0,
                "current_value": 0.0,
                "unrealized_p_and_l": 0.0,
                "valuation_history": [],
                "holdings": []
            }

        from collections import deque
        from domain.models import CorporateActionEvent

        xirr_dates: List[date] = []
        xirr_amounts: List[float] = []

        # FIFO queues for each ticker: dict[ticker, deque[{'qty': Decimal, 'cost': Decimal}]]
        holdings_fifo: Dict[str, deque] = {}
        unique_tickers = {tx.ticker for tx in transactions}

        # Pre-fetch splits
        all_splits = self.db.query(CorporateActionEvent).filter(
            CorporateActionEvent.ticker.in_(unique_tickers),
            CorporateActionEvent.action_type == "SPLIT"
        ).order_by(CorporateActionEvent.ex_date.asc()).all()

        splits_map = {}
        for sp in all_splits:
            if sp.ticker not in splits_map:
                splits_map[sp.ticker] = {}
            splits_map[sp.ticker][sp.ex_date] = sp.adjustment_factor

        net_cash_flow = Decimal('0.0000')
        net_deployed_capital = Decimal('0.0000')

        # Group transactions by date to apply splits on the ex_date before processing trades
        tx_by_date = {}
        for tx in transactions:
            d = tx.execution_date
            if d not in tx_by_date:
                tx_by_date[d] = []
            tx_by_date[d].append(tx)

        # Collect all relevant dates (trade dates + split dates)
        all_dates = set(tx_by_date.keys())
        for sp in all_splits:
            all_dates.add(sp.ex_date)
        sorted_dates = sorted(list(all_dates))

        # We will build valuation_history accurately using FIFO
        valuation_history = []

        for current_date in sorted_dates:
            # 1. Apply Splits occurring on this date
            for ticker, queue in holdings_fifo.items():
                if ticker in splits_map and current_date in splits_map[ticker]:
                    factor = splits_map[ticker][current_date]
                    for lot in queue:
                        lot['qty'] *= factor
                        lot['cost'] /= factor

            # 2. Process transactions for this date
            day_txs = tx_by_date.get(current_date, [])
            for tx in day_txs:
                ticker = tx.ticker
                qty = Decimal(str(tx.quantity))
                price = Decimal(str(tx.price_per_unit))
                fees = Decimal(str(tx.brokerage_fees))

                if ticker not in holdings_fifo:
                    holdings_fifo[ticker] = deque()

                if tx.transaction_type == "BUY":
                    # Outflow: Cash leaves portfolio
                    cash_flow_val = (qty * price) + fees
                    net_cash_flow -= cash_flow_val
                    net_deployed_capital += cash_flow_val

                    xirr_dates.append(tx.execution_date)
                    xirr_amounts.append(-float(cash_flow_val))

                    # For "Invested Value" calculations (like Groww), fees are excluded from the unit cost
                    lot_cost = price
                    holdings_fifo[ticker].append({'qty': qty, 'cost': lot_cost})

                elif tx.transaction_type == "SELL":
                    # Inflow: Cash enters portfolio
                    cash_flow_val = (qty * price) - fees
                    net_cash_flow += cash_flow_val
                    net_deployed_capital -= cash_flow_val

                    xirr_dates.append(tx.execution_date)
                    xirr_amounts.append(float(cash_flow_val))

                    # FIFO Depletion
                    sell_qty = qty
                    queue = holdings_fifo[ticker]
                    while sell_qty > Decimal('0') and queue:
                        oldest_lot = queue[0]
                        matched_qty = min(sell_qty, oldest_lot['qty'])
                        
                        sell_qty -= matched_qty
                        oldest_lot['qty'] -= matched_qty
                        
                        if oldest_lot['qty'] <= Decimal('0'):
                            queue.popleft()

                elif tx.transaction_type == "DIVIDEND":
                    # Inflow: Pure cash return
                    cash_flow_val = qty * price
                    net_cash_flow += cash_flow_val

                    xirr_dates.append(tx.execution_date)
                    xirr_amounts.append(float(cash_flow_val))

            # Record end-of-day market value for history
            if day_txs:
                eod_market_value = Decimal('0.0000')
                for ticker, queue in holdings_fifo.items():
                    qty = sum(lot['qty'] for lot in queue)
                    if qty > Decimal('0.0000'):
                        try:
                            price = Decimal(str(self.market_service.get_price(ticker, current_date)))
                            eod_market_value += qty * price
                        except ValueError:
                            # If no price is available for that historical date, fallback to cost
                            cost = sum(lot['qty'] * lot['cost'] for lot in queue)
                            eod_market_value += cost
                
                valuation_history.append({
                    "date": current_date.isoformat(),
                    "valuation": round(float(eod_market_value), 2)
                })

        # 3. Process terminal cash flows (Simulated sell off of remaining holdings today)
        today = date.today()
        current_portfolio_value = Decimal('0.0000')
        current_cost_basis = Decimal('0.0000')

        # Per-ticker asset class for grouping equity vs mutual funds in allocation.
        ac_map = {tx.ticker: (getattr(tx, "asset_class", None) or "EQUITY") for tx in transactions}
        holdings_breakdown: List[dict] = []

        for ticker, queue in holdings_fifo.items():
            remaining_qty = sum(lot['qty'] for lot in queue)
            if remaining_qty > Decimal('0.0000'):
                # Calculate FIFO Cost Basis
                cost_basis = sum(lot['qty'] * lot['cost'] for lot in queue)
                current_cost_basis += cost_basis

                try:
                    # Fetch price from your market service cache
                    latest_price = Decimal(str(self.market_service.get_price(ticker, today)))
                    asset_value = remaining_qty * latest_price

                    # Append to copy arrays for XIRR mathematical calculation without mutating master ledger
                    xirr_dates.append(today)
                    xirr_amounts.append(float(asset_value))

                    current_portfolio_value += asset_value
                except ValueError:
                    # Missing terminal market data. Fallback to cost basis so allocation
                    # stays meaningful (rather than zeroing the holding out).
                    asset_value = cost_basis

                    xirr_dates.append(today)
                    xirr_amounts.append(float(asset_value))

                    current_portfolio_value += asset_value

                holdings_breakdown.append({
                    "ticker": ticker,
                    "quantity": round(float(remaining_qty), 4),
                    "market_value": round(float(asset_value), 2),
                    "asset_class": ac_map.get(ticker, "EQUITY"),
                })

        # Largest holdings first for a clean allocation chart.
        holdings_breakdown.sort(key=lambda h: h["market_value"], reverse=True)

        # Append today's final terminal value as the last point
        valuation_history.append({
            "date": today.isoformat(),
            "valuation": round(float(current_portfolio_value), 2)
        })

        # 4. Compute accurate math-convergent XIRR
        try:
            computed_xirr = pyxirr.xirr(xirr_dates, xirr_amounts)
            xirr_percentage = computed_xirr * 100.0 if computed_xirr is not None else 0.0
        except Exception:
            xirr_percentage = 0.0

        # Net Deployed Capital is the cumulative net money added to the system
        # If negative, it means more money was put in than taken out via sells/dividends
        net_deployed = abs(net_cash_flow) if net_cash_flow < 0 else Decimal('0.0000')
        unrealized_pl = current_portfolio_value - current_cost_basis

        return {
            "xirr_percentage": round(float(xirr_percentage), 2),
            "net_deployed_capital": round(float(net_deployed), 2),
            "current_cost_basis": round(float(current_cost_basis), 2),
            "current_value": round(float(current_portfolio_value), 2),
            "unrealized_p_and_l": round(float(unrealized_pl), 2),
            "valuation_history": valuation_history,
            "holdings": holdings_breakdown
        }
