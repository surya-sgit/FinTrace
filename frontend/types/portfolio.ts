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

export interface TaxReport {
    realized_stcg: number;
    realized_ltcg: number;
    current_holdings: Record<string, number>;
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
