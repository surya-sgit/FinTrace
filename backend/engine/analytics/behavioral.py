from typing import Dict, List, Tuple
from decimal import Decimal
from datetime import date, datetime
import pandas as pd
import numpy as np
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert

from domain.models import TransactionLedger, BehavioralAnalysisSnapshot, AssetPrices
from engine.market_data.market_service import MarketDataService

class BehavioralAnalyticsEngine:
    """
    Computes psychological trading biases:
    - Disposition Effect: Holding losers longer than winners.
    - Momentum Bias: Buying at overbought levels (RSI > 70).
    """

    BENCHMARK_TICKER = "^NSEI"  # NIFTY 50

    def __init__(self, db_session: Session, portfolio_id: str):
        self.db = db_session
        self.portfolio_id = portfolio_id
        self.market_service = MarketDataService(db_session)

    def _compute_rsi(self, series: pd.Series, window: int = 14) -> pd.Series:
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    def _compute_macd(self, series: pd.Series) -> pd.Series:
        exp1 = series.ewm(span=12, adjust=False).mean()
        exp2 = series.ewm(span=26, adjust=False).mean()
        macd = exp1 - exp2
        # Signal is 9-day EMA of MACD
        signal = macd.ewm(span=9, adjust=False).mean()
        # Histogram is MACD - Signal
        return macd - signal

    def run_analysis(self) -> None:
        transactions = self.db.query(TransactionLedger).filter(
            TransactionLedger.portfolio_id == self.portfolio_id
        ).order_by(TransactionLedger.execution_date.asc(), TransactionLedger.transaction_type.asc()).all()

        if not transactions:
            return

        earliest_date = transactions[0].execution_date
        today = date.today()

        # 1. Fetch Benchmark Data
        self.market_service.fetch_historical_prices(self.BENCHMARK_TICKER, earliest_date, today)
        benchmark_prices = self.db.query(AssetPrices).filter(
            AssetPrices.ticker == self.BENCHMARK_TICKER,
            AssetPrices.price_date >= earliest_date,
            AssetPrices.price_date <= today
        ).order_by(AssetPrices.price_date.asc()).all()

        bench_df = pd.DataFrame([{
            'date': p.price_date,
            'price': float(p.adjusted_close)
        } for p in benchmark_prices]).set_index('date')

        def get_bench_return(start_d: date, end_d: date) -> float:
            if bench_df.empty: return 0.0
            # Find closest dates
            s_idx = bench_df.index.get_indexer([start_d], method='nearest')[0]
            e_idx = bench_df.index.get_indexer([end_d], method='nearest')[0]
            if s_idx == -1 or e_idx == -1: return 0.0
            p1 = bench_df.iloc[s_idx]['price']
            p2 = bench_df.iloc[e_idx]['price']
            return (p2 - p1) / p1 if p1 > 0 else 0.0

        # 2. Extract uniquely traded tickers
        tickers = list(set([tx.ticker for tx in transactions]))
        prices_df_map = {}

        # Load all cached prices for these tickers
        for ticker in tickers:
            prices = self.db.query(AssetPrices).filter(
                AssetPrices.ticker == ticker
            ).order_by(AssetPrices.price_date.asc()).all()
            
            if prices:
                df = pd.DataFrame([{
                    'date': p.price_date,
                    'price': float(p.adjusted_close)
                } for p in prices]).set_index('date')
                
                # Compute Indicators natively!
                df['RSI_14'] = self._compute_rsi(df['price'])
                df['MACD_Hist'] = self._compute_macd(df['price'])
                prices_df_map[ticker] = df

        # 3. Analyze Trades (FIFO matching to find closed loops)
        holdings = {}
        closed_trades = []
        momentum_buys = 0
        total_buys = 0
        revenge_trade_count = 0
        panic_sell_count = 0
        endowment_trap_count = 0
        total_buys_value = 0.0
        total_sold_value = 0.0
        dividend_trap_count = 0
        dividends_received = {}
        buy_events = []
        bandwagon_bias_count = 0
        boredom_trade_count = 0
        overconfidence_bias_count = 0

        for tx in transactions:
            t = tx.ticker
            qty = float(tx.quantity)
            price = float(tx.price_per_unit)
            d = tx.execution_date

            if t not in holdings:
                holdings[t] = []

            # Check momentum at buy
            if tx.transaction_type == 'BUY':
                total_buys += 1
                buy_val = qty * price
                total_buys_value += buy_val
                
                df = prices_df_map.get(t)
                rsi_val = None
                if df is not None and not df.empty:
                    idx = df.index.get_indexer([d], method='nearest')[0]
                    if idx != -1:
                        rsi_val = df.iloc[idx].get('RSI_14')
                        if pd.notna(rsi_val) and rsi_val > 70:
                            momentum_buys += 1

                # Bandwagon Bias Check: Bought 3+ distinct tickers in 7 days
                buy_events.append({'date': d, 'ticker': t})
                recent_buys = set([b['ticker'] for b in buy_events if (d - b['date']).days <= 7])
                if len(recent_buys) >= 3:
                    bandwagon_bias_count += 1
                    buy_events = []  # Reset to prevent spamming

                # Overconfidence Bias Check: Bet size > 2x historical average after a massive win
                avg_historical_buy = (total_buys_value - buy_val) / (total_buys - 1) if total_buys > 1 else 0
                if avg_historical_buy > 0 and buy_val > 2 * avg_historical_buy:
                    recent_huge_wins = [
                        ct for ct in closed_trades
                        if ct['alpha'] > 0.20 and ct['trade_ret'] > 0.20 and (d - datetime.strptime(ct['sell_date'], '%Y-%m-%d').date()).days <= 10
                    ]
                    if recent_huge_wins:
                        overconfidence_bias_count += 1

                # Boredom Trading Check (BUY)
                if not bench_df.empty:
                    b_idx = bench_df.index.get_indexer([d], method='nearest')[0]
                    if b_idx >= 14:
                        p_curr = bench_df.iloc[b_idx]['price']
                        p_old = bench_df.iloc[b_idx - 14]['price']
                        if p_old > 0 and abs((p_curr - p_old) / p_old) < 0.01:
                            boredom_trade_count += 1

                # Endowment Trap Check: Buying 10% below current average cost
                if holdings[t]:
                    tot_qty = sum(lot['qty'] for lot in holdings[t])
                    tot_val = sum(lot['qty'] * lot['price'] for lot in holdings[t])
                    if tot_qty > 0:
                        avg_cost = tot_val / tot_qty
                        if price < avg_cost * 0.90:
                            endowment_trap_count += 1
                
                # Revenge Trade Check: Buying within 5 days of a loser sell
                recent_loser_sells = [
                    ct for ct in closed_trades 
                    if ct['ticker'] == t and ct['alpha'] < 0 and (d - datetime.strptime(ct['sell_date'], '%Y-%m-%d').date()).days <= 5
                ]
                if recent_loser_sells:
                    revenge_trade_count += 1

                holdings[t].append({'qty': qty, 'price': price, 'date': d, 'rsi': rsi_val})
                
            elif tx.transaction_type == 'SELL':
                sell_qty = qty
                total_sold_value += qty * price
                
                # Boredom Trading Check (SELL)
                if not bench_df.empty:
                    b_idx = bench_df.index.get_indexer([d], method='nearest')[0]
                    if b_idx >= 14:
                        p_curr = bench_df.iloc[b_idx]['price']
                        p_old = bench_df.iloc[b_idx - 14]['price']
                        if p_old > 0 and abs((p_curr - p_old) / p_old) < 0.01:
                            boredom_trade_count += 1
                            
                while sell_qty > 0 and holdings[t]:
                    oldest = holdings[t][0]
                    matched = min(oldest['qty'], sell_qty)
                    
                    # Record the closed trade
                    days_held = (d - oldest['date']).days
                    if days_held > 0:
                        trade_ret = (price - oldest['price']) / oldest['price']
                        bench_ret = get_bench_return(oldest['date'], d)
                        alpha = trade_ret - bench_ret
                        buy_val_trade = matched * oldest['price']
                        
                        closed_trades.append({
                            'ticker': t,
                            'days_held': days_held,
                            'alpha': alpha,
                            'buy_date': str(oldest['date']),
                            'sell_date': str(d),
                            'trade_ret': trade_ret,
                            'bench_ret': bench_ret,
                            'capital_invested': float(buy_val_trade)
                        })

                        # Panic Sell Check: Sold a loser on a day NIFTY dropped > 1.5%
                        if trade_ret < 0 and not bench_df.empty:
                            b_idx = bench_df.index.get_indexer([d], method='nearest')[0]
                            if b_idx > 0:
                                prev_p = bench_df.iloc[b_idx - 1]['price']
                                curr_p = bench_df.iloc[b_idx]['price']
                                if prev_p > 0:
                                    daily_bench_ret = (curr_p - prev_p) / prev_p
                                    if daily_bench_ret < -0.015:
                                        panic_sell_count += 1
                                        
                        # Dividend Trap Check
                        if trade_ret < 0:
                            loss_amount = matched * (oldest['price'] - price)
                            divs = dividends_received.get(t, 0.0)
                            if divs > 0 and loss_amount > divs:
                                dividend_trap_count += 1
                                dividends_received[t] = 0.0  # Clear to avoid double counting

                    oldest['qty'] -= matched
                    sell_qty -= matched
                    if oldest['qty'] <= 0:
                        holdings[t].pop(0)
            
            elif tx.transaction_type == 'DIVIDEND':
                dividends_received[t] = dividends_received.get(t, 0.0) + (qty * price)

        # 4. Calculate Aggregate Metrics
        winner_days = []
        loser_days = []
        winner_capital = []
        loser_capital = []
        days_held_list = []

        for ct in closed_trades:
            days_held_list.append(ct['days_held'])
            if ct['alpha'] > 0:
                winner_days.append(ct['days_held'])
                winner_capital.append(ct.get('capital_invested', 0.0))
            else:
                loser_days.append(ct['days_held'])
                loser_capital.append(ct.get('capital_invested', 0.0))

        avg_winner_hold = sum(winner_days) / len(winner_days) if winner_days else 0.0
        avg_loser_hold = sum(loser_days) / len(loser_days) if loser_days else 0.0

        # Disposition Ratio: If < 1.0, user sells winners faster than losers (The Disposition Effect!)
        disp_ratio = 1.0
        if avg_loser_hold > 0:
            disp_ratio = avg_winner_hold / avg_loser_hold

        momentum_score = (momentum_buys / total_buys) * 100 if total_buys > 0 else 0.0
        
        # Phase 3 & 4 Metric Aggregations
        win_rate = (len(winner_days) / len(closed_trades) * 100) if closed_trades else 0.0
        winner_avg_capital = sum(winner_capital) / len(winner_capital) if winner_capital else 0.0
        loser_avg_capital = sum(loser_capital) / len(loser_capital) if loser_capital else 0.0
        
        holding_period_variance = float(np.var(days_held_list)) if len(days_held_list) > 1 else 0.0

        days_active = (today - earliest_date).days
        churn_rate = 0.0
        if total_buys_value > 0 and days_active > 0:
            churn_rate = (total_sold_value / total_buys_value) * (365 / days_active) * 100

        actual_profit = sum(ct.get('capital_invested', 0.0) * ct['trade_ret'] for ct in closed_trades)
        bench_profit = sum(ct.get('capital_invested', 0.0) * ct['bench_ret'] for ct in closed_trades)
        market_timing_futility_delta = float(actual_profit - bench_profit)

        detailed_metrics = {
            "avg_winner_hold_days": avg_winner_hold,
            "avg_loser_hold_days": avg_loser_hold,
            "total_closed_trades": len(closed_trades),
            "momentum_buys": momentum_buys,
            "total_buys": total_buys,
            "revenge_trades": revenge_trade_count,
            "panic_sells": panic_sell_count,
            "endowment_traps": endowment_trap_count,
            "churn_rate_percent": churn_rate,
            "win_rate_percent": win_rate,
            "winner_avg_capital": winner_avg_capital,
            "loser_avg_capital": loser_avg_capital,
            "holding_period_variance": holding_period_variance,
            "overconfidence_bias_count": overconfidence_bias_count,
            "dividend_trap_count": dividend_trap_count,
            "bandwagon_bias_count": bandwagon_bias_count,
            "market_timing_futility_delta": market_timing_futility_delta,
            "boredom_trade_count": boredom_trade_count,
            "trades": closed_trades
        }

        # 5. Save Snapshot
        stmt = insert(BehavioralAnalysisSnapshot).values(
            portfolio_id=self.portfolio_id,
            snapshot_date=today,
            disposition_ratio=disp_ratio,
            momentum_bias_score=momentum_score,
            revenge_trade_count=revenge_trade_count,
            panic_sell_score=float(panic_sell_count),  # Stored as float for scale logic
            endowment_trap_count=endowment_trap_count,
            churn_rate=churn_rate,
            win_rate=win_rate,
            winner_avg_capital=winner_avg_capital,
            loser_avg_capital=loser_avg_capital,
            holding_period_variance=holding_period_variance,
            overconfidence_bias_count=overconfidence_bias_count,
            dividend_trap_count=dividend_trap_count,
            bandwagon_bias_count=bandwagon_bias_count,
            market_timing_futility_delta=market_timing_futility_delta,
            boredom_trade_count=boredom_trade_count,
            detailed_metrics=detailed_metrics
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=['portfolio_id'],
            set_={
                'snapshot_date': stmt.excluded.snapshot_date,
                'disposition_ratio': stmt.excluded.disposition_ratio,
                'momentum_bias_score': stmt.excluded.momentum_bias_score,
                'revenge_trade_count': stmt.excluded.revenge_trade_count,
                'panic_sell_score': stmt.excluded.panic_sell_score,
                'endowment_trap_count': stmt.excluded.endowment_trap_count,
                'churn_rate': stmt.excluded.churn_rate,
                'win_rate': stmt.excluded.win_rate,
                'winner_avg_capital': stmt.excluded.winner_avg_capital,
                'loser_avg_capital': stmt.excluded.loser_avg_capital,
                'holding_period_variance': stmt.excluded.holding_period_variance,
                'overconfidence_bias_count': stmt.excluded.overconfidence_bias_count,
                'dividend_trap_count': stmt.excluded.dividend_trap_count,
                'bandwagon_bias_count': stmt.excluded.bandwagon_bias_count,
                'market_timing_futility_delta': stmt.excluded.market_timing_futility_delta,
                'boredom_trade_count': stmt.excluded.boredom_trade_count,
                'detailed_metrics': stmt.excluded.detailed_metrics
            }
        )

        self.db.execute(stmt)
        self.db.commit()
