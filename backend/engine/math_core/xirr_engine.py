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
        # 1. Fetch all transactions sorted by date to process chronologically
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
                "valuation_history": []
            }

        xirr_dates: List[date] = []
        xirr_amounts: List[float] = []

        # Quant tracking dictionaries
        holdings_qty: Dict[str, Decimal] = {}
        holdings_cost: Dict[str, Decimal] = {} # Total cost spent on remaining shares

        net_cash_flow = Decimal('0.0000')

        # 2. Process historical cash flows chronologically
        for tx in transactions:
            qty = Decimal(str(tx.quantity))
            price = Decimal(str(tx.price_per_unit))
            fees = Decimal(str(tx.brokerage_fees))

            if tx.ticker not in holdings_qty:
                holdings_qty[tx.ticker] = Decimal('0.0000')
                holdings_cost[tx.ticker] = Decimal('0.0000')

            if tx.transaction_type == "BUY":
                # Outflow: Cash leaves portfolio
                cash_flow_val = (qty * price) + fees
                net_cash_flow -= cash_flow_val

                xirr_dates.append(tx.execution_date)
                xirr_amounts.append(-float(cash_flow_val))

                holdings_qty[tx.ticker] += qty
                holdings_cost[tx.ticker] += cash_flow_val

            elif tx.transaction_type == "SELL":
                # Inflow: Cash enters portfolio
                cash_flow_val = (qty * price) - fees
                net_cash_flow += cash_flow_val

                xirr_dates.append(tx.execution_date)
                xirr_amounts.append(float(cash_flow_val))

                # Update cost basis proportionally to shares sold (FIFO/Average Cost hybrid assumption)
                if holdings_qty[tx.ticker] > 0:
                    avg_price_before_sell = holdings_cost[tx.ticker] / holdings_qty[tx.ticker]
                    holdings_cost[tx.ticker] -= (qty * avg_price_before_sell)

                holdings_qty[tx.ticker] -= qty

            elif tx.transaction_type == "DIVIDEND":
                # Inflow: Pure cash return
                cash_flow_val = qty * price
                net_cash_flow += cash_flow_val

                xirr_dates.append(tx.execution_date)
                xirr_amounts.append(float(cash_flow_val))

        # 3. Process terminal cash flows (Simulated sell off of remaining holdings today)
        today = date.today()
        current_portfolio_value = Decimal('0.0000')
        current_cost_basis = Decimal('0.0000')

        for ticker, remaining_qty in holdings_qty.items():
            if remaining_qty > Decimal('0.0000'):
                try:
                    # Fetch price from your market service cache
                    latest_price = Decimal(str(self.market_service.get_price(ticker, today)))
                    asset_value = remaining_qty * latest_price

                    # Append to copy arrays for XIRR mathematical calculation without mutating master ledger
                    xirr_dates.append(today)
                    xirr_amounts.append(float(asset_value))

                    current_portfolio_value += asset_value
                    current_cost_basis += holdings_cost[ticker]
                except ValueError:
                    # Missing terminal market data. Fallback to 0.00 so the report doesn't crash.
                    latest_price = Decimal('0.00')
                    asset_value = remaining_qty * latest_price

                    xirr_dates.append(today)
                    xirr_amounts.append(float(asset_value))

                    current_portfolio_value += asset_value
                    current_cost_basis += holdings_cost[ticker]

        # NEW: Build a clean historical timeline directly using the dates from the CSV transactions
        valuation_history = []
        running_cost = Decimal('0.0000')
        
        # Capture historical milestone dates from your ledger
        for tx in transactions:
            qty = Decimal(str(tx.quantity))
            price = Decimal(str(tx.price_per_unit))
            fees = Decimal(str(tx.brokerage_fees))
            
            if tx.transaction_type == "BUY":
                running_cost += (qty * price) + fees
            elif tx.transaction_type == "SELL":
                # Basic representation of reduction on transaction date
                running_cost -= (qty * price) - fees
                
            valuation_history.append({
                "date": tx.execution_date.isoformat(),
                "valuation": round(float(running_cost), 2)
            })

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
            "valuation_history": valuation_history
        }
