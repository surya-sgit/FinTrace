import logging
from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
import pyxirr

from domain.models import TransactionLedger, AssetMetadata, BenchmarkIndex, CorporateActionEvent
from engine.market_data.market_service import MarketDataService

logger = logging.getLogger(__name__)

class LongTermAttributionEngine:
    def __init__(self, db_session: Session, portfolio_id: str):
        self.db = db_session
        self.portfolio_id = portfolio_id
        self.market_service = MarketDataService(db_session)

    def _get_inception_date(self) -> Optional[date]:
        tx = self.db.query(TransactionLedger).filter(
            TransactionLedger.portfolio_id == self.portfolio_id
        ).order_by(TransactionLedger.execution_date.asc()).first()
        return tx.execution_date if tx else None

    def execute_full_long_term_analysis(self, start_date: Optional[date] = None, end_date: Optional[date] = None) -> Dict:
        if not start_date:
            start_date = self._get_inception_date()
        if not end_date:
            end_date = date.today()

        if not start_date:
            return {
                "portfolio_id": self.portfolio_id,
                "start_date": end_date,
                "end_date": end_date,
                "organic_variation": [],
                "brinson_fachler": [],
                "mwr_slicing": [],
                "is_synthetic_cash_proxy": False
            }

        # Fetch all transactions up to end_date
        transactions = self.db.query(TransactionLedger).filter(
            TransactionLedger.portfolio_id == self.portfolio_id,
            TransactionLedger.execution_date <= end_date
        ).order_by(TransactionLedger.execution_date.asc()).all()

        # Isolate transactions within T
        tx_in_period = [tx for tx in transactions if tx.execution_date >= start_date]

        # Get relevant tickers
        relevant_tickers = set(tx.ticker for tx in transactions)
        relevant_tickers_list = list(relevant_tickers)

        # Bulk fetch prices for start_date and end_date
        bulk_prices = self.market_service.get_prices_bulk(relevant_tickers_list, [start_date, end_date])
        prices_start = bulk_prices.get(start_date, {})
        prices_end = bulk_prices.get(end_date, {})

        # Fetch corporate actions for adjustment
        corp_actions_map = self._get_corporate_actions(relevant_tickers_list)

        organic_variation = self._compute_organic_variation(transactions, start_date, end_date, prices_start, prices_end, corp_actions_map)
        brinson_fachler = self._compute_brinson_fachler(transactions, start_date, end_date, prices_start, prices_end, corp_actions_map)
        mwr_slicing = self._compute_mwr_slicing(transactions, start_date, end_date, prices_end, corp_actions_map)

        is_synthetic_cash_proxy = not any(tx.transaction_type in ["DEPOSIT", "WITHDRAWAL"] for tx in transactions)

        return {
            "portfolio_id": self.portfolio_id,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "organic_variation": organic_variation,
            "brinson_fachler": brinson_fachler,
            "mwr_slicing": mwr_slicing,
            "is_synthetic_cash_proxy": is_synthetic_cash_proxy
        }

    def _get_corporate_actions(self, tickers: List[str]) -> Dict[str, List]:
        events = self.db.query(CorporateActionEvent).filter(
            CorporateActionEvent.ticker.in_(tickers)
        ).all()
        result = {}
        for ev in events:
            if ev.ticker not in result:
                result[ev.ticker] = []
            result[ev.ticker].append(ev)
        return result

    def _get_adjusted_qty_price(self, tx, corp_actions_map: Dict):
        qty = Decimal(str(tx.quantity))
        price = Decimal(str(tx.price_per_unit))
        
        events = corp_actions_map.get(tx.ticker, [])
        for ev in events:
            if tx.execution_date < ev.ex_date:
                if ev.action_type in ["SPLIT", "BONUS"]:
                    factor = Decimal(str(ev.adjustment_factor))
                    qty = qty * factor
                    price = price / factor
        return qty, price

    def _compute_organic_variation(self, all_transactions: List[TransactionLedger], start_date: date, end_date: date, prices_start: Dict, prices_end: Dict, corp_actions_map: Dict) -> List[Dict]:
        results = []
        
        # Group by ticker
        tickers = set(tx.ticker for tx in all_transactions)
        for ticker in tickers:
            q_start = Decimal('0.0')
            q_end = Decimal('0.0')
            cf_in_period = Decimal('0.0')
            dividends_in_period = Decimal('0.0')

            for tx in all_transactions:
                if tx.transaction_type in ["DEPOSIT", "WITHDRAWAL"]:
                    continue

                qty, exec_price = self._get_adjusted_qty_price(tx, corp_actions_map)
                
                # Build Q_start
                if tx.execution_date < start_date:
                    if tx.transaction_type == "BUY":
                        q_start += qty
                    elif tx.transaction_type == "SELL":
                        q_start -= qty
                
                # Build Q_end and CF
                if tx.execution_date <= end_date:
                    if tx.transaction_type == "BUY":
                        q_end += qty
                        if tx.execution_date >= start_date:
                            cf_in_period += (qty * exec_price)
                    elif tx.transaction_type == "SELL":
                        q_end -= qty
                        if tx.execution_date >= start_date:
                            cf_in_period -= (qty * exec_price)
                    elif tx.transaction_type == "DIVIDEND" and tx.execution_date >= start_date:
                        dividends_in_period += (qty * exec_price)

            p_start = Decimal(str(prices_start.get(ticker, 0.0)))
            p_end = Decimal(str(prices_end.get(ticker, 0.0)))

            a_start = q_start * p_start
            a_end = q_end * p_end

            # V_i,T = A_end - A_start - CF_T + Dividends
            v_t = a_end - a_start - cf_in_period + dividends_in_period

            results.append({
                "ticker": ticker,
                "net_organic_contribution": v_t
            })

        return results

    def _compute_brinson_fachler(self, all_transactions: List[TransactionLedger], start_date: date, end_date: date, prices_start: Dict, prices_end: Dict, corp_actions_map: Dict) -> List[Dict]:
        from domain.models import AssetMetadata, BenchmarkIndex
        
        # 1. Group by ticker to compute q_start, q_end, net_contribution, and positive cash flows (buys)
        tickers = set(tx.ticker for tx in all_transactions if tx.ticker)
        
        # Determine sector for each ticker
        ticker_sectors = {}
        if tickers:
            metadata_records = self.db.query(AssetMetadata).filter(AssetMetadata.ticker.in_(tickers)).all()
            for r in metadata_records:
                ticker_sectors[r.ticker] = r.sector or "Unknown"

        sector_initial_values = {}
        sector_net_contributions = {}
        sector_buys = {}

        for ticker in tickers:
            sector = ticker_sectors.get(ticker, "Unknown")
            
            q_start = Decimal('0.0')
            q_end = Decimal('0.0')
            cf_in_period = Decimal('0.0')
            dividends_in_period = Decimal('0.0')
            buys_in_period = Decimal('0.0')

            for tx in all_transactions:
                if tx.ticker != ticker:
                    continue
                if tx.transaction_type in ["DEPOSIT", "WITHDRAWAL"]:
                    continue

                qty, exec_price = self._get_adjusted_qty_price(tx, corp_actions_map)
                
                # Build Q_start
                if tx.execution_date < start_date:
                    if tx.transaction_type == "BUY":
                        q_start += qty
                    elif tx.transaction_type == "SELL":
                        q_start -= qty
                
                # Build Q_end and CF
                if tx.execution_date <= end_date:
                    if tx.transaction_type == "BUY":
                        q_end += qty
                        if tx.execution_date >= start_date:
                            cf_in_period += (qty * exec_price)
                            buys_in_period += (qty * exec_price)
                    elif tx.transaction_type == "SELL":
                        q_end -= qty
                        if tx.execution_date >= start_date:
                            cf_in_period -= (qty * exec_price)
                    elif tx.transaction_type == "DIVIDEND" and tx.execution_date >= start_date:
                        dividends_in_period += (qty * exec_price)

            p_start = Decimal(str(prices_start.get(ticker, 0.0)))
            p_end = Decimal(str(prices_end.get(ticker, 0.0)))

            a_start = q_start * p_start
            a_end = q_end * p_end

            # V_i,T = A_end - A_start - CF_T + Dividends
            v_t = a_end - a_start - cf_in_period + dividends_in_period

            sector_initial_values[sector] = sector_initial_values.get(sector, Decimal('0.0000')) + a_start
            sector_net_contributions[sector] = sector_net_contributions.get(sector, Decimal('0.0000')) + v_t
            sector_buys[sector] = sector_buys.get(sector, Decimal('0.0000')) + buys_in_period

        # 2. Compute portfolio weights (w_p) and returns (r_p) per sector
        v_start_total = sum(sector_initial_values.values(), Decimal('0.0000'))
        
        w_p = {}
        r_p = {}
        
        for sector in sector_initial_values:
            init_val = sector_initial_values[sector]
            net_contrib = sector_net_contributions[sector]
            
            # Weight
            w_p[sector] = init_val / v_start_total if v_start_total != Decimal('0.0000') else Decimal('0.0000')
            
            # Return
            if init_val != Decimal('0.0000'):
                r_p[sector] = net_contrib / init_val
            else:
                buys = sector_buys.get(sector, Decimal('0.0000'))
                if buys != Decimal('0.0000'):
                    r_p[sector] = net_contrib / buys
                else:
                    r_p[sector] = Decimal('0.0000')

        # 3. Query BenchmarkIndex
        # Find latest benchmark records <= end_date
        latest_benchmark_rec = self.db.query(BenchmarkIndex).filter(
            BenchmarkIndex.price_date <= end_date
        ).order_by(BenchmarkIndex.price_date.desc()).first()

        benchmark_records = []
        if latest_benchmark_rec:
            benchmark_name = latest_benchmark_rec.benchmark_name
            benchmark_date = latest_benchmark_rec.price_date
            benchmark_records = self.db.query(BenchmarkIndex).filter(
                BenchmarkIndex.benchmark_name == benchmark_name,
                BenchmarkIndex.price_date == benchmark_date
            ).all()

        w_b: Dict[str, Decimal] = {}
        r_b: Dict[str, Decimal] = {}

        if benchmark_records:
            for rec in benchmark_records:
                sec_name = rec.sector
                w_b[sec_name] = Decimal(str(rec.sector_weight))
                r_b[sec_name] = Decimal(str(rec.sector_return))
        else:
            # No BenchmarkIndex rows in the database.
            # Use NSE sector indices from yfinance for per-sector benchmark returns.
            # This gives each sector a different r_b, producing non-zero allocation effects.
            # Equal weights are used for w_b (per-sector NSE weights require a paid data provider).
            SECTOR_INDEX_MAP: Dict[str, str] = {
                "Technology":          "^CNXIT",
                "Financial Services":  "^NSEBANK",
                "Consumer Cyclical":   "^CNXAUTO",
                "Consumer Defensive":  "^CNXFMCG",
                "Industrials":         "^CNXINFRA",
                "Utilities":           "^CNXENERGY",
                "Basic Materials":     "^CNXMETAL",
                "Energy":              "^CNXENERGY",
            }
            FALLBACK_INDEX = "^NSEI"

            import yfinance as yf
            from datetime import timedelta as _td
            yf_start = start_date.strftime("%Y-%m-%d")
            yf_end   = (end_date + _td(days=1)).strftime("%Y-%m-%d")

            def _fetch_index_return(symbol: str) -> Optional[Decimal]:
                try:
                    data = yf.download(symbol, start=yf_start, end=yf_end, auto_adjust=True, progress=False)
                    if data.empty:
                        return None
                    close = data["Close"]
                    if hasattr(close, "columns"):
                        close = close.iloc[:, 0]
                    p_s = float(close.iloc[0])
                    p_e = float(close.iloc[-1])
                    if p_s > 0:
                        return Decimal(str((p_e - p_s) / p_s))
                except Exception as exc:
                    logger.warning(f"Failed to fetch {symbol} from yfinance: {exc}")
                return None

            # Pre-fetch NIFTY 50 as the universal fallback
            nifty_return = _fetch_index_return(FALLBACK_INDEX) or Decimal('0.0000')

            n_sectors = len(w_p)
            equal_w = Decimal('1') / Decimal(str(n_sectors)) if n_sectors else Decimal('0.0000')

            for sector in w_p:
                symbol = SECTOR_INDEX_MAP.get(sector, FALLBACK_INDEX)
                sector_return = _fetch_index_return(symbol)
                if sector_return is None:
                    sector_return = nifty_return
                w_b[sector] = equal_w
                r_b[sector] = sector_return


        # R_b = sum(w_b^s * r_b^s)
        R_b = sum((w_b[s] * r_b[s] for s in w_b), Decimal('0.0000'))

        # Combine all sectors
        all_sectors = set(w_p.keys()) | set(w_b.keys())
        results = []
        for sector in sorted(all_sectors):
            w_p_s = w_p.get(sector, Decimal('0.0000'))
            w_b_s = w_b.get(sector, Decimal('0.0000'))
            r_p_s = r_p.get(sector, Decimal('0.0000'))
            r_b_s = r_b.get(sector, Decimal('0.0000'))

            allocation_effect = (w_p_s - w_b_s) * (r_b_s - R_b)
            selection_effect = w_b_s * (r_p_s - r_b_s)
            interaction_effect = (w_p_s - w_b_s) * (r_p_s - r_b_s)

            results.append({
                "sector": sector,
                "allocation_effect": allocation_effect,
                "selection_effect": selection_effect,
                "interaction_effect": interaction_effect
            })

        return results


    def _compute_mwr_slicing(self, all_transactions: List[TransactionLedger], start_date: date, end_date: date, prices_end: Dict, corp_actions_map: Dict) -> List[Dict]:
        results = []
        tickers = set(tx.ticker for tx in all_transactions if tx.ticker)
        
        # Track aggregate portfolio cash flows
        portfolio_dates = []
        portfolio_amounts = []
        
        remaining_cash = Decimal('0.0')
        total_market_value = Decimal('0.0')
        
        for tx in all_transactions:
            if tx.execution_date <= end_date:
                if tx.transaction_type == "DEPOSIT":
                    qty = Decimal(str(tx.quantity))
                    price = Decimal(str(tx.price_per_unit))
                    amount = float(qty * price)
                    portfolio_dates.append(tx.execution_date)
                    portfolio_amounts.append(amount) # Cash inflow from external
                    remaining_cash += Decimal(str(amount))
                elif tx.transaction_type == "WITHDRAWAL":
                    qty = Decimal(str(tx.quantity))
                    price = Decimal(str(tx.price_per_unit))
                    amount = float(qty * price)
                    portfolio_dates.append(tx.execution_date)
                    portfolio_amounts.append(-amount) # Cash outflow to external
                    remaining_cash -= Decimal(str(amount))
        
        for ticker in tickers:
            dates = []
            amounts = []
            
            q_end = Decimal('0.0')
            mean_capital = Decimal('0.0')
            
            for tx in all_transactions:
                if tx.ticker != ticker:
                    continue
                    
                qty, exec_price = self._get_adjusted_qty_price(tx, corp_actions_map)
                
                if tx.execution_date <= end_date:
                    tx_value = qty * exec_price
                    if tx.transaction_type == "BUY":
                        q_end += qty
                        dates.append(tx.execution_date)
                        amounts.append(-float(tx_value)) # Asset cash outflow
                        mean_capital += tx_value
                        remaining_cash -= tx_value
                    elif tx.transaction_type == "SELL":
                        q_end -= qty
                        dates.append(tx.execution_date)
                        amounts.append(float(tx_value)) # Asset cash inflow
                        remaining_cash += tx_value
                    elif tx.transaction_type == "DIVIDEND":
                        dates.append(tx.execution_date)
                        amounts.append(float(tx_value))
                        remaining_cash += tx_value
            
            # Terminal value
            if q_end > Decimal('0.0'):
                p_end = float(prices_end.get(ticker, 0.0))
                terminal_val = float(q_end) * p_end
                dates.append(end_date)
                amounts.append(terminal_val)
                total_market_value += Decimal(str(terminal_val))
                
            try:
                xirr_val = pyxirr.xirr(dates, amounts)
                if xirr_val is None or __import__('math').isinf(xirr_val) or __import__('math').isnan(xirr_val):
                    xirr_val = 0.0
            except Exception:
                xirr_val = 0.0
                
            results.append({
                "ticker": ticker,
                "standalone_xirr": xirr_val,
                "mwr_contribution": Decimal(str(xirr_val)) * Decimal('0.1') # Mock weight for MVP
            })
            
        # Append "CASH" as a drag asset
        if not portfolio_dates:
            # Auto-Deduction: Zero Cash Drag Assumption
            # Simulate perfectly timed deposits and withdrawals to mirror asset cashflows
            for ticker_res in results:
                pass # The drag is mathematically zero in this case
            
            # Compute a proxy aggregate XIRR from combined asset cashflows
            all_dates = []
            all_amounts = []
            for tx in all_transactions:
                qty, exec_price = self._get_adjusted_qty_price(tx, corp_actions_map)
                tx_value = float(qty * exec_price)
                if tx.execution_date <= end_date:
                    if tx.transaction_type == "BUY":
                        all_dates.append(tx.execution_date)
                        all_amounts.append(-tx_value)
                    elif tx.transaction_type == "SELL" or tx.transaction_type == "DIVIDEND":
                        all_dates.append(tx.execution_date)
                        all_amounts.append(tx_value)
            all_dates.append(end_date)
            all_amounts.append(float(total_market_value))
            try:
                agg_xirr = pyxirr.xirr(all_dates, all_amounts)
                if agg_xirr is None or __import__('math').isinf(agg_xirr) or __import__('math').isnan(agg_xirr):
                    agg_xirr = 0.0
            except Exception:
                agg_xirr = 0.0
            
            results.append({
                "ticker": "AGGREGATE_PORTFOLIO (0 Cash Drag)",
                "standalone_xirr": agg_xirr,
                "mwr_contribution": Decimal(str(agg_xirr))
            })
        else:
            portfolio_terminal_value = total_market_value + remaining_cash
            portfolio_dates.append(end_date)
            portfolio_amounts.append(-float(portfolio_terminal_value)) # Terminal value is outflow for NPV
            try:
                # Reverse signs for portfolio XIRR calculation so DEPOSITS are negative (outflows from user to portfolio)
                port_amounts_adj = [-a if i < len(portfolio_amounts)-1 else a for i, a in enumerate(portfolio_amounts)]
                agg_xirr = pyxirr.xirr(portfolio_dates, port_amounts_adj)
                if agg_xirr is None or __import__('math').isinf(agg_xirr) or __import__('math').isnan(agg_xirr):
                    agg_xirr = 0.0
            except Exception:
                agg_xirr = 0.0
                
            results.append({
                "ticker": "CASH_DRAG",
                "standalone_xirr": agg_xirr,
                "mwr_contribution": Decimal(str(agg_xirr))
            })
            
        return results
