'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Briefcase, ArrowRight, Plus, LogOut, Loader2, X, Wallet, TrendingUp, PieChart, Trash2 } from 'lucide-react';
import api from '@/lib/api';
import { ConsolidatedView } from '@/types/portfolio';
import { getErrorMessage } from '@/lib/errors';

interface Portfolio {
    id: string;
    name: string;
    tax_jurisdiction: string;
    created_at: string;
}

export default function DashboardPage() {
    const router = useRouter();
    const [portfolios, setPortfolios] = useState<Portfolio[]>([]);
    const [consolidated, setConsolidated] = useState<ConsolidatedView | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState('');

    // New state variables for the Modal
    const [isModalOpen, setIsModalOpen] = useState(false);
    const [newName, setNewName] = useState('');
    const [newJurisdiction, setNewJurisdiction] = useState('IN'); // Changed from 'INDIA' to 'IN'
    const [isCreating, setIsCreating] = useState(false);

    useEffect(() => {
        fetchPortfolios();
    }, []);

    const fetchPortfolios = async () => {
        try {
            const response = await api.get('/portfolios/');
            setPortfolios(response.data);

            // Consolidated net-worth view (best-effort; don't block the list on it).
            try {
                const consRes = await api.get('/portfolios/consolidated');
                setConsolidated(consRes.data);
            } catch {
                setConsolidated(null);
            }
        } catch (err: any) {
            setError('Failed to load your financial data.');
        } finally {
            setIsLoading(false);
        }
    };

    const formatCurrency = (amount: number) =>
        `₹${Math.abs(amount).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;

    // The new function to handle form submission
    const handleCreatePortfolio = async (e: React.FormEvent) => {
        e.preventDefault();
        setIsCreating(true);
        setError('');

        try {
            await api.post('/portfolios/', {
                name: newName,
                tax_jurisdiction: newJurisdiction,
            });

            // Reset form and close modal
            setNewName('');
            setNewJurisdiction('INDIA');
            setIsModalOpen(false);

            // Instantly refresh the data so the new portfolio appears
            fetchPortfolios();
        } catch (err: any) {
            setError(getErrorMessage(err, 'Failed to create portfolio.'));
        } finally {
            setIsCreating(false);
        }
    };

    const [deletingId, setDeletingId] = useState<string | null>(null);

    const handleDeletePortfolio = async (id: string, name: string) => {
        if (!window.confirm(`Delete "${name}"? This permanently removes its ledger and reports and cannot be undone.`)) {
            return;
        }
        setDeletingId(id);
        setError('');
        try {
            await api.delete(`/portfolios/${id}`);
            await fetchPortfolios();
        } catch (err: any) {
            setError(getErrorMessage(err, 'Failed to delete portfolio.'));
        } finally {
            setDeletingId(null);
        }
    };

    const handleLogout = () => {
        localStorage.removeItem('fintrace_token');
        router.push('/login');
    };

    if (isLoading) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-gray-50">
                <Loader2 className="w-8 h-8 animate-spin text-blue-600" />
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-gray-50 relative">
            {/* Top Navigation */}
            <nav className="bg-white border-b border-gray-200 px-6 py-4 flex justify-between items-center">
                <div className="flex items-center space-x-2">
                    <Briefcase className="w-6 h-6 text-blue-600" />
                    <h1 className="text-xl font-bold text-gray-900">FinTrace Engine</h1>
                </div>
                <button onClick={handleLogout} className="flex items-center text-sm font-medium text-gray-600 hover:text-red-600 transition-colors">
                    <LogOut className="w-4 h-4 mr-2" />
                    Sign Out
                </button>
            </nav>

            {/* Main Content Area */}
            <main className="max-w-7xl mx-auto px-6 py-8">
                <div className="flex justify-between items-center mb-8">
                    <div>
                        <h2 className="text-2xl font-bold text-gray-900">Command Center</h2>
                        <p className="text-gray-500 mt-1">Manage your quantitative portfolios and tax ledgers.</p>
                    </div>
                    <button
                        onClick={() => setIsModalOpen(true)}
                        className="flex items-center bg-blue-600 text-white py-2 px-4 rounded-md hover:bg-blue-700 transition-colors font-medium"
                    >
                        <Plus className="w-4 h-4 mr-2" />
                        New Portfolio
                    </button>
                </div>

                {error && (
                    <div className="mb-6 p-4 bg-red-50 text-red-700 rounded-md border border-red-200">
                        {error}
                    </div>
                )}

                {consolidated && consolidated.portfolio_count > 0 && (
                    <div className="mb-8 bg-white border border-gray-200 rounded-lg p-6 shadow-sm">
                        <div className="flex items-center mb-4">
                            <Wallet className="w-5 h-5 mr-2 text-blue-600" />
                            <h3 className="text-lg font-semibold text-gray-900">Total Net Worth</h3>
                            <span className="ml-2 text-xs text-gray-400">across {consolidated.portfolio_count} portfolios</span>
                        </div>
                        <p className="text-3xl font-bold text-gray-900 mb-6">{formatCurrency(consolidated.total_net_worth)}</p>

                        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
                            <div>
                                <p className="text-xs text-gray-500">Invested</p>
                                <p className="text-lg font-semibold text-gray-900">{formatCurrency(consolidated.total_invested)}</p>
                            </div>
                            <div>
                                <p className="text-xs text-gray-500">Unrealized P&amp;L</p>
                                <p className={`text-lg font-semibold ${consolidated.unrealized_pl >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                                    {consolidated.unrealized_pl < 0 ? '-' : ''}{formatCurrency(consolidated.unrealized_pl)}
                                </p>
                            </div>
                            <div>
                                <p className="text-xs text-gray-500 flex items-center"><TrendingUp className="w-3 h-3 mr-1" /> Blended XIRR</p>
                                <p className={`text-lg font-semibold ${consolidated.blended_xirr >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                                    {consolidated.blended_xirr.toFixed(2)}%
                                </p>
                            </div>
                            <div>
                                <p className="text-xs text-gray-500 flex items-center"><PieChart className="w-3 h-3 mr-1" /> Current Value</p>
                                <p className="text-lg font-semibold text-gray-900">{formatCurrency(consolidated.total_current_value)}</p>
                            </div>
                        </div>

                        {/* Equity vs Mutual Fund split */}
                        {(consolidated.equity_value + consolidated.mutual_fund_value) > 0 && (
                            <div>
                                <div className="flex justify-between text-xs text-gray-500 mb-1">
                                    <span>Equity {formatCurrency(consolidated.equity_value)}</span>
                                    <span>Mutual Funds {formatCurrency(consolidated.mutual_fund_value)}</span>
                                </div>
                                <div className="flex h-2.5 rounded-full overflow-hidden bg-gray-100">
                                    <div
                                        className="bg-blue-600"
                                        style={{ width: `${(consolidated.equity_value / (consolidated.equity_value + consolidated.mutual_fund_value)) * 100}%` }}
                                    />
                                    <div
                                        className="bg-amber-500"
                                        style={{ width: `${(consolidated.mutual_fund_value / (consolidated.equity_value + consolidated.mutual_fund_value)) * 100}%` }}
                                    />
                                </div>
                            </div>
                        )}
                    </div>
                )}

                {portfolios.length === 0 && !error ? (
                    <div className="bg-white border border-gray-200 border-dashed rounded-lg p-12 text-center">
                        <Briefcase className="w-12 h-12 text-gray-400 mx-auto mb-4" />
                        <h3 className="text-lg font-medium text-gray-900 mb-2">No Portfolios Found</h3>
                        <p className="text-gray-500 max-w-sm mx-auto mb-6">
                            You haven't initialized any financial ledgers yet. Create a new portfolio to start tracking your XIRR and tax liabilities.
                        </p>
                        <button
                            onClick={() => setIsModalOpen(true)}
                            className="bg-white border border-gray-300 text-gray-700 py-2 px-4 rounded-md hover:bg-gray-50 transition-colors font-medium shadow-sm"
                        >
                            Initialize Portfolio
                        </button>
                    </div>
                ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                        {portfolios.map((portfolio) => (
                            <div key={portfolio.id} className="bg-white border border-gray-200 rounded-lg p-6 shadow-sm hover:shadow-md transition-shadow">
                                <div className="flex justify-between items-start mb-4">
                                    <h3 className="text-lg font-bold text-gray-900 truncate pr-4">{portfolio.name}</h3>
                                    <span className="px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800 shrink-0">
                                        {portfolio.tax_jurisdiction}
                                    </span>
                                </div>
                                <div className="text-sm text-gray-500 mb-6">
                                    Created: {new Date(portfolio.created_at).toLocaleDateString()}
                                </div>
                                <div className="flex items-center space-x-2">
                                    <button
                                        onClick={() => router.push(`/dashboard/${portfolio.id}`)}
                                        className="flex-1 flex items-center justify-center bg-gray-50 border border-gray-200 text-gray-700 py-2 rounded-md hover:bg-gray-100 transition-colors font-medium"
                                    >
                                        View Analytics <ArrowRight className="w-4 h-4 ml-2" />
                                    </button>
                                    <button
                                        onClick={() => handleDeletePortfolio(portfolio.id, portfolio.name)}
                                        disabled={deletingId === portfolio.id}
                                        title="Delete portfolio"
                                        aria-label="Delete portfolio"
                                        className="flex items-center justify-center p-2 border border-gray-200 text-gray-400 rounded-md hover:text-red-600 hover:border-red-200 hover:bg-red-50 transition-colors disabled:opacity-50"
                                    >
                                        {deletingId === portfolio.id ? <Loader2 className="w-4 h-4 animate-spin" /> : <Trash2 className="w-4 h-4" />}
                                    </button>
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </main>

            {/* Creation Modal Overlay */}
            {isModalOpen && (
                <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50">
                    <div className="bg-white rounded-lg shadow-xl w-full max-w-md p-6">
                        <div className="flex justify-between items-center mb-6">
                            <h3 className="text-xl font-bold text-gray-900">Initialize Ledger</h3>
                            <button onClick={() => setIsModalOpen(false)} className="text-gray-400 hover:text-gray-600">
                                <X className="w-5 h-5" />
                            </button>
                        </div>

                        <form onSubmit={handleCreatePortfolio} className="space-y-4">
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-1">Portfolio Name</label>
                                <input
                                    type="text"
                                    required
                                    value={newName}
                                    onChange={(e) => setNewName(e.target.value)}
                                    placeholder="e.g., Core Equity Holdings"
                                    className="w-full px-4 py-2 border border-gray-300 rounded-md text-gray-900 bg-white focus:ring-2 focus:ring-blue-500 outline-none"
                                />
                            </div>

                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-1">Tax Jurisdiction</label>
                                <select
                                    value={newJurisdiction}
                                    onChange={(e) => setNewJurisdiction(e.target.value)}
                                    className="w-full px-4 py-2 border border-gray-300 rounded-md text-gray-900 bg-white focus:ring-2 focus:ring-blue-500 outline-none"
                                >
                                    {/* Map the display text to the strict short-code tokens required by Pydantic */}
                                    <option value="IN">India (FIFO Standard)</option>
                                    <option value="US">United States</option>
                                </select>
                            </div>

                            <div className="pt-4 flex space-x-3">
                                <button
                                    type="button"
                                    onClick={() => setIsModalOpen(false)}
                                    className="flex-1 bg-white border border-gray-300 text-gray-700 py-2 rounded-md hover:bg-gray-50 transition-colors font-medium"
                                >
                                    Cancel
                                </button>
                                <button
                                    type="submit"
                                    disabled={isCreating}
                                    className="flex-1 bg-blue-600 text-white py-2 rounded-md hover:bg-blue-700 transition-colors font-medium disabled:opacity-70"
                                >
                                    {isCreating ? 'Creating...' : 'Create Portfolio'}
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}
        </div>
    );
}
