from datetime import date
from typing import List, Tuple, Dict
from decimal import Decimal
from sqlalchemy.orm import Session
import pyxirr

from domain.models import TransactionLedger
from engine.market_data.market_service import MarketDataService

class XIRREngine:
    """
    Computes the Extended Internal Rate of Return (XIRR) for a portfolio.
    Translates ledger transactions into a chronological cash flow array,
    evaluating current unsold holdings at today's market price.
    """

    def __init__(self, db_session: Session, portfolio_id: str):
        self.db = db_session
        self.portfolio_id = portfolio_id
        self.market_service = MarketDataService(db_session)

    def calculate_portfolio_xirr(self) -> Dict[str, any]:
        # 1. Fetch all transactions
        transactions = self.db.query(TransactionLedger).filter(
            TransactionLedger.portfolio_id == self.portfolio_id
        ).all()

        if not transactions:
            return {"xirr_percentage": 0.0, "total_invested": 0.0, "current_value": 0.0}

        dates: List[date] = []
        amounts: List[float] = []

        # Track current inventory to calculate terminal value
        holdings: Dict[str, Decimal] = {}
        total_invested = 0.0

        # 2. Process historical cash flows
        for tx in transactions:
            qty = Decimal(tx.quantity)
            price = Decimal(tx.price_per_unit)
            fees = Decimal(tx.brokerage_fees)

            if tx.ticker not in holdings:
                holdings[tx.ticker] = Decimal('0.0000')

            if tx.transaction_type == "BUY":
                # Outflow: Money leaves the account to buy the asset + pay fees
                cash_flow = -float((qty * price) + fees)
                dates.append(tx.execution_date)
                amounts.append(cash_flow)

                holdings[tx.ticker] += qty
                total_invested += abs(cash_flow)

            elif tx.transaction_type == "SELL":
                # Inflow: Money enters the account from the sale, minus fees
                cash_flow = float((qty * price) - fees)
                dates.append(tx.execution_date)
                amounts.append(cash_flow)

                holdings[tx.ticker] -= qty

            elif tx.transaction_type == "DIVIDEND":
                # Inflow: Pure cash received
                cash_flow = float(qty * price)
                dates.append(tx.execution_date)
                amounts.append(cash_flow)

        # 3. Process terminal cash flows (Simulated Sell of all remaining assets today)
        today = date.today()
        current_portfolio_value = 0.0

        for ticker, remaining_qty in holdings.items():
            if remaining_qty > Decimal('0.0000'):
                try:
                    # Fetch the latest available price from our local cache
                    latest_price = self.market_service.get_price(ticker, today)
                    asset_value = float(remaining_qty) * latest_price

                    # Log the simulated inflow
                    dates.append(today)
                    amounts.append(asset_value)

                    current_portfolio_value += asset_value
                except ValueError:
                    # If we have no market data, we must abort to prevent corrupted XIRR
                    raise ValueError(f"Missing terminal market data for {ticker}. Cannot compute XIRR.")

        # 4. Compute XIRR
        try:
            # pyxirr.xirr returns a decimal multiplier (e.g., 0.15 for 15%)
            computed_xirr = pyxirr.xirr(dates, amounts)

            # If the calculation fails to converge, pyxirr returns None
            if computed_xirr is None:
                xirr_percentage = 0.0
            else:
                xirr_percentage = computed_xirr * 100.0

        except Exception:
            xirr_percentage = 0.0

        return {
            "xirr_percentage": round(xirr_percentage, 2),
            "total_invested": round(total_invested, 2),
            "current_value": round(current_portfolio_value, 2)
        }
