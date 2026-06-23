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
        from domain.models import CorporateActionEvent

        # Fetch all transactions for this portfolio
        transactions = self.db.query(TransactionLedger).filter(
            TransactionLedger.portfolio_id == self.portfolio_id
        ).order_by(
            asc(TransactionLedger.execution_date),
            asc(TransactionLedger.transaction_type)
        ).all()

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
            buy_queue = deque()
            
            # Group ledger by date
            tx_by_date = {}
            for tx in ledger:
                if tx.execution_date not in tx_by_date:
                    tx_by_date[tx.execution_date] = []
                tx_by_date[tx.execution_date].append(tx)

            ticker_splits = splits_map.get(ticker, {})
            
            all_dates = set(tx_by_date.keys())
            for d in ticker_splits.keys():
                all_dates.add(d)
                
            sorted_dates = sorted(list(all_dates))

            for current_date in sorted_dates:
                # Apply splits first
                if current_date in ticker_splits:
                    factor = ticker_splits[current_date]
                    for lot in buy_queue:
                        lot['remaining_quantity'] *= factor
                        lot['price_per_unit'] /= factor

                day_txs = tx_by_date.get(current_date, [])
                for tx in day_txs:
                    if tx.transaction_type == "BUY":
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

                            matched_qty = min(sell_qty_remaining, oldest_buy['remaining_quantity'])

                            buy_value = matched_qty * oldest_buy['price_per_unit']
                            sell_value = matched_qty * sell_price
                            gross_profit = sell_value - buy_value

                            days_held = (tx.execution_date - oldest_buy['execution_date']).days

                            if days_held >= self.LTCG_THRESHOLD_DAYS:
                                total_ltcg += gross_profit
                            else:
                                total_stcg += gross_profit

                            sell_qty_remaining -= matched_qty
                            oldest_buy['remaining_quantity'] -= matched_qty

                            if oldest_buy['remaining_quantity'] <= Decimal('0.0000'):
                                buy_queue.popleft()

                        if sell_qty_remaining > Decimal('0.0000'):
                            total_stcg += (sell_qty_remaining * sell_price)
                            sell_qty_remaining = Decimal('0.0000')

            current_holdings_qty = sum(lot['remaining_quantity'] for lot in buy_queue)
            if current_holdings_qty > Decimal('0.0000'):
                unsold_inventory[ticker] = current_holdings_qty

        return {
            "realized_stcg": total_stcg,
            "realized_ltcg": total_ltcg,
            "current_holdings": unsold_inventory
        }
