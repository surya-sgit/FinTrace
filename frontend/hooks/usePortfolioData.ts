import { useState, useEffect } from 'react';
import api from '@/lib/api';
import {
    Portfolio,
    XIRRReport,
    TaxReport,
    AttributionReport,
    LongTermAttributionReport,
    RiskMetricsReport
} from '@/types/portfolio';

export function usePortfolioData(portfolioId: string, selectedDate: string) {
    const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
    const [xirrReport, setXirrReport] = useState<XIRRReport | null>(null);
    const [taxReport, setTaxReport] = useState<TaxReport | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState('');

    const [attributionData, setAttributionData] = useState<AttributionReport | null>(null);
    const [isAttributionLoading, setIsAttributionLoading] = useState(false);
    const [attributionError, setAttributionError] = useState('');

    const [ltData, setLtData] = useState<LongTermAttributionReport | null>(null);
    const [isLtLoading, setIsLtLoading] = useState(false);
    const [ltError, setLtError] = useState('');

    const [riskMetrics, setRiskMetrics] = useState<RiskMetricsReport | null>(null);
    const [isRiskLoading, setIsRiskLoading] = useState(false);
    const [riskError, setRiskError] = useState('');

    useEffect(() => {
        if (portfolioId) {
            fetchData();
        }
    }, [portfolioId, selectedDate]);

    const fetchData = async () => {
        setIsLoading(true);
        setError('');
        try {
            // 1. Fetch Portfolio Details
            const portRes = await api.get(`/portfolios/${portfolioId}`);
            setPortfolio(portRes.data);

            // 2. Fetch Analytics (Run in parallel if portfolio exists)
            try {
                const [xirrRes, taxRes] = await Promise.all([
                    api.get(`/portfolios/${portfolioId}/xirr-report`),
                    api.get(`/portfolios/${portfolioId}/tax-report`)
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
                const attrRes = await api.get(`/analytics/${portfolioId}/attribution?target_date=${selectedDate}`);
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
                const ltRes = await api.get(`/analytics/${portfolioId}/long-term-attribution`);
                setLtData(ltRes.data);
            } catch (err: any) {
                setLtError('Failed to load long term analytics.');
            } finally {
                setIsLtLoading(false);
            }

            // 5. Fetch Risk Metrics
            setIsRiskLoading(true);
            setRiskError('');
            try {
                const riskRes = await api.get(`/analytics/${portfolioId}/risk-metrics`);
                setRiskMetrics(riskRes.data);
            } catch (err: any) {
                setRiskError('Failed to load risk metrics.');
            } finally {
                setIsRiskLoading(false);
            }

        } catch (err: any) {
            setError(err.response?.data?.detail || 'Failed to load portfolio details.');
        } finally {
            setIsLoading(false);
        }
    };

    return {
        portfolio,
        xirrReport,
        taxReport,
        isLoading,
        error,
        attributionData,
        isAttributionLoading,
        attributionError,
        ltData,
        isLtLoading,
        ltError,
        riskMetrics,
        isRiskLoading,
        riskError,
        refetch: fetchData
    };
}
