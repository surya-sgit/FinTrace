import { UploadCloud, Download, Loader2, Activity, FileText, TrendingUp, PieChart as PieChartIcon } from 'lucide-react';
import { PieChart, Pie, Cell, Legend, Tooltip as RechartsTooltip, ResponsiveContainer } from 'recharts';
import { Portfolio, XIRRReport, TaxReport, LongTermAttributionReport } from '@/types/portfolio';
import { PerformanceChart } from './PerformanceChart';

interface OverviewTabProps {
    portfolio: Portfolio;
    xirrReport: XIRRReport | null;
    taxReport: TaxReport | null;
    ltData: LongTermAttributionReport | null;
    isUploading: boolean;
    uploadSuccess: string;
    uploadRowErrors: any[];
    selectedFile: File | null;
    pdfPassword: string;
    setPdfPassword: (val: string) => void;
    handleFileSelect: (e: React.ChangeEvent<HTMLInputElement>) => void;
    processUpload: (file: File, password?: string) => void;
    handleDownloadTaxReport: () => void;
    isDownloading: boolean;
}

const COLORS = ['#2563eb', '#3b82f6', '#60a5fa', '#93c5fd', '#bfdbfe', '#dbeafe'];

export function OverviewTab({
    portfolio, xirrReport, taxReport, ltData,
    isUploading, uploadSuccess, uploadRowErrors, selectedFile,
    pdfPassword, setPdfPassword, handleFileSelect, processUpload,
    handleDownloadTaxReport, isDownloading
}: OverviewTabProps) {
    const formatCurrency = (amount: number) => {
        const symbol = portfolio.tax_jurisdiction === 'IN' ? '₹' : '$';
        const isNegative = amount < 0;
        const absAmount = Math.abs(amount).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        return `${isNegative ? '-' : ''}${symbol}${absAmount}`;
    };

    const getColorClass = (amount: number) => {
        if (amount > 0) return 'text-green-600';
        if (amount < 0) return 'text-red-600';
        return 'text-gray-900';
    };

    const pieData = taxReport?.current_holdings
        ? Object.entries(taxReport.current_holdings).map(([name, value]) => ({ name, value: Number(value) })).filter(item => item.value > 0)
        : [];

    return (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
            {/* Full Width Warning Banner for Synthetic Cash */}
            {ltData?.is_synthetic_cash_proxy && (
                <div className="lg:col-span-3 bg-amber-50 border-l-4 border-amber-400 p-4 rounded-md shadow-sm">
                    <div className="flex">
                        <div className="flex-shrink-0">
                            <svg className="h-5 w-5 text-amber-400" viewBox="0 0 20 20" fill="currentColor">
                                <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                            </svg>
                        </div>
                        <div className="ml-3">
                            <h3 className="text-sm font-medium text-amber-800">Synthetic Cash Proxy Enabled</h3>
                            <div className="mt-2 text-sm text-amber-700">
                                <p>No external cash DEPOSIT or WITHDRAWAL transactions were found in your ledger. The Long-Term Value engine has automatically simulated perfectly timed cash deployments to calculate your portfolio XIRR. <strong>This masks un-deployed capital inefficiencies (Cash Drag).</strong> For a true analysis, please upload your brokerage cash flows.</p>
                            </div>
                        </div>
                    </div>
                </div>
            )}

            {/* Left Column: Stats, Upload & Tax Hub */}
            <div className="lg:col-span-1 space-y-6">
                {/* Stats Card */}
                <div className="bg-white p-6 rounded-lg shadow-sm border border-gray-200">
                    <h3 className="text-lg font-semibold text-gray-900 flex items-center mb-4">
                        <Activity className="w-5 h-5 mr-2 text-blue-600" /> Key Metrics
                    </h3>
                    <div className="space-y-4">
                        <div>
                            <p className="text-sm text-gray-500">XIRR (Annualized)</p>
                            <p className="text-2xl font-bold text-gray-900">
                                {xirrReport ? `${xirrReport.xirr_percentage.toFixed(2)}%` : '--'}
                            </p>
                        </div>
                        <div className="grid grid-cols-2 gap-4">
                            <div>
                                <p className="text-sm text-gray-500">Invested</p>
                                <p className="text-lg font-semibold text-gray-900">
                                    {xirrReport ? formatCurrency(xirrReport.total_invested_capital) : '--'}
                                </p>
                            </div>
                            <div>
                                <p className="text-sm text-gray-500">Current Value</p>
                                <p className="text-lg font-semibold text-gray-900">
                                    {xirrReport ? formatCurrency(xirrReport.current_market_value) : '--'}
                                </p>
                            </div>
                        </div>
                    </div>
                </div>

                {/* Ingestion Engine */}
                <div className="bg-white p-6 rounded-lg shadow-sm border border-gray-200">
                    <div className="flex justify-between items-center mb-4">
                        <h3 className="text-lg font-semibold text-gray-900 flex items-center">
                            <UploadCloud className="w-5 h-5 mr-2 text-blue-600" /> Data Ingestion
                        </h3>
                        <a href="/template.csv" download className="text-sm font-medium text-blue-600 hover:text-blue-800 flex items-center bg-blue-50 px-2 py-1 rounded transition-colors">
                            <Download className="w-3.5 h-3.5 mr-1" /> Template
                        </a>
                    </div>
                    <p className="text-sm text-gray-500 mb-4">
                        Upload a broker CSV or CAS PDF to sync transaction ledgers.
                    </p>
                    
                    {!selectedFile || selectedFile.name.toLowerCase().endsWith('.csv') ? (
                        <label className="flex flex-col items-center justify-center w-full h-32 border-2 border-gray-300 border-dashed rounded-lg cursor-pointer bg-gray-50 hover:bg-gray-100 transition-colors relative">
                            <div className="flex flex-col items-center justify-center pt-5 pb-6">
                                {isUploading ? (
                                    <Loader2 className="w-8 h-8 animate-spin text-blue-600" />
                                ) : (
                                    <>
                                        <UploadCloud className="w-8 h-8 text-gray-400 mb-2" />
                                        <p className="text-sm text-gray-500 font-medium">Click to upload CSV or PDF</p>
                                    </>
                                )}
                            </div>
                            <input
                                type="file"
                                accept=".csv, .pdf"
                                className="hidden"
                                onChange={handleFileSelect}
                                disabled={isUploading}
                            />
                        </label>
                    ) : (
                        <div className="p-4 border border-blue-200 bg-blue-50 rounded-lg">
                            <p className="text-sm font-semibold text-blue-900 mb-2 truncate">
                                Selected: {selectedFile.name}
                            </p>
                            <p className="text-xs text-blue-700 mb-3">
                                CAS PDFs are usually password protected (often your PAN).
                            </p>
                            <input
                                type="password"
                                placeholder="Enter PDF Password"
                                className="w-full px-3 py-2 border border-blue-300 rounded-md text-gray-900 mb-3 focus:ring-2 focus:ring-blue-500 outline-none"
                                value={pdfPassword}
                                onChange={(e) => setPdfPassword(e.target.value)}
                                disabled={isUploading}
                            />
                            <div className="flex space-x-2">
                                <button 
                                    onClick={() => { handleFileSelect({ target: { files: [] } } as unknown as React.ChangeEvent<HTMLInputElement>); }}
                                    className="flex-1 px-3 py-2 bg-white border border-gray-300 text-gray-700 rounded-md hover:bg-gray-50 font-medium text-sm transition-colors"
                                    disabled={isUploading}
                                >
                                    Cancel
                                </button>
                                <button
                                    onClick={() => processUpload(selectedFile, pdfPassword)}
                                    className="flex-1 flex items-center justify-center px-3 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 font-medium text-sm transition-colors disabled:opacity-70"
                                    disabled={isUploading || !pdfPassword}
                                >
                                    {isUploading ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Confirm Upload'}
                                </button>
                            </div>
                        </div>
                    )}
                </div>

                {/* Tax Compliance Hub */}
                <div className="bg-white p-6 rounded-lg shadow-sm border border-gray-200">
                    <h3 className="text-lg font-semibold text-gray-900 flex items-center mb-4">
                        <FileText className="w-5 h-5 mr-2 text-blue-600" /> Tax Compliance
                    </h3>
                    <div className="mb-4 space-y-2">
                        <div className="flex justify-between">
                            <span className="text-sm text-gray-500">STCG</span>
                            <span className={`text-sm font-medium ${taxReport ? getColorClass(taxReport.realized_stcg) : ''}`}>
                                {taxReport ? formatCurrency(taxReport.realized_stcg) : '--'}
                            </span>
                        </div>
                        <div className="flex justify-between">
                            <span className="text-sm text-gray-500">LTCG</span>
                            <span className={`text-sm font-medium ${taxReport ? getColorClass(taxReport.realized_ltcg) : ''}`}>
                                {taxReport ? formatCurrency(taxReport.realized_ltcg) : '--'}
                            </span>
                        </div>
                    </div>
                    <button
                        type="button"
                        onClick={(e) => { e.preventDefault(); handleDownloadTaxReport(); }}
                        disabled={isDownloading || !taxReport}
                        className="w-full flex items-center justify-center bg-blue-600 text-white py-2 px-4 rounded-md hover:bg-blue-700 transition-colors font-medium disabled:opacity-70"
                    >
                        {isDownloading ? (
                            <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                        ) : (
                            <Download className="w-4 h-4 mr-2" />
                        )}
                        Download Tax Report
                    </button>
                </div>
            </div>

            {/* Right Column: Visualizations */}
            <div className="lg:col-span-2 space-y-6">
                {/* Time-Series Growth via PerformanceChart */}
                <div className="bg-white p-6 rounded-lg shadow-sm border border-gray-200">
                    <h3 className="text-lg font-semibold text-gray-900 flex items-center mb-4">
                        <TrendingUp className="w-5 h-5 mr-2 text-blue-600" /> Portfolio Growth
                    </h3>
                    {xirrReport && xirrReport.valuation_history && xirrReport.valuation_history.length > 0 ? (
                        <PerformanceChart 
                            data={xirrReport.valuation_history.map(pt => ({
                                date: pt.date,
                                valuation: pt.valuation
                            }))} 
                        />
                    ) : (
                        <div className="h-64 flex items-center justify-center text-gray-400">
                            No transaction records found to process historical timeline.
                        </div>
                    )}
                </div>

                {/* Asset Allocation */}
                <div className="bg-white p-6 rounded-lg shadow-sm border border-gray-200">
                    <h3 className="text-lg font-semibold text-gray-900 flex items-center mb-4">
                        <PieChartIcon className="w-5 h-5 mr-2 text-blue-600" /> Asset Allocation
                    </h3>
                    {pieData.length > 0 ? (
                        <div style={{ width: '100%', height: 250 }}>
                            <ResponsiveContainer width="100%" height="100%">
                                <PieChart>
                                    <Pie
                                        data={pieData}
                                        cx="50%"
                                        cy="50%"
                                        innerRadius={60}
                                        outerRadius={80}
                                        paddingAngle={5}
                                        dataKey="value"
                                    >
                                        {pieData.map((entry, index) => (
                                            <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                                        ))}
                                    </Pie>
                                    <RechartsTooltip />
                                    <Legend />
                                </PieChart>
                            </ResponsiveContainer>
                        </div>
                    ) : (
                        <div className="h-64 flex items-center justify-center text-gray-400">
                            No holdings available to visualize.
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
