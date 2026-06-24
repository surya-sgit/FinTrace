import { useState, useEffect } from 'react';
import api from '@/lib/api';
import { getErrorMessage } from '@/lib/errors';
import {
    Portfolio,
    XIRRReport,
    TaxReport,
    AttributionReport,
    LongTermAttributionReport,
    RiskMetricsReport,
    BehavioralAnalysisReport
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

    const [behavioralData, setBehavioralData] = useState<BehavioralAnalysisReport | null>(null);
    const [isBehavioralLoading, setIsBehavioralLoading] = useState(false);
    const [behavioralError, setBehavioralError] = useState('');

    useEffect(() => {
        if (portfolioId) {
            fetchData();
        }
    }, [portfolioId, selectedDate]);

    const fetchData = async () => {
        setIsLoading(true);
        setError('');
        setIsAttributionLoading(true);
        setIsLtLoading(true);
        setIsRiskLoading(true);
        setIsBehavioralLoading(true);
        setAttributionError('');
        setLtError('');
        setRiskError('');
        setBehavioralError('');

        try {
            // 1. Fire Portfolio Details fetch without blocking others
            const fetchPortfolio = async () => {
                try {
                    const portRes = await api.get(`/portfolios/${portfolioId}`);
                    setPortfolio(portRes.data);
                } catch (err: any) {
                    setError(getErrorMessage(err, 'Failed to fetch portfolio details.'));
                } finally {
                    setIsLoading(false);
                }
            };

            const fetchReports = async () => {
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
            };

            const fetchAttribution = async () => {
                try {
                    const attrRes = await api.get(`/analytics/${portfolioId}/attribution?target_date=${selectedDate}`);
                    setAttributionData(attrRes.data);
                } catch (err: any) {
                    setAttributionError(getErrorMessage(err, 'Failed to load attribution data.'));
                    setAttributionData(null);
                } finally {
                    setIsAttributionLoading(false);
                }
            };

            const fetchLt = async () => {
                try {
                    const ltRes = await api.get(`/analytics/${portfolioId}/long-term-attribution`);
                    setLtData(ltRes.data);
                } catch (err: any) {
                    setLtError('Failed to load long term analytics.');
                } finally {
                    setIsLtLoading(false);
                }
            };

            const fetchRisk = async () => {
                try {
                    const riskRes = await api.get(`/analytics/${portfolioId}/risk-metrics`);
                    setRiskMetrics(riskRes.data);
                } catch (err: any) {
                    setRiskError('Failed to load risk metrics.');
                } finally {
                    setIsRiskLoading(false);
                }
            };

            const fetchBehavioral = async () => {
                try {
                    const behavRes = await api.get(`/analytics/${portfolioId}/behavioral`);
                    setBehavioralData(behavRes.data);
                } catch (err: any) {
                    setBehavioralError('Failed to load behavioral analytics.');
                } finally {
                    setIsBehavioralLoading(false);
                }
            };

            // Execute all analytics fetches in parallel
            await Promise.allSettled([
                fetchPortfolio(),
                fetchReports(),
                fetchAttribution(),
                fetchLt(),
                fetchRisk(),
                fetchBehavioral()
            ]);


        } catch (err: any) {
            setError(getErrorMessage(err, 'Failed to load portfolio details.'));
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
        behavioralData,
        isBehavioralLoading,
        behavioralError,
        refetch: fetchData
    };
}
