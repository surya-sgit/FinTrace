import { useState, useRef, useEffect } from 'react';
import { Loader2, Activity, PieChart as PieChartIcon, TrendingUp, Clock, Info } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer, Legend, ReferenceLine } from 'recharts';
import { LongTermAttributionReport, RiskMetricsReport, HoldingPeriodRow } from '@/types/portfolio';

// ── Reusable info tooltip ──────────────────────────────────────────────────
function InfoTooltip({ text }: { text: string }) {
    const [open, setOpen] = useState(false);
    const ref = useRef<HTMLDivElement>(null);

    useEffect(() => {
        if (!open) return;
        function handler(e: MouseEvent) {
            if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
        }
        document.addEventListener('mousedown', handler);
        return () => document.removeEventListener('mousedown', handler);
    }, [open]);

    return (
        <div ref={ref} className="relative inline-flex items-center ml-2">
            <button
                onClick={() => setOpen(o => !o)}
                className="text-gray-400 hover:text-blue-500 transition-colors focus:outline-none"
                aria-label="More information"
            >
                <Info className="w-4 h-4" />
            </button>
            {open && (
                <div className="absolute z-50 left-6 top-0 w-72 bg-gray-900 text-white text-xs rounded-lg p-3 shadow-xl leading-relaxed">
                    {text}
                    <div className="absolute -left-1.5 top-2 w-3 h-3 bg-gray-900 rotate-45" />
                </div>
            )}
        </div>
    );
}

interface LongTermTabProps {
    ltData: LongTermAttributionReport | null;
    isLtLoading: boolean;
    ltError: string;
    riskMetrics: RiskMetricsReport | null;
    isRiskLoading: boolean;
    riskError: string;
}

export interface MwrSlicingItem {
    ticker: string;
    standalone_xirr: number;
    mwr_contribution: number;
}

export function processMwrSlicing(mwrSlicing: MwrSlicingItem[] | null | undefined): (MwrSlicingItem & { original_xirr: number; isCapped: boolean })[] {
    if (!mwrSlicing) return [];
    return [...mwrSlicing]
        .filter((item) => item && item.standalone_xirr !== null && item.standalone_xirr !== undefined && !isNaN(item.standalone_xirr))
        .map((item) => {
            const original = item.standalone_xirr;
            let displayXirr = original;
            let isCapped = false;
            if (displayXirr > 10.0) { displayXirr = 10.0; isCapped = true; }
            else if (displayXirr < -1.0) { displayXirr = -1.0; isCapped = true; }
            return { ...item, standalone_xirr: displayXirr, original_xirr: original, isCapped };
        })
        .sort((a, b) => b.standalone_xirr - a.standalone_xirr);
}

function fmt(val: number, decimals = 2) { return val.toFixed(decimals); }
function fmtPct(val: number, decimals = 2) { return `${(val * 100).toFixed(decimals)}%`; }

function StatCard({ label, value, sub, positive, info }: { label: string; value: string; sub?: string; positive?: boolean; info?: string }) {
    const colour = positive === undefined ? 'text-gray-900' : positive ? 'text-green-600' : 'text-red-600';
    return (
        <div className="bg-gray-50 rounded-xl p-4 border border-gray-100">
            <div className="text-xs text-gray-500 font-medium uppercase tracking-wide mb-1 flex items-center">
                {label}
                {info && <InfoTooltip text={info} />}
            </div>
            <p className={`text-2xl font-bold ${colour}`}>{value}</p>
            {sub && <p className="text-xs text-gray-400 mt-1">{sub}</p>}
        </div>
    );
}

export function LongTermTab({ ltData, isLtLoading, ltError, riskMetrics, isRiskLoading, riskError }: LongTermTabProps) {
    const processedMwrSlicing = processMwrSlicing(ltData?.mwr_slicing);

    return (
        <div className="space-y-6">

            {/* ── Risk Summary Cards ── */}
            <div className="bg-white p-6 rounded-lg shadow-sm border border-gray-200">
                <h3 className="text-lg font-semibold text-gray-900 flex items-center mb-4">
                    <TrendingUp className="w-5 h-5 mr-2 text-blue-600" /> Portfolio Risk & Return Summary
                </h3>
                {isRiskLoading ? (
                    <div className="flex justify-center items-center h-24"><Loader2 className="w-6 h-6 animate-spin text-blue-600" /></div>
                ) : riskError ? (
                    <div className="text-sm text-red-600 p-4 bg-red-50 rounded-md border border-red-100">{riskError}</div>
                ) : riskMetrics ? (
                    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
                        <StatCard
                            label="Alpha (Ann.)"
                            value={fmtPct(riskMetrics.alpha)}
                            sub="vs NIFTY 50"
                            positive={riskMetrics.alpha > 0}
                            info="Annualised excess return compared to the NIFTY 50 benchmark. Positive alpha means your portfolio outperformed the market."
                        />
                        <StatCard
                            label="Beta"
                            value={fmt(riskMetrics.beta, 2)}
                            sub={riskMetrics.beta > 1 ? 'More volatile than market' : 'Less volatile than market'}
                            info="Measures how sensitive your portfolio is to market moves. Beta of 1.0 means it moves exactly with the market. Beta > 1 means higher volatility."
                        />
                        <StatCard
                            label="Max Drawdown"
                            value={fmtPct(riskMetrics.max_drawdown)}
                            sub="Peak-to-trough"
                            positive={false}
                            info="The worst peak-to-trough loss your portfolio has ever experienced. A key indicator of downside risk."
                        />
                        <StatCard
                            label="Ann. Volatility"
                            value={fmtPct(riskMetrics.annualised_volatility)}
                            sub="Std dev of returns"
                            info="How much your daily returns swing up and down (annualised standard deviation). Lower means steadier growth."
                        />
                        <StatCard
                            label="Sharpe Ratio"
                            value={fmt(riskMetrics.sharpe_ratio, 2)}
                            sub="Risk-free: 6.5%"
                            positive={riskMetrics.sharpe_ratio > 0}
                            info="Measures the return earned per unit of total risk. A higher ratio (>1) indicates excellent risk-adjusted performance."
                        />
                        <StatCard
                            label="Sortino Ratio"
                            value={fmt(riskMetrics.sortino_ratio, 2)}
                            sub="Downside deviation"
                            positive={riskMetrics.sortino_ratio > 0}
                            info="Similar to the Sharpe Ratio, but only penalises downside volatility (losses). Upside swings aren't treated as a risk here."
                        />
                    </div>
                ) : (
                    <div className="h-24 flex items-center justify-center text-gray-400 text-sm">No risk data available.</div>
                )}
            </div>

            {/* ── Brinson-Fachler ── */}
            <div className="bg-white p-6 rounded-lg shadow-sm border border-gray-200">
                <h3 className="text-lg font-semibold text-gray-900 flex items-center mb-1">
                    <Activity className="w-5 h-5 mr-2 text-blue-600" /> Macro Brinson-Fachler Decomposition
                    <InfoTooltip text="Breaks down your return vs the NSE sector benchmark into three effects. Allocation Effect: did you over/underweight the right sectors? Selection Effect: did you pick stocks that beat their sector index? Interaction Effect: the combined impact of both decisions. Positive bars = that decision added return. Negative bars = it cost you return." />
                </h3>
                <p className="text-xs text-gray-400 mb-4">Allocation, selection &amp; interaction effects vs NSE sector indices</p>
                {isLtLoading ? (
                    <div className="flex justify-center items-center h-32"><Loader2 className="w-6 h-6 animate-spin text-blue-600" /></div>
                ) : ltError ? (
                    <div className="text-sm text-red-600 p-4 bg-red-50 rounded-md border border-red-100">{ltError}</div>
                ) : ltData && ltData.brinson_fachler.length > 0 ? (
                    <div className="w-full h-[320px]">
                        <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={0}>
                            <BarChart data={ltData.brinson_fachler} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
                                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                                <XAxis dataKey="sector" fontSize={11} tick={{ fill: '#6b7280' }} />
                                <YAxis tickFormatter={(val) => `${(val * 100).toFixed(1)}%`} fontSize={11} tick={{ fill: '#6b7280' }} />
                                <ReferenceLine y={0} stroke="#d1d5db" />
                                <RechartsTooltip formatter={(val: any) => `${(Number(val) * 100).toFixed(2)}%`} />
                                <Legend />
                                <Bar dataKey="allocation_effect" fill="#8884d8" name="Allocation Effect" radius={[3, 3, 0, 0]} />
                                <Bar dataKey="selection_effect" fill="#82ca9d" name="Selection Effect" radius={[3, 3, 0, 0]} />
                                <Bar dataKey="interaction_effect" fill="#fbbf24" name="Interaction Effect" radius={[3, 3, 0, 0]} />
                            </BarChart>
                        </ResponsiveContainer>
                    </div>
                ) : (
                    <div className="h-64 flex items-center justify-center text-gray-400 text-sm">
                        No sector benchmark data available.
                    </div>
                )}
            </div>

            {/* ── MWR XIRR Slicing ── */}
            <div className="bg-white p-6 rounded-lg shadow-sm border border-gray-200">
                <h3 className="text-lg font-semibold text-gray-900 flex items-center mb-1">
                    <PieChartIcon className="w-5 h-5 mr-2 text-blue-600" /> Asset &amp; Cash Drag MWR Slicing
                    <InfoTooltip text="Shows the standalone XIRR (annualised return) for each individual holding in isolation. XIRR accounts for the exact timing and size of your buys and sells. ATE_PORTFOLIO represents uninvested cash — a negative XIRR here means idle cash is dragging your overall return. Values beyond ±200% are capped visually; hover for the real number." />
                </h3>
                <p className="text-xs text-gray-400 mb-4">Standalone XIRR per asset — values beyond ±200% are capped for readability (tooltip shows true value)</p>
                {isLtLoading ? (
                    <div className="flex justify-center items-center h-32"><Loader2 className="w-6 h-6 animate-spin text-blue-600" /></div>
                ) : processedMwrSlicing.length > 0 ? (
                    <div className="w-full" style={{ height: Math.max(300, processedMwrSlicing.length * 26 + 60) }}>
                        <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={0}>
                            <BarChart
                                data={processedMwrSlicing}
                                layout="vertical"
                                margin={{ top: 5, right: 40, left: 110, bottom: 5 }}
                            >
                                <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                                <XAxis type="number" tickFormatter={(val) => `${(val * 100).toFixed(0)}%`} fontSize={11} tick={{ fill: '#6b7280' }} />
                                <YAxis dataKey="ticker" type="category" fontSize={11} tick={{ fill: '#374151' }} width={105} />
                                <ReferenceLine x={0} stroke="#d1d5db" />
                                <RechartsTooltip
                                    formatter={(value: any, name: any, props: any) => {
                                        const original = props.payload?.original_xirr;
                                        if (original !== undefined) {
                                            const displayVal = `${(Number(original) * 100).toFixed(2)}%`;
                                            return [props.payload?.isCapped ? `${displayVal} (capped for display)` : displayVal, 'XIRR'];
                                        }
                                        return [`${(Number(value) * 100).toFixed(2)}%`, 'XIRR'];
                                    }}
                                />
                                <Bar dataKey="standalone_xirr" fill="#3b82f6" name="Standalone XIRR" radius={[0, 3, 3, 0]} />
                            </BarChart>
                        </ResponsiveContainer>
                    </div>
                ) : null}
            </div>

            {/* ── Holding Period Table ── */}
            <div className="bg-white p-6 rounded-lg shadow-sm border border-gray-200">
                <h3 className="text-lg font-semibold text-gray-900 flex items-center mb-1">
                    <Clock className="w-5 h-5 mr-2 text-blue-600" /> Holding Period Analysis
                    <InfoTooltip text="Shows how long you've held each stock, calculated using FIFO lot matching (oldest shares sold first). Avg Hold = average days across all lots bought and sold. Max Hold = the longest any single lot was held. Open Qty = shares still in your portfolio. 'Held' = position still open; 'Exited' = fully sold. Longer holding periods generally indicate a long-term investing style." />
                </h3>
                <p className="text-xs text-gray-400 mb-4">FIFO lot-matched average holding duration per ticker</p>
                {isRiskLoading ? (
                    <div className="flex justify-center items-center h-32"><Loader2 className="w-6 h-6 animate-spin text-blue-600" /></div>
                ) : riskMetrics && riskMetrics.holding_periods.length > 0 ? (
                    <div className="overflow-x-auto">
                        <table className="w-full text-sm text-left">
                            <thead>
                                <tr className="border-b border-gray-100 text-xs text-gray-500 uppercase tracking-wide">
                                    <th className="pb-2 pr-4 font-medium">Ticker</th>
                                    <th className="pb-2 pr-4 font-medium text-right">Avg Hold</th>
                                    <th className="pb-2 pr-4 font-medium text-right">Max Hold</th>
                                    <th className="pb-2 pr-4 font-medium text-right">Open Qty</th>
                                    <th className="pb-2 font-medium text-right">Status</th>
                                </tr>
                            </thead>
                            <tbody>
                                {riskMetrics.holding_periods
                                    .sort((a, b) => b.avg_holding_days - a.avg_holding_days)
                                    .map((row: HoldingPeriodRow) => (
                                    <tr key={row.ticker} className="border-b border-gray-50 hover:bg-gray-50 transition-colors">
                                        <td className="py-2 pr-4 font-mono font-medium text-gray-800">{row.ticker}</td>
                                        <td className="py-2 pr-4 text-right text-gray-700">{row.avg_holding_days.toFixed(0)} days</td>
                                        <td className="py-2 pr-4 text-right text-gray-500">{row.max_holding_days} days</td>
                                        <td className="py-2 pr-4 text-right text-gray-700">{row.open_position_qty.toFixed(2)}</td>
                                        <td className="py-2 text-right">
                                            <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${row.is_still_held ? 'bg-green-50 text-green-700' : 'bg-gray-100 text-gray-500'}`}>
                                                {row.is_still_held ? 'Held' : 'Exited'}
                                            </span>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                ) : (
                    <div className="h-24 flex items-center justify-center text-gray-400 text-sm">No holding period data available.</div>
                )}
            </div>

        </div>
    );
}


