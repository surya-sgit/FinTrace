from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, List, Optional
from sqlalchemy.orm import Session

from domain.models import TransactionLedger, PortfolioPositionSnapshot
from engine.market_data.market_service import MarketDataService

class PerformanceAttributionEngine:
    """
    Executes purely deterministic multi-vector performance attribution math
    for a targeted portfolio on a given date.
    Calculates Legacy Position Drift, Intraday Transaction Impact, and Corporate Action Shields.
    """
    
    def __init__(self, db_session: Session, portfolio_id: str):
        self.db = db_session
        self.portfolio_id = portfolio_id
        self.market_service = MarketDataService(db_session)
        
    def identify_top_drags(self, target_date: date) -> Dict:
        """
        Analyzes the portfolio on the target_date to break down the valuation variance contribution.
        Returns a sorted matrix of assets and their net contribution to the portfolio's daily drift.
        """
        yesterday = target_date - timedelta(days=1)
        
        legacy_positions: Dict[str, Decimal] = {}
        running_positions: Dict[str, Decimal] = {}
        intraday_trades: List[TransactionLedger] = []
        
        # 1. Attempt to fetch latest position snapshot strictly before target_date
        latest_snapshot = self.db.query(PortfolioPositionSnapshot).filter(
            PortfolioPositionSnapshot.portfolio_id == self.portfolio_id,
            PortfolioPositionSnapshot.snapshot_date <= yesterday
        ).order_by(PortfolioPositionSnapshot.snapshot_date.desc()).first()
        
        last_snapshot_date = None
        if latest_snapshot:
            last_snapshot_date = latest_snapshot.snapshot_date
            for ticker, qty_str in latest_snapshot.positions.items():
                qty = Decimal(qty_str)
                running_positions[ticker] = qty
                legacy_positions[ticker] = qty
        
        # 2. Fetch transactions after the snapshot, sorted chronologically
        tx_query = self.db.query(TransactionLedger).filter(
            TransactionLedger.portfolio_id == self.portfolio_id,
            TransactionLedger.execution_date <= target_date
        )
        if last_snapshot_date:
            tx_query = tx_query.filter(TransactionLedger.execution_date > last_snapshot_date)
            
        transactions = tx_query.order_by(TransactionLedger.execution_date.asc()).all()
        
        # Chronological processing to build Q_open and ensure ledger integrity
        for tx in transactions:
            ticker = tx.ticker
            if ticker not in running_positions:
                running_positions[ticker] = Decimal('0.0000')
                legacy_positions[ticker] = Decimal('0.0000')
                
            qty = Decimal(str(tx.quantity))
            
            # 1. Transaction Safety Check
            if tx.transaction_type == "BUY":
                running_positions[ticker] += qty
            elif tx.transaction_type == "SELL":
                running_positions[ticker] -= qty
                if running_positions[ticker] < Decimal('0.0000'):
                    raise ValueError(f"Transaction ledger corruption: Position for {ticker} dropped below 0.0000 on {tx.execution_date}.")
            
            # 2. Segregate legacy vs intraday
            if tx.execution_date < target_date:
                if tx.transaction_type == "BUY":
                    legacy_positions[ticker] += qty
                elif tx.transaction_type == "SELL":
                    legacy_positions[ticker] -= qty
            elif tx.execution_date == target_date:
                intraday_trades.append(tx)

        # Identify all tickers that need market data pricing
        relevant_tickers = set()
        for ticker, qty in legacy_positions.items():
            if qty > Decimal('0.0000'):
                relevant_tickers.add(ticker)
        for tx in intraday_trades:
            relevant_tickers.add(tx.ticker)
            
        # Fetch high-precision pricing snapshots in bulk
        relevant_tickers_list = list(relevant_tickers)
        bulk_prices = self.market_service.get_prices_bulk(relevant_tickers_list, [target_date, yesterday])
        
        prices_today = bulk_prices.get(target_date, {})
        prices_yesterday = bulk_prices.get(yesterday, {})
        
        for ticker in relevant_tickers_list:
            if ticker not in prices_today:
                raise ValueError(f"Missing market data for {ticker} on {target_date}. Cannot compute attribution.")
            if ticker not in prices_yesterday:
                raise ValueError(f"Missing market data for {ticker} on {yesterday}. Cannot compute attribution.")
                
            prices_today[ticker] = Decimal(str(prices_today[ticker]))
            prices_yesterday[ticker] = Decimal(str(prices_yesterday[ticker]))

        # Compute the mathematical vectors
        contribution_matrix = []
        
        for ticker in relevant_tickers:
            p_today = prices_today[ticker]
            p_yday = prices_yesterday[ticker]
            
            # Vector 1: Legacy Position Drift (V_Legacy)
            q_open = legacy_positions.get(ticker, Decimal('0.0000'))
            v_legacy = q_open * (p_today - p_yday)
            
            v_intraday = Decimal('0.0000')
            v_corporate = Decimal('0.0000')
            
            # Vectors 2 & 3: Intraday Impact and Corporate Shields
            ticker_trades = [tx for tx in intraday_trades if tx.ticker == ticker]
            for tx in ticker_trades:
                qty = Decimal(str(tx.quantity))
                exec_price = Decimal(str(tx.price_per_unit))
                
                if tx.transaction_type == "BUY":
                    v_intraday += qty * (p_today - exec_price)
                elif tx.transaction_type == "SELL":
                    v_intraday -= qty * (p_today - exec_price)
                elif tx.transaction_type == "DIVIDEND":
                    v_corporate += qty * exec_price
                    
            # Net Variance
            net_contribution = v_legacy + v_intraday + v_corporate
            
            contribution_matrix.append({
                "ticker": ticker,
                "shares_held": running_positions.get(ticker, Decimal('0.0000')),
                "legacy_drift": v_legacy,
                "intraday_impact": v_intraday,
                "corporate_shield": v_corporate,
                "net_contribution": net_contribution
            })
            
        # Clear Sorted Matrix Output (ascending by net_contribution)
        contribution_matrix.sort(key=lambda x: x["net_contribution"])
        
        primary_drag_ticker = None
        absolute_impact = Decimal('0.0000')
        
        if contribution_matrix and contribution_matrix[0]["net_contribution"] < 0:
            primary_drag_ticker = contribution_matrix[0]["ticker"]
            absolute_impact = abs(contribution_matrix[0]["net_contribution"])
            
        return {
            "analysis_date": target_date.isoformat(),
            "primary_drag_ticker": primary_drag_ticker,
            "absolute_impact": absolute_impact,
            "full_contribution_matrix": contribution_matrix
        }
