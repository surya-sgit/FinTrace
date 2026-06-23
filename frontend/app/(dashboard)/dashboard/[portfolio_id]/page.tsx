'use client';

import { useEffect, useState, use } from 'react';
import { useRouter } from 'next/navigation';
import {
    ArrowLeft,
    UploadCloud,
    Download,
    Loader2,
    TrendingUp,
    PieChart as PieChartIcon,
    Activity,
    FileText
} from 'lucide-react';
import {
    LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer,
    PieChart, Pie, Cell, Legend, BarChart, Bar
} from 'recharts';
import api from '@/lib/api';

interface Portfolio {
    id: string;
    name: string;
    tax_jurisdiction: string;
    created_at: string;
}

interface ValuationPoint {
    date: string;
    valuation: number;
}

interface XIRRReport {
    xirr_percentage: number;
    total_invested_capital: number;
    current_market_value: number;
    valuation_history?: ValuationPoint[];
}

interface TaxReport {
    realized_stcg: number;
    realized_ltcg: number;
    current_holdings: Record<string, number>;
}

interface DragRow {
    ticker: string;
    shares_held: number;
    legacy_drift: number;
    intraday_impact: number;
    corporate_shield: number;
    net_contribution: number;
}

interface AttributionReport {
    analysis_date: string;
    primary_drag_ticker: string | null;
    absolute_impact: number;
    full_contribution_matrix: DragRow[];
}

interface OrganicVariationRow {
    ticker: string;
    net_organic_contribution: number;
}

interface BrinsonFachlerRow {
    sector: string;
    allocation_effect: number;
    selection_effect: number;
    interaction_effect: number;
}

interface MWRSlicingRow {
    ticker: string;
    standalone_xirr: number;
    mwr_contribution: number;
}

interface LongTermAttributionReport {
    portfolio_id: string;
    start_date: string;
    end_date: string;
    organic_variation: OrganicVariationRow[];
    brinson_fachler: BrinsonFachlerRow[];
    mwr_slicing: MWRSlicingRow[];
    is_synthetic_cash_proxy: boolean;
}

const COLORS = ['#2563eb', '#3b82f6', '#60a5fa', '#93c5fd', '#bfdbfe', '#dbeafe'];

export default function PortfolioDetailPage({ params }: { params: Promise<{ portfolio_id: string }> }) {
    const router = useRouter();
    const resolvedParams = use(params);
    const { portfolio_id } = resolvedParams;

    const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
    const [xirrReport, setXirrReport] = useState<XIRRReport | null>(null);
    const [taxReport, setTaxReport] = useState<TaxReport | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [isUploading, setIsUploading] = useState(false);
    const [isDownloading, setIsDownloading] = useState(false);
    const [error, setError] = useState('');
    const [uploadSuccess, setUploadSuccess] = useState('');
    const [uploadRowErrors, setUploadRowErrors] = useState<any[]>([]);
    const [selectedFile, setSelectedFile] = useState<File | null>(null);
    const [pdfPassword, setPdfPassword] = useState('');

    const [selectedDate, setSelectedDate] = useState<string>(new Date().toISOString().split('T')[0]);
    const [attributionData, setAttributionData] = useState<AttributionReport | null>(null);
    const [isAttributionLoading, setIsAttributionLoading] = useState(false);
    const [attributionError, setAttributionError] = useState('');

    const [ltData, setLtData] = useState<LongTermAttributionReport | null>(null);
    const [isLtLoading, setIsLtLoading] = useState(false);
    const [ltError, setLtError] = useState('');

    const [activeTab, setActiveTab] = useState<'overview' | 'short-term' | 'long-term'>('overview');

    useEffect(() => {
        fetchData();
    }, [portfolio_id, selectedDate]);

    const fetchData = async () => {
        setIsLoading(true);
        setError('');
        try {
            // 1. Fetch Portfolio Details
            const portRes = await api.get(`/portfolios/${portfolio_id}`);
            setPortfolio(portRes.data);

            // 2. Fetch Analytics (Run in parallel if portfolio exists)
            try {
                const [xirrRes, taxRes] = await Promise.all([
                    api.get(`/portfolios/${portfolio_id}/xirr-report`),
                    api.get(`/portfolios/${portfolio_id}/tax-report`)
                ]);
                setXirrReport(xirrRes.data);
                setTaxReport(taxRes.data);
            } catch (err) {
                console.log("No data for reports yet or engine error.", err);
            }

            // 3. Fetch Attribution
            setIsAttributionLoading(true);
            setAttributionError('');
            try {
                const attrRes = await api.get(`/analytics/${portfolio_id}/attribution?target_date=${selectedDate}`);
                setAttributionData(attrRes.data);
            } catch (err: any) {
                setAttributionError(err.response?.data?.detail || 'Failed to load attribution data.');
                setAttributionData(null);
            } finally {
                setIsAttributionLoading(false);
            }

            // 4. Fetch Long Term Analytics
            setIsLtLoading(true);
            setLtError('');
            try {
                const ltRes = await api.get(`/analytics/${portfolio_id}/long-term-attribution`);
                setLtData(ltRes.data);
            } catch (err: any) {
                setLtError('Failed to load long term analytics.');
            } finally {
                setIsLtLoading(false);
            }

        } catch (err: any) {
            setError(err.response?.data?.detail || 'Failed to load portfolio details.');
        } finally {
            setIsLoading(false);
        }
    };

    const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;

        setError('');
        setUploadSuccess('');
        setSelectedFile(file);
        setPdfPassword('');

        if (file.name.toLowerCase().endsWith('.csv')) {
            await processUpload(file, '');
        }
        // If it's a PDF, we just wait for the user to enter the password and click submit
    };

    const processUpload = async (file: File, password?: string) => {
        setIsUploading(true);
        setError('');
        setUploadSuccess('');
        setUploadRowErrors([]);

        const formData = new FormData();
        formData.append('file', file);
        if (password) {
            formData.append('password', password);
        }

        try {
            await api.post(`/portfolios/${portfolio_id}/upload`, formData, {
                headers: {
                    'Content-Type': 'multipart/form-data',
                },
            });
            setUploadSuccess('Transactions successfully ingested and market data synced.');
            setSelectedFile(null);
            setPdfPassword('');
            fetchData();
        } catch (err: any) {
            let errorMsg = 'Failed to upload file.';
            if (err.response) {
                const { status: s, data } = err.response;
                if (s === 422) {
                    setUploadRowErrors(data.detail.errors || []);
                    errorMsg = data.detail.message || 'Validation failed';
                } else if (s === 401 || s === 400) {
                    errorMsg = data.detail || 'Invalid request';
                } else {
                    errorMsg = err.message;
                }
            } else {
                errorMsg = err.message;
            }
            setError(errorMsg);
        } finally {
            setIsUploading(false);
        }
    };

    const handleDownloadTaxReport = async () => {
        setIsDownloading(true);
        setError('');
        try {
            const response = await api.get(`/portfolios/${portfolio_id}/tax-report/pdf`, {
                responseType: 'blob',
            });

            const url = window.URL.createObjectURL(new Blob([response.data]));
            const link = document.createElement('a');
            link.href = url;
            link.setAttribute('download', `FinTrace_Tax_Report_${portfolio_id}.pdf`);
            document.body.appendChild(link);
            link.click();
            link.remove();
        } catch (err: any) {
            setError('Failed to download tax report.');
        } finally {
            setIsDownloading(false);
        }
    };

    if (isLoading) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-gray-50">
                <Loader2 className="w-8 h-8 animate-spin text-blue-600" />
            </div>
        );
    }

    if (!portfolio) {
        return (
            <div className="min-h-screen p-8 bg-gray-50 text-center flex flex-col items-center justify-center">
                <h2 className="text-2xl font-bold text-gray-900 mb-4">Portfolio Not Found</h2>
                <button onClick={() => router.push('/dashboard')} className="text-blue-600 hover:underline">
                    Return to Dashboard
                </button>
            </div>
        );
    }

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
        <div className="min-h-screen bg-gray-50 relative">
            {/* Top Navigation */}
            <nav className="bg-white border-b border-gray-200 px-6 py-4 flex justify-between items-center">
                <div className="flex items-center space-x-4">
                    <button onClick={() => router.push('/dashboard')} className="text-gray-500 hover:text-gray-900 transition-colors">
                        <ArrowLeft className="w-5 h-5" />
                    </button>
                    <div className="flex items-center space-x-2">
                        <h1 className="text-xl font-bold text-gray-900">{portfolio.name}</h1>
                        <span className="px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                            {portfolio.tax_jurisdiction}
                        </span>
                    </div>
                </div>
            </nav>

            <main className="max-w-7xl mx-auto px-6 py-8">
                {error && (
                    <div className="mb-6 p-4 bg-red-50 text-red-700 rounded-md border border-red-200">
                        <p>{error}</p>
                        {uploadRowErrors.length > 0 && (
                            <div className="mt-4">
                                <h4 className="font-semibold mb-2">Row Validation Errors:</h4>
                                <ul className="list-disc list-inside text-sm space-y-1">
                                    {uploadRowErrors.map((e, i) => (
                                        <li key={i}>
                                            <span className="font-medium">Row {e.row}:</span>{' '}
                                            {Array.isArray(e.errors) ? e.errors.map((err: any) => err.msg || err).join(', ') : e.errors}
                                        </li>
                                    ))}
                                </ul>
                            </div>
                        )}
                    </div>
                )}
                {uploadSuccess && (
                    <div className="mb-6 p-4 bg-green-50 text-green-700 rounded-md border border-green-200">
                        {uploadSuccess}
                    </div>
                )}

                <div className="mb-6 border-b border-gray-200">
                    <nav className="-mb-px flex space-x-8">
                        <button
                            onClick={() => setActiveTab('overview')}
                            className={`${activeTab === 'overview' ? 'border-blue-500 text-blue-600' : 'border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700'} whitespace-nowrap pb-4 px-1 border-b-2 font-medium text-sm`}
                        >
                            Overview
                        </button>
                        <button
                            onClick={() => setActiveTab('short-term')}
                            className={`${activeTab === 'short-term' ? 'border-blue-500 text-blue-600' : 'border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700'} whitespace-nowrap pb-4 px-1 border-b-2 font-medium text-sm`}
                        >
                            Short-Term Attribution
                        </button>
                        <button
                            onClick={() => setActiveTab('long-term')}
                            className={`${activeTab === 'long-term' ? 'border-blue-500 text-blue-600' : 'border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700'} whitespace-nowrap pb-4 px-1 border-b-2 font-medium text-sm`}
                        >
                            Long-Term Value
                        </button>
                    </nav>
                </div>

                {activeTab === 'overview' && (
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
                                            onClick={() => { setSelectedFile(null); setPdfPassword(''); }}
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
                    </div>
                )}

                {activeTab === 'short-term' && (
                    <div className="space-y-6">
                        {/* Performance Attribution Panel */}
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
                )}

                {activeTab === 'long-term' && (
                    <div className="space-y-6">
                        {/* Brinson Fachler Sector Attribution */}
                        <div className="bg-white p-6 rounded-lg shadow-sm border border-gray-200">
                            <h3 className="text-lg font-semibold text-gray-900 flex items-center mb-4">
                                <Activity className="w-5 h-5 mr-2 text-blue-600" /> Macro Brinson-Fachler Decomposition
                            </h3>
                            {isLtLoading ? (
                                <div className="flex justify-center items-center h-32">
                                    <Loader2 className="w-6 h-6 animate-spin text-blue-600" />
                                </div>
                            ) : ltError ? (
                                <div className="text-sm text-red-600 p-4 bg-red-50 rounded-md border border-red-100">
                                    {ltError}
                                </div>
                            ) : ltData && ltData.brinson_fachler.length > 0 ? (
                                <div className="w-full h-[300px]">
                                    <ResponsiveContainer width="100%" height="100%">
                                        <BarChart data={ltData.brinson_fachler} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
                                            <CartesianGrid strokeDasharray="3 3" vertical={false} />
                                            <XAxis dataKey="sector" fontSize={12} />
                                            <YAxis tickFormatter={(val) => `${(val * 100).toFixed(1)}%`} fontSize={12} />
                                            <RechartsTooltip formatter={(val: number) => `${(val * 100).toFixed(2)}%`} />
                                            <Legend />
                                            <Bar dataKey="allocation_effect" fill="#8884d8" name="Allocation Effect" />
                                            <Bar dataKey="selection_effect" fill="#82ca9d" name="Selection Effect" />
                                        </BarChart>
                                    </ResponsiveContainer>
                                </div>
                            ) : (
                                <div className="h-64 flex items-center justify-center text-gray-400">
                                    No macro benchmark data available to decompose sector returns.
                                </div>
                            )}
                        </div>

                        {/* MWR Contribution (Cash Drag) */}
                        <div className="bg-white p-6 rounded-lg shadow-sm border border-gray-200 mt-6">
                            <h3 className="text-lg font-semibold text-gray-900 flex items-center mb-4">
                                <PieChartIcon className="w-5 h-5 mr-2 text-blue-600" /> Asset & Cash Drag MWR Slicing
                            </h3>
                            {isLtLoading ? (
                                <div className="flex justify-center items-center h-32">
                                    <Loader2 className="w-6 h-6 animate-spin text-blue-600" />
                                </div>
                            ) : ltData && ltData.mwr_slicing.length > 0 ? (
                                <div className="w-full h-[300px]">
                                    <ResponsiveContainer width="100%" height="100%">
                                        <BarChart 
                                            data={ltData.mwr_slicing.sort((a,b) => b.standalone_xirr - a.standalone_xirr)} 
                                            layout="vertical"
                                            margin={{ top: 20, right: 30, left: 40, bottom: 5 }}
                                        >
                                            <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                                            <XAxis type="number" tickFormatter={(val) => `${(val * 100).toFixed(0)}%`} fontSize={12} />
                                            <YAxis dataKey="ticker" type="category" fontSize={12} />
                                            <RechartsTooltip formatter={(val: number) => `${(val * 100).toFixed(2)}%`} />
                                            <Legend />
                                            <Bar dataKey="standalone_xirr" fill="#3b82f6" name="Standalone XIRR" />
                                        </BarChart>
                                    </ResponsiveContainer>
                                </div>
                            ) : null}
                        </div>
                    </div>
                )}
            </main>
        </div>
    );
}

// ==========================================
// SUB-COMPONENTS: PERFORMANCE CHART ENGINE
// ==========================================

interface ChartDataPoint {
    date: string;
    valuation: number;
}

interface PerformanceChartProps {
    data: ChartDataPoint[];
}

function PerformanceChart({ data }: PerformanceChartProps) {
    const formatXAxisDate = (dateStr: string) => {
        if (!dateStr) return '';
        try {
            const d = new Date(dateStr);
            return d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' });
        } catch {
            return dateStr;
        }
    };

    const formatCurrency = (value: number) => {
        return new Intl.NumberFormat('en-IN', {
            style: 'currency',
            currency: 'INR',
            maximumFractionDigits: 2
        }).format(value);
    };

    return (
        <div className="w-full h-[250px]">
            <ResponsiveContainer width="100%" height="100%">
                <LineChart data={data} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" vertical={false} />
                    <XAxis
                        dataKey="date"
                        tickFormatter={formatXAxisDate}
                        stroke="#9ca3af"
                        fontSize={12}
                        tickLine={false}
                    />
                    <YAxis
                        stroke="#9ca3af"
                        fontSize={12}
                        tickLine={false}
                        tickFormatter={(value) => `₹${value.toLocaleString('en-IN')}`}
                    />
                    <RechartsTooltip
                        formatter={(value: any) => [formatCurrency(Number(value) || 0), 'Valuation']}
                        labelFormatter={(label) => `Date: ${new Date(label).toLocaleDateString('en-IN')}`}
                        contentStyle={{ backgroundColor: '#ffffff', borderRadius: '6px', border: '1px solid #e5e7eb' }}
                    />
                    <Line
                        type="monotone"
                        dataKey="valuation"
                        stroke="#2563eb"
                        strokeWidth={2.5}
                        dot={{ r: 4, stroke: '#2563eb', strokeWidth: 1, fill: '#ffffff' }}
                        activeDot={{ r: 6 }}
                    />
                </LineChart>
            </ResponsiveContainer>
        </div>
    );
}
