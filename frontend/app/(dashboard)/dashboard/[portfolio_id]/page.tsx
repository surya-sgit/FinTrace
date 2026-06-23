'use client';

import { useState, use } from 'react';
import { useRouter } from 'next/navigation';
import { ArrowLeft, Loader2 } from 'lucide-react';

import { usePortfolioData } from '@/hooks/usePortfolioData';
import { useUpload } from '@/hooks/useUpload';

import { OverviewTab } from '@/components/portfolio/OverviewTab';
import { ShortTermTab } from '@/components/portfolio/ShortTermTab';
import { LongTermTab } from '@/components/portfolio/LongTermTab';
import api from '@/lib/api';

export default function PortfolioDetailPage({ params }: { params: Promise<{ portfolio_id: string }> }) {
    const router = useRouter();
    const resolvedParams = use(params);
    const { portfolio_id } = resolvedParams;

    const [selectedDate, setSelectedDate] = useState<string>(new Date().toISOString().split('T')[0]);
    const [activeTab, setActiveTab] = useState<'overview' | 'short-term' | 'long-term'>('overview');
    const [isDownloading, setIsDownloading] = useState(false);
    const [downloadError, setDownloadError] = useState('');

    // Fetch portfolio analytics
    const {
        portfolio, xirrReport, taxReport, isLoading, error,
        attributionData, isAttributionLoading, attributionError,
        ltData, isLtLoading, ltError,
        riskMetrics, isRiskLoading, riskError,
        refetch
    } = usePortfolioData(portfolio_id, selectedDate);

    // Upload transaction logic
    const {
        isUploading, uploadError, uploadSuccess, uploadRowErrors,
        selectedFile, pdfPassword, setPdfPassword,
        handleFileSelect, processUpload
    } = useUpload(portfolio_id, refetch);

    const handleDownloadTaxReport = async () => {
        setIsDownloading(true);
        setDownloadError('');
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
            setDownloadError('Failed to download tax report.');
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

    const combinedError = error || uploadError || downloadError;

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
                {combinedError && (
                    <div className="mb-6 p-4 bg-red-50 text-red-700 rounded-md border border-red-200">
                        <p>{combinedError}</p>
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
                    <OverviewTab 
                        portfolio={portfolio}
                        xirrReport={xirrReport}
                        taxReport={taxReport}
                        ltData={ltData}
                        isUploading={isUploading}
                        uploadSuccess={uploadSuccess}
                        uploadRowErrors={uploadRowErrors}
                        selectedFile={selectedFile}
                        pdfPassword={pdfPassword}
                        setPdfPassword={setPdfPassword}
                        handleFileSelect={handleFileSelect}
                        processUpload={processUpload}
                        handleDownloadTaxReport={handleDownloadTaxReport}
                        isDownloading={isDownloading}
                    />
                )}

                {activeTab === 'short-term' && (
                    <ShortTermTab 
                        attributionData={attributionData}
                        isAttributionLoading={isAttributionLoading}
                        attributionError={attributionError}
                        selectedDate={selectedDate}
                        setSelectedDate={setSelectedDate}
                    />
                )}

                {activeTab === 'long-term' && (
                    <LongTermTab
                        ltData={ltData}
                        isLtLoading={isLtLoading}
                        ltError={ltError}
                        riskMetrics={riskMetrics}
                        isRiskLoading={isRiskLoading}
                        riskError={riskError}
                    />
                )}
            </main>
        </div>
    );
}
