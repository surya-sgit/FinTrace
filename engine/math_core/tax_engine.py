from decimal import Decimal
from datetime import date
from collections import deque
from typing import Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import asc

from domain.models import TransactionLedger

class FIFOTaxEngine:
    """
    Deterministic FIFO computation engine for Indian Equity Capital Gains.
    Strictly adheres to zero-float policies using python's decimal.Decimal.
    """

    # In India, equity holding period >= 365 days is Long Term
    LTCG_THRESHOLD_DAYS = 365

    def __init__(self, db_session: Session, portfolio_id: str):
        self.db = db_session
        self.portfolio_id = portfolio_id

    def compute_realized_gains(self) -> Dict[str, Any]:
        """
        Processes the entire immutable ledger chronologically.
        Returns aggregated STCG, LTCG, and the remaining unsold holdings (inventory).
        """
        # Fetch all transactions for this portfolio, strictly ordered by execution date
        transactions = self.db.query(TransactionLedger).filter(
            TransactionLedger.portfolio_id == self.portfolio_id
        ).order_by(
            asc(TransactionLedger.execution_date)
        ).all()

        # Group ledgers by ticker
        ledgers_by_ticker = {}
        for tx in transactions:
            if tx.ticker not in ledgers_by_ticker:
                ledgers_by_ticker[tx.ticker] = []
            ledgers_by_ticker[tx.ticker].append(tx)

        total_stcg = Decimal('0.0000')
        total_ltcg = Decimal('0.0000')
        unsold_inventory = {}

        for ticker, ledger in ledgers_by_ticker.items():
            # A queue to hold our "Unsold" Buy lots
            buy_queue = deque()

            for tx in ledger:
                if tx.transaction_type == "BUY":
                    # Push the lot into the queue
                    buy_queue.append({
                        'execution_date': tx.execution_date,
                        'remaining_quantity': Decimal(tx.quantity),
                        'price_per_unit': Decimal(tx.price_per_unit)
                    })

                elif tx.transaction_type == "SELL":
                    sell_qty_remaining = Decimal(tx.quantity)
                    sell_price = Decimal(tx.price_per_unit)

                    while sell_qty_remaining > Decimal('0.0000') and buy_queue:
                        oldest_buy = buy_queue[0]

                        # Determine how many shares we can match against this oldest lot
                        matched_qty = min(sell_qty_remaining, oldest_buy['remaining_quantity'])

                        # Calculate the profit for this specific matched chunk
                        buy_value = matched_qty * oldest_buy['price_per_unit']
                        sell_value = matched_qty * sell_price
                        gross_profit = sell_value - buy_value

                        # Determine Tax Bracket (Holding Period)
                        days_held = (tx.execution_date - oldest_buy['execution_date']).days

                        if days_held >= self.LTCG_THRESHOLD_DAYS:
                            total_ltcg += gross_profit
                        else:
                            total_stcg += gross_profit

                        # Deduct the matched shares from our running totals
                        sell_qty_remaining -= matched_qty
                        oldest_buy['remaining_quantity'] -= matched_qty

                        # If the oldest lot is completely sold, remove it from the queue
                        if oldest_buy['remaining_quantity'] == Decimal('0.0000'):
                            buy_queue.popleft()

                    # If we exhausted the buy queue but still have shares to sell,
                    # the ledger data is corrupted (selling shares that don't exist).
                    if sell_qty_remaining > Decimal('0.0000'):
                        raise ValueError(f"Ledger corruption: Attempted to sell {sell_qty_remaining} phantom shares of {ticker}.")

            # Store whatever is left in the queue as our current holdings
            current_holdings_qty = sum(lot['remaining_quantity'] for lot in buy_queue)
            if current_holdings_qty > Decimal('0.0000'):
                unsold_inventory[ticker] = current_holdings_qty

        return {
            "realized_stcg": total_stcg,
            "realized_ltcg": total_ltcg,
            "current_holdings": unsold_inventory
        }
