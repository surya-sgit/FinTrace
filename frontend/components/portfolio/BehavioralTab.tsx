import React from 'react';
import { Loader2, Brain, Scale, Zap, TrendingUp, AlertTriangle, CheckCircle, Info } from 'lucide-react';
import { BehavioralAnalysisReport } from '@/types/portfolio';

interface BehavioralTabProps {
    data: BehavioralAnalysisReport | null;
    isLoading: boolean;
    error: string;
}

export function BehavioralTab({ data, isLoading, error }: BehavioralTabProps) {
    if (isLoading) {
        return (
            <div className="flex items-center justify-center py-12">
                <Loader2 className="w-8 h-8 animate-spin text-blue-600" />
            </div>
        );
    }

    if (error) {
        return (
            <div className="p-4 bg-red-50 text-red-700 rounded-md border border-red-200">
                {error}
            </div>
        );
    }

    if (!data) {
        return (
            <div className="text-center py-12 text-gray-500">
                No behavioral data available. Upload a transaction ledger to generate insights.
            </div>
        );
    }

    const {
        disposition_ratio,
        momentum_bias_score,
        revenge_trade_count,
        panic_sell_score,
        endowment_trap_count,
        churn_rate,
        win_rate,
        winner_avg_capital,
        loser_avg_capital,
        holding_period_variance,
        overconfidence_bias_count,
        dividend_trap_count,
        bandwagon_bias_count,
        market_timing_futility_delta,
        boredom_trade_count,
        detailed_metrics
    } = data;

    // Helper for traffic light styling
    const getDispColor = (val: number) => val >= 1.2 ? 'text-green-600' : val >= 1.0 ? 'text-yellow-600' : 'text-red-600';
    const getZeroGoodColor = (val: number) => val === 0 ? 'text-green-600' : val <= 2 ? 'text-yellow-600' : 'text-red-600';
    const getWinRateColor = (val: number) => val >= 55 ? 'text-green-600' : val >= 45 ? 'text-yellow-600' : 'text-red-600';
    const getDeltaColor = (val: number) => val > 0 ? 'text-green-600' : 'text-red-600';
    const getChurnColor = (val: number) => val <= 40 ? 'text-green-600' : val <= 100 ? 'text-yellow-600' : 'text-red-600';

    // Tooltip component
    const TooltipInfo = ({ text }: { text: string }) => (
        <div className="group relative inline-block ml-1">
            <Info className="w-3.5 h-3.5 text-gray-400 hover:text-blue-500 cursor-help" />
            <div className="opacity-0 w-48 bg-gray-900 text-white text-xs rounded py-1.5 px-2 absolute z-10 bottom-full left-1/2 -translate-x-1/2 mb-2 pointer-events-none group-hover:opacity-100 transition-opacity">
                {text}
                <svg className="absolute text-gray-900 h-2 w-full left-0 top-full" x="0px" y="0px" viewBox="0 0 255 255"><polygon className="fill-current" points="0,0 127.5,127.5 255,0" /></svg>
            </div>
        </div>
    );

    // Deterministic Insights Engine
    const generateInsights = () => {
        const insights = [];

        if (disposition_ratio < 1.0) {
            insights.push({
                type: 'warning',
                title: 'The Disposition Flaw',
                issue: `You hold losing trades longer than winning trades (${detailed_metrics.avg_loser_hold_days.toFixed(1)} days vs ${detailed_metrics.avg_winner_hold_days.toFixed(1)} days).`,
                fix: 'Mechanical Fix: Place a strict 10-15% stop-loss immediately upon execution. Stop relying on mental stops.'
            });
        } else if (disposition_ratio > 1.5) {
            insights.push({
                type: 'success',
                title: 'Excellent Loss Management',
                issue: 'You cut your losers quickly while letting your winners ride.',
                fix: 'Keep trusting your trailing stop-loss strategy.'
            });
        }

        if (market_timing_futility_delta > 0) {
            insights.push({
                type: 'success',
                title: 'The Alpha Generator',
                issue: `Your active stock picking generated ₹${market_timing_futility_delta.toFixed(2)} in pure Alpha over a passive Nifty 50 strategy.`,
                fix: 'Your edge is working. Continue scaling your highest-conviction setups.'
            });
        } else if (market_timing_futility_delta < 0) {
            insights.push({
                type: 'warning',
                title: 'Market Timing Futility',
                issue: `You underperformed a passive Nifty 50 buy-and-hold strategy by ₹${Math.abs(market_timing_futility_delta).toFixed(2)}.`,
                fix: 'Consider allocating a larger portion of your portfolio to passive ETFs rather than active stock picking.'
            });
        }

        if (boredom_trade_count > 5) {
            insights.push({
                type: 'warning',
                title: 'Action Bias / Boredom Trading',
                issue: `You executed ${boredom_trade_count} trades during periods of extremely low market volatility.`,
                fix: 'Stop forcing trades. Cash is a valid position. Wait for high-probability momentum setups before deploying capital.'
            });
        }

        if (bandwagon_bias_count > 0) {
            insights.push({
                type: 'warning',
                title: 'Shiny Object Syndrome',
                issue: `Detected ${bandwagon_bias_count} instances where you rapidly bought 3+ distinct tickers within a single week.`,
                fix: 'Avoid buying clusters of stocks based on news hype. Phase your capital deployment over weeks instead of days.'
            });
        }

        if (winner_avg_capital > loser_avg_capital * 1.5) {
            insights.push({
                type: 'success',
                title: 'Smart Money Conviction',
                issue: 'You allocate significantly more capital to your winning ideas than your losing ideas.',
                fix: 'Your intuition on position sizing is extremely sharp.'
            });
        } else if (loser_avg_capital > winner_avg_capital * 1.2) {
            insights.push({
                type: 'warning',
                title: 'Inverted Conviction Bias',
                issue: 'You are risking more capital on trades that ultimately lose.',
                fix: 'Review your initial position sizing rules. Do not double-down on losing positions.'
            });
        }
        
        if (win_rate > 55) {
             insights.push({
                type: 'success',
                title: 'Sniper Accuracy',
                issue: `Your win rate is a highly profitable ${win_rate.toFixed(1)}%.`,
                fix: 'Your entry criteria are statistically robust. Do not change your screening process.'
            });
        }

        return insights;
    };

    const insights = generateInsights();

    return (
        <div className="space-y-8 animate-fade-in-up">
            
            {/* Header */}
            <div>
                <h2 className="text-2xl font-bold text-gradient-blue">Hedge Fund Manager Profile</h2>
                <p className="text-gray-500 mt-1">A deep quantitative teardown of your psychological trading biases.</p>
            </div>

            {/* 4 Pillars Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 relative">
                <div className="glow-orb top-0 right-0"></div>
                
                {/* Pillar 1: Discipline */}
                <div className="glass-card-light p-6 z-10">
                    <div className="flex items-center space-x-2 mb-4">
                        <Brain className="w-5 h-5 text-indigo-500" />
                        <h3 className="text-lg font-bold text-gray-900">Discipline</h3>
                    </div>
                    <div className="space-y-4">
                        <div className="flex justify-between items-center">
                            <span className="text-sm text-gray-600 flex items-center">Panic Sells <TooltipInfo text="Selling losers on days when the Nifty drops > 1.5%" /></span>
                            <span className={`font-bold ${getZeroGoodColor(panic_sell_score)}`}>{panic_sell_score}</span>
                        </div>
                        <div className="flex justify-between items-center">
                            <span className="text-sm text-gray-600 flex items-center">Revenge Trades <TooltipInfo text="Buying a stock within 5 days of selling it for a loss" /></span>
                            <span className={`font-bold ${getZeroGoodColor(revenge_trade_count)}`}>{revenge_trade_count}</span>
                        </div>
                        <div className="flex justify-between items-center">
                            <span className="text-sm text-gray-600 flex items-center">Boredom Trades <TooltipInfo text="Trading volume when the Nifty 14-day volatility is < 1%" /></span>
                            <span className={`font-bold ${getZeroGoodColor(boredom_trade_count)}`}>{boredom_trade_count}</span>
                        </div>
                        <div className="flex justify-between items-center">
                            <span className="text-sm text-gray-600 flex items-center">FOMO Buys <TooltipInfo text="% of buys when RSI was > 70 (Overbought)" /></span>
                            <span className={`font-bold ${getChurnColor(momentum_bias_score)}`}>{momentum_bias_score.toFixed(1)}%</span>
                        </div>
                    </div>
                </div>

                {/* Pillar 2: Conviction */}
                <div className="glass-card-light p-6 z-10">
                    <div className="flex items-center space-x-2 mb-4">
                        <Scale className="w-5 h-5 text-blue-500" />
                        <h3 className="text-lg font-bold text-gray-900">Conviction</h3>
                    </div>
                    <div className="space-y-4">
                        <div className="flex justify-between items-center">
                            <span className="text-sm text-gray-600 flex items-center">Winner Avg Capital <TooltipInfo text="Average initial capital allocated to trades that became winners" /></span>
                            <span className="font-bold text-gray-900">₹{winner_avg_capital.toFixed(0)}</span>
                        </div>
                        <div className="flex justify-between items-center">
                            <span className="text-sm text-gray-600 flex items-center">Loser Avg Capital <TooltipInfo text="Average initial capital allocated to trades that became losers" /></span>
                            <span className="font-bold text-gray-900">₹{loser_avg_capital.toFixed(0)}</span>
                        </div>
                        <div className="flex justify-between items-center">
                            <span className="text-sm text-gray-600 flex items-center">Endowment Traps <TooltipInfo text="Buying more of a stock when it is 10% below your average cost" /></span>
                            <span className={`font-bold ${getZeroGoodColor(endowment_trap_count)}`}>{endowment_trap_count}</span>
                        </div>
                        <div className="flex justify-between items-center">
                            <span className="text-sm text-gray-600 flex items-center">Post-Win Recklessness <TooltipInfo text="Sizing up > 2x historical average right after a big win" /></span>
                            <span className={`font-bold ${getZeroGoodColor(overconfidence_bias_count)}`}>{overconfidence_bias_count}</span>
                        </div>
                    </div>
                </div>

                {/* Pillar 3: Agility */}
                <div className="glass-card-light p-6 z-10">
                    <div className="flex items-center space-x-2 mb-4">
                        <Zap className="w-5 h-5 text-yellow-500" />
                        <h3 className="text-lg font-bold text-gray-900">Agility</h3>
                    </div>
                    <div className="space-y-4">
                        <div className="flex justify-between items-center">
                            <span className="text-sm text-gray-600 flex items-center">Portfolio Churn <TooltipInfo text="Annualized turnover rate (Capital Sold / Avg Capital)" /></span>
                            <span className={`font-bold ${getChurnColor(churn_rate)}`}>{churn_rate.toFixed(1)}%</span>
                        </div>
                        <div className="flex justify-between items-center">
                            <span className="text-sm text-gray-600 flex items-center">Strategy Erraticism <TooltipInfo text="Statistical variance of your holding periods. High variance = emotional exits." /></span>
                            <span className="font-bold text-gray-900">{holding_period_variance.toFixed(0)}</span>
                        </div>
                        <div className="flex justify-between items-center">
                            <span className="text-sm text-gray-600 flex items-center">Bandwagon Biases <TooltipInfo text="Rapidly buying 3+ distinct tickers in a 7-day window" /></span>
                            <span className={`font-bold ${getZeroGoodColor(bandwagon_bias_count)}`}>{bandwagon_bias_count}</span>
                        </div>
                    </div>
                </div>

                {/* Pillar 4: Performance */}
                <div className="glass-card-light p-6 z-10">
                    <div className="flex items-center space-x-2 mb-4">
                        <TrendingUp className="w-5 h-5 text-green-500" />
                        <h3 className="text-lg font-bold text-gray-900">Performance</h3>
                    </div>
                    <div className="space-y-4">
                        <div className="flex justify-between items-center">
                            <span className="text-sm text-gray-600 flex items-center">Active Delta (vs Nifty) <TooltipInfo text="Absolute profit vs buying Nifty 50 on the exact same dates" /></span>
                            <span className={`font-bold ${getDeltaColor(market_timing_futility_delta)}`}>
                                {market_timing_futility_delta > 0 ? '+' : ''}₹{market_timing_futility_delta.toFixed(0)}
                            </span>
                        </div>
                        <div className="flex justify-between items-center">
                            <span className="text-sm text-gray-600 flex items-center">Win Rate <TooltipInfo text="% of closed trades that resulted in positive Alpha" /></span>
                            <span className={`font-bold ${getWinRateColor(win_rate)}`}>{win_rate.toFixed(1)}%</span>
                        </div>
                        <div className="flex justify-between items-center">
                            <span className="text-sm text-gray-600 flex items-center">Disposition Ratio <TooltipInfo text="Avg Winner Hold Days / Avg Loser Hold Days. Aim for > 1.0" /></span>
                            <span className={`font-bold ${getDispColor(disposition_ratio)}`}>{disposition_ratio.toFixed(2)}</span>
                        </div>
                        <div className="flex justify-between items-center">
                            <span className="text-sm text-gray-600 flex items-center">Dividend Traps <TooltipInfo text="Capital loss exceeds dividend yield collected" /></span>
                            <span className={`font-bold ${getZeroGoodColor(dividend_trap_count)}`}>{dividend_trap_count}</span>
                        </div>
                    </div>
                </div>
            </div>

            {/* Diagnosis Engine */}
            <div className="mt-8 z-10 relative">
                <h3 className="text-xl font-bold text-gray-900 mb-4">Diagnosis & Action Plan</h3>
                <div className="space-y-4">
                    {insights.length === 0 ? (
                        <div className="p-6 bg-gray-50 border border-gray-200 rounded-lg text-gray-500 text-center">
                            Your psychological profile is perfectly balanced. No critical issues detected.
                        </div>
                    ) : (
                        insights.map((insight, idx) => (
                            <div key={idx} className={`p-5 rounded-xl border ${insight.type === 'warning' ? 'bg-red-50/50 border-red-200' : 'bg-green-50/50 border-green-200'} shadow-sm`}>
                                <div className="flex items-start">
                                    {insight.type === 'warning' ? (
                                        <AlertTriangle className="w-5 h-5 text-red-500 mt-0.5 mr-3 shrink-0" />
                                    ) : (
                                        <CheckCircle className="w-5 h-5 text-green-500 mt-0.5 mr-3 shrink-0" />
                                    )}
                                    <div>
                                        <h4 className={`font-bold ${insight.type === 'warning' ? 'text-red-900' : 'text-green-900'}`}>
                                            {insight.title}
                                        </h4>
                                        <p className={`mt-1 text-sm ${insight.type === 'warning' ? 'text-red-700' : 'text-green-700'}`}>
                                            {insight.issue}
                                        </p>
                                        <div className="mt-3 text-sm font-medium text-gray-800 bg-white/60 p-3 rounded-lg border border-white/40">
                                            <span className="text-blue-600 font-bold mr-1">Fix:</span> {insight.fix}
                                        </div>
                                    </div>
                                </div>
                            </div>
                        ))
                    )}
                </div>
            </div>
        </div>
    );
}
