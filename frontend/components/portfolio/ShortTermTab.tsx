import { Loader2, Activity } from 'lucide-react';
import { AttributionReport } from '@/types/portfolio';

interface ShortTermTabProps {
    attributionData: AttributionReport | null;
    isAttributionLoading: boolean;
    attributionError: string;
    selectedDate: string;
    setSelectedDate: (date: string) => void;
}

export function ShortTermTab({
    attributionData, isAttributionLoading, attributionError,
    selectedDate, setSelectedDate
}: ShortTermTabProps) {
    
    const formatCurrency = (amount: number) => {
        const isNegative = amount < 0;
        const absAmount = Math.abs(amount).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        return `${isNegative ? '-' : ''}₹${absAmount}`;
    };

    const getColorClass = (amount: number) => {
        if (amount > 0) return 'text-green-600';
        if (amount < 0) return 'text-red-600';
        return 'text-gray-900';
    };

    return (
        <div className="space-y-6">
            <div className="bg-white p-6 rounded-lg shadow-sm border border-gray-200">
                <div className="flex justify-between items-center mb-4">
                    <h3 className="text-lg font-semibold text-gray-900 flex items-center">
                        <Activity className="w-5 h-5 mr-2 text-blue-600" /> Performance Attribution
                    </h3>
                    <input 
                        type="date" 
                        value={selectedDate}
                        onChange={(e) => setSelectedDate(e.target.value)}
                        max={new Date().toISOString().split('T')[0]}
                        className="border border-gray-300 rounded-md px-3 py-1.5 text-sm"
                    />
                </div>
                
                {isAttributionLoading ? (
                    <div className="flex justify-center items-center h-32">
                        <Loader2 className="w-6 h-6 animate-spin text-blue-600" />
                    </div>
                ) : attributionError ? (
                    <div className="text-sm text-red-600 p-4 bg-red-50 rounded-md border border-red-100">
                        {attributionError}
                    </div>
                ) : attributionData ? (
                    <div className="space-y-4">
                        {attributionData.primary_drag_ticker && attributionData.absolute_impact > 0 && (
                            <div className="bg-amber-50 border border-amber-200 text-amber-800 px-4 py-3 rounded-md text-sm">
                                <span className="font-semibold">Portfolio Doctor Diagnosis:</span> Ticker {attributionData.primary_drag_ticker} generated the highest negative drag on this date, impacting value by {formatCurrency(-attributionData.absolute_impact)}.
                            </div>
                        )}
                        
                        <div className="overflow-x-auto">
                            <table className="w-full text-sm text-left">
                                <thead className="bg-gray-50 text-gray-600 font-medium border-b border-gray-200">
                                    <tr>
                                        <th className="px-4 py-2">Ticker</th>
                                        <th className="px-4 py-2 text-right">Shares</th>
                                        <th className="px-4 py-2 text-right">Open Drift</th>
                                        <th className="px-4 py-2 text-right">Intraday</th>
                                        <th className="px-4 py-2 text-right">Dividend Shield</th>
                                        <th className="px-4 py-2 text-right">Net Contribution</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-gray-100">
                                    {attributionData.full_contribution_matrix.map((row, idx) => (
                                        <tr key={idx} className="hover:bg-gray-50">
                                            <td className="px-4 py-3 font-medium text-gray-900">{row.ticker}</td>
                                            <td className="px-4 py-3 text-right text-gray-600">{row.shares_held}</td>
                                            <td className={`px-4 py-3 text-right font-medium ${getColorClass(row.legacy_drift)}`}>
                                                {formatCurrency(row.legacy_drift)}
                                            </td>
                                            <td className={`px-4 py-3 text-right font-medium ${getColorClass(row.intraday_impact)}`}>
                                                {formatCurrency(row.intraday_impact)}
                                            </td>
                                            <td className={`px-4 py-3 text-right font-medium ${getColorClass(row.corporate_shield)}`}>
                                                {formatCurrency(row.corporate_shield)}
                                            </td>
                                            <td className={`px-4 py-3 text-right font-bold ${getColorClass(row.net_contribution)}`}>
                                                {formatCurrency(row.net_contribution)}
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </div>
                ) : (
                    <div className="text-sm text-gray-500 text-center py-8">
                        Select a date to view performance attribution.
                    </div>
                )}
            </div>
        </div>
    );
}
