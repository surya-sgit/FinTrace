import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer } from 'recharts';

export interface ChartDataPoint {
    date: string;
    valuation: number;
}

interface PerformanceChartProps {
    data: ChartDataPoint[];
}

export function PerformanceChart({ data }: PerformanceChartProps) {
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
