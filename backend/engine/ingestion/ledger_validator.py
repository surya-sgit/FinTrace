from decimal import Decimal
from typing import List, Dict, Any
from sqlalchemy.orm import Session

from domain import models, schemas

class LedgerValidator:
    """
    Simulates the ledger chronologically to prevent mathematically impossible "Phantom Shorts".
    Validates EOD (End of Day) balances to allow Intraday Short Selling.
    Split-Aware: Mathematically adjusts running quantities using Corporate Action Events
    before evaluating balances, preventing false validation errors on stock splits.
    """
    def __init__(self, db_session: Session):
        self.db = db_session

    def validate(self, existing_txs: List[Any], new_txs: List[schemas.TransactionCreate]):
        # 1. Combine into a simulated ledger
        simulated_ledger = []
        
        for tx in existing_txs:
            simulated_ledger.append({
                "ticker": tx.ticker,
                "type": tx.transaction_type,
                "quantity": tx.quantity,
                "date": tx.execution_date
            })

        for txn in new_txs:
            txn_type = txn.transaction_type.value if hasattr(txn.transaction_type, "value") else txn.transaction_type
            simulated_ledger.append({
                "ticker": txn.ticker.upper(),
                "type": txn_type,
                "quantity": txn.quantity,
                "date": txn.execution_date
            })

        # Sort chronologically by date.
        # Within the same date, order doesn't matter because we only check End of Day (EOD) balances.
        simulated_ledger.sort(key=lambda x: x["date"])

        # Group by date for EOD processing
        ledger_by_date = {}
        for event in simulated_ledger:
            d = event["date"]
            if d not in ledger_by_date:
                ledger_by_date[d] = []
            ledger_by_date[d].append(event)
            
        # Get unique tickers to fetch splits
        tickers = {event["ticker"] for event in simulated_ledger}
        
        # Pre-fetch all corporate actions for these tickers
        all_splits = self.db.query(models.CorporateActionEvent).filter(
            models.CorporateActionEvent.ticker.in_(tickers),
            models.CorporateActionEvent.action_type == "SPLIT"
        ).all()
        
        # Map splits: dict[ticker, dict[ex_date, adjustment_factor]]
        splits_map = {}
        for sp in all_splits:
            if sp.ticker not in splits_map:
                splits_map[sp.ticker] = {}
            splits_map[sp.ticker][sp.ex_date] = sp.adjustment_factor

        running_balances = {ticker: Decimal("0.0000") for ticker in tickers}
        
        sorted_dates = sorted(list(ledger_by_date.keys()))
        
        for current_date in sorted_dates:
            # First, check if any splits occur ON this date for our holdings.
            # Splits happen at market open, so multiply the balance before processing trades.
            for ticker in running_balances.keys():
                if ticker in splits_map and current_date in splits_map[ticker]:
                    factor = splits_map[ticker][current_date]
                    running_balances[ticker] = running_balances[ticker] * factor
            
            # Now process the day's transactions
            day_events = ledger_by_date[current_date]
            for event in day_events:
                ticker = event["ticker"]
                qty = Decimal(str(event["quantity"]))
                
                if event["type"] == "BUY":
                    running_balances[ticker] += qty
                elif event["type"] == "SELL":
                    running_balances[ticker] -= qty
            
            # --- END OF DAY (EOD) BALANCE VALIDATION ---
            # Intraday shorts are allowed as long as EOD balance >= 0
            for ticker, balance in running_balances.items():
                # Allow a tiny tolerance for floating point weirdness during splits
                if balance < Decimal("-0.0001"):
                    raise ValueError(
                        f"Ledger Integrity Error: End of Day short position detected for {ticker} "
                        f"on {current_date}. Intraday shorts must be squared off before market close. "
                        f"Closing balance: {balance}"
                    )
