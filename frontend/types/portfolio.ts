export interface Portfolio {
    id: string;
    name: string;
    tax_jurisdiction: string;
    created_at: string;
}

export interface ValuationPoint {
    date: string;
    valuation: number;
}

export interface XIRRReport {
    xirr_percentage: number;
    total_invested_capital: number;
    current_market_value: number;
    valuation_history?: ValuationPoint[];
}

export interface FinancialYearTax {
    financial_year: string;
    gross_stcg: number;
    gross_ltcg: number;
    taxable_stcg: number;
    taxable_ltcg: number;
    ltcg_exemption_applied: number;
    stcg_tax: number;
    ltcg_tax: number;
    total_tax: number;
    dividend_income: number;
    stcg_loss_carried_forward: number;
    ltcg_loss_carried_forward: number;
}

export interface TaxLotDetail {
    ticker: string;
    buy_date: string;
    sell_date: string;
    quantity: number;
    cost_basis: number;
    proceeds: number;
    gain: number;
    is_long_term: boolean;
    grandfathered: boolean;
}

export interface TaxReport {
    realized_stcg: number;
    realized_ltcg: number;
    current_holdings: Record<string, number>;
    financial_years?: FinancialYearTax[];
    total_tax_payable?: number;
    lots?: TaxLotDetail[];
}

export interface DragRow {
    ticker: string;
    shares_held: number;
    legacy_drift: number;
    intraday_impact: number;
    corporate_shield: number;
    net_contribution: number;
}

export interface AttributionReport {
    analysis_date: string;
    primary_drag_ticker: string | null;
    absolute_impact: number;
    full_contribution_matrix: DragRow[];
}

export interface OrganicVariationRow {
    ticker: string;
    net_organic_contribution: number;
}

export interface BrinsonFachlerRow {
    sector: string;
    allocation_effect: number;
    selection_effect: number;
    interaction_effect: number;
}

export interface MWRSlicingRow {
    ticker: string;
    standalone_xirr: number;
    mwr_contribution: number;
}

export interface LongTermAttributionReport {
    portfolio_id: string;
    start_date: string;
    end_date: string;
    organic_variation: OrganicVariationRow[];
    brinson_fachler: BrinsonFachlerRow[];
    mwr_slicing: MWRSlicingRow[];
    is_synthetic_cash_proxy: boolean;
}

export interface HoldingPeriodRow {
    ticker: string;
    avg_holding_days: number;
    max_holding_days: number;
    open_position_qty: number;
    is_still_held: boolean;
}

export interface RiskMetricsReport {
    portfolio_id: string;
    start_date: string;
    end_date: string;
    alpha: number;
    beta: number;
    max_drawdown: number;
    annualised_volatility: number;
    sharpe_ratio: number;
    sortino_ratio: number;
    holding_periods: HoldingPeriodRow[];
}

export interface BehavioralTrade {
    ticker: string;
    days_held: number;
    alpha: number;
    buy_date: string;
    sell_date: string;
    trade_ret: number;
    bench_ret: number;
    capital_invested?: number;
}

export interface BehavioralDetailedMetrics {
    total_buys: number;
    panic_sells: number;
    momentum_buys: number;
    revenge_trades: number;
    endowment_traps: number;
    win_rate_percent: number;
    loser_avg_capital: number;
    churn_rate_percent: number;
    winner_avg_capital: number;
    avg_loser_hold_days: number;
    boredom_trade_count: number;
    dividend_trap_count: number;
    total_closed_trades: number;
    avg_winner_hold_days: number;
    bandwagon_bias_count: number;
    holding_period_variance: number;
    overconfidence_bias_count: number;
    market_timing_futility_delta: number;
    trades: BehavioralTrade[];
}

export interface BehavioralAnalysisReport {
    portfolio_id: string;
    snapshot_date: string;
    disposition_ratio: number;
    momentum_bias_score: number;
    revenge_trade_count: number;
    panic_sell_score: number;
    endowment_trap_count: number;
    churn_rate: number;
    win_rate: number;
    winner_avg_capital: number;
    loser_avg_capital: number;
    holding_period_variance: number;
    overconfidence_bias_count: number;
    dividend_trap_count: number;
    bandwagon_bias_count: number;
    market_timing_futility_delta: number;
    boredom_trade_count: number;
    detailed_metrics: BehavioralDetailedMetrics;
}
