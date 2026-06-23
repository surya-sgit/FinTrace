import { Loader2, Activity, PieChart as PieChartIcon } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer, Legend } from 'recharts';
import { LongTermAttributionReport } from '@/types/portfolio';

interface LongTermTabProps {
    ltData: LongTermAttributionReport | null;
    isLtLoading: boolean;
    ltError: string;
}

export function LongTermTab({ ltData, isLtLoading, ltError }: LongTermTabProps) {
    return (
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
                                <RechartsTooltip formatter={(val: any) => `${(Number(val) * 100).toFixed(2)}%`} />
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
                                <RechartsTooltip formatter={(val: any) => `${(Number(val) * 100).toFixed(2)}%`} />
                                <Legend />
                                <Bar dataKey="standalone_xirr" fill="#3b82f6" name="Standalone XIRR" />
                            </BarChart>
                        </ResponsiveContainer>
                    </div>
                ) : null}
            </div>
        </div>
    );
}
