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
    PieChart, Pie, Cell, Legend
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

    useEffect(() => {
        fetchData();
    }, [portfolio_id]);

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

        } catch (err: any) {
            setError(err.response?.data?.detail || 'Failed to load portfolio details.');
        } finally {
            setIsLoading(false);
        }
    };

    const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;

        setIsUploading(true);
        setError('');
        setUploadSuccess('');

        const formData = new FormData();
        formData.append('file', file);

        try {
            await api.post(`/portfolios/${portfolio_id}/upload`, formData, {
                headers: {
                    'Content-Type': 'multipart/form-data',
                },
            });
            setUploadSuccess('Transactions successfully ingested and market data synced.');
            fetchData();
        } catch (err: any) {
            let errorMsg = 'Failed to upload CSV.';
            if (err.response?.data?.detail) {
                if (typeof err.response.data.detail === 'string') {
                    errorMsg = err.response.data.detail;
                } else if (err.response.data.detail.message) {
                    errorMsg = err.response.data.detail.message;
                }
            }
            setError(errorMsg);
        } finally {
            setIsUploading(false);
            e.target.value = '';
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
                        {error}
                    </div>
                )}
                {uploadSuccess && (
                    <div className="mb-6 p-4 bg-green-50 text-green-700 rounded-md border border-green-200">
                        {uploadSuccess}
                    </div>
                )}

                <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
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
                            <h3 className="text-lg font-semibold text-gray-900 flex items-center mb-4">
                                <UploadCloud className="w-5 h-5 mr-2 text-blue-600" /> Data Ingestion
                            </h3>
                            <p className="text-sm text-gray-500 mb-4">
                                Upload a broker CSV to sync transaction ledgers.
                            </p>
                            <label className="flex flex-col items-center justify-center w-full h-32 border-2 border-gray-300 border-dashed rounded-lg cursor-pointer bg-gray-50 hover:bg-gray-100 transition-colors relative">
                                <div className="flex flex-col items-center justify-center pt-5 pb-6">
                                    {isUploading ? (
                                        <Loader2 className="w-8 h-8 animate-spin text-blue-600" />
                                    ) : (
                                        <>
                                            <UploadCloud className="w-8 h-8 text-gray-400 mb-2" />
                                            <p className="text-sm text-gray-500 font-medium">Click to upload CSV</p>
                                        </>
                                    )}
                                </div>
                                <input
                                    type="file"
                                    accept=".csv"
                                    className="hidden"
                                    onChange={handleFileUpload}
                                    disabled={isUploading}
                                />
                            </label>
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
                        formatter={(value: number) => [formatCurrency(value), 'Valuation']}
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
