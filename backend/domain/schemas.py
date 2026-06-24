from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator, ConfigDict
from decimal import Decimal
from datetime import date, datetime
from enum import Enum
from typing import Dict, Optional, List
import uuid

# ---------------------------------------------------------
# Enums for Strict Type Enforcement
# ---------------------------------------------------------
class TransactionType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    DIVIDEND = "DIVIDEND"
    DEPOSIT = "DEPOSIT"
    WITHDRAWAL = "WITHDRAWAL"

class TaxJurisdiction(str, Enum):
    IN = "IN"
    US = "US"

# ---------------------------------------------------------
# User Validation Schemas
# ---------------------------------------------------------
class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, description="Must be at least 8 characters")

class UserResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    created_at: datetime

    class Config:
        from_attributes = True

# ---------------------------------------------------------
# Portfolio Validation Schemas
# ---------------------------------------------------------
class PortfolioCreate(BaseModel):
    name: str = Field(
        ...,
        min_length=3,
        max_length=128,
        description="The display name of the portfolio used for reporting.",
        examples=["Long-term Wealth", "Retirement Fund 2050"]
    )
    tax_jurisdiction: TaxJurisdiction = Field(
        default=TaxJurisdiction.IN,
        description="The regulatory region dictating capital gains computation."
    )

class PortfolioResponse(BaseModel):
    id: uuid.UUID = Field(description="The unique system identifier for the portfolio.")
    user_id: uuid.UUID = Field(description="The ID of the user who owns this portfolio.")
    name: str = Field(description="The display name.")
    tax_jurisdiction: TaxJurisdiction = Field(description="The applied tax region.")
    created_at: datetime = Field(description="The UTC timestamp of creation.")

    model_config = ConfigDict(from_attributes=True)

# ---------------------------------------------------------
# Transaction Validation Schemas (The CSV Interface)
# ---------------------------------------------------------
class TransactionCreate(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=128, description="Exchange ticker, ISIN, or mutual-fund scheme name.")
    transaction_type: TransactionType
    quantity: Decimal = Field(..., gt=0, description="Must be greater than 0")
    price_per_unit: Decimal = Field(..., ge=0, description="Must be 0 or greater")
    brokerage_fees: Decimal = Field(default=Decimal('0.00'), ge=0)
    asset_class: str = Field(default="EQUITY", description="Tax routing class: EQUITY | EQUITY_MF | DEBT_MF | HYBRID_MF | OTHER_MF")
    execution_date: date
    settlement_date: Optional[date] = None

    @model_validator(mode='after')
    def validate_dates(self) -> 'TransactionCreate':
        """
        Ensures that settlement date is never logically before the execution date.
        If settlement_date is missing, it defaults to execution_date + 1 day for Indian Equities.
        """
        # Auto-fill settlement date if not provided (T+1 logic)
        if self.settlement_date is None:
            from datetime import timedelta
            self.settlement_date = self.execution_date + timedelta(days=1)

        if self.execution_date > self.settlement_date:
            raise ValueError("Execution date cannot be after settlement date.")
        return self

    @model_validator(mode='after')
    def validate_dividend_amount(self) -> 'TransactionCreate':
        """
        Dividend income is computed everywhere as quantity x price_per_unit. A zero
        per-share value therefore silently records a zero dividend, so reject it with
        an actionable message instead of accepting a meaningless row.
        """
        if self.transaction_type == TransactionType.DIVIDEND and self.price_per_unit <= 0:
            raise ValueError(
                "Dividend rows must record the dividend-per-share in 'price_per_unit' "
                "(total dividend = quantity x price_per_unit). A value of 0 was provided."
            )
        return self

class TransactionResponse(TransactionCreate):
    id: uuid.UUID
    portfolio_id: uuid.UUID
    checksum: str

    class Config:
        from_attributes = True


# ---------------------------------------------------------
# Report Validation Schemas
# ---------------------------------------------------------
class FinancialYearTax(BaseModel):
    financial_year: str = Field(..., description="Indian FY label, e.g. '2024-25'.")
    gross_stcg: Decimal = Field(..., description="Net short-term capital gain before set-off.")
    gross_ltcg: Decimal = Field(..., description="Net long-term capital gain before set-off.")
    taxable_stcg: Decimal = Field(..., description="STCG remaining after loss set-off.")
    taxable_ltcg: Decimal = Field(..., description="LTCG remaining after set-off and exemption.")
    ltcg_exemption_applied: Decimal = Field(..., description="Sec 112A annual exemption used this FY.")
    stcg_tax: Decimal = Field(..., description="Tax on STCG (Sec 111A).")
    ltcg_tax: Decimal = Field(..., description="Tax on LTCG (Sec 112A).")
    noneq_ltcg_gain: Decimal = Field(default=Decimal("0.00"), description="Non-equity (debt/hybrid) LTCG taxable @12.5%.")
    noneq_ltcg_tax: Decimal = Field(default=Decimal("0.00"), description="Tax on non-equity LTCG @12.5%.")
    slab_taxable_gain: Decimal = Field(default=Decimal("0.00"), description="Non-equity gain taxed at the investor's slab (reported, not rupee-computed).")
    total_tax: Decimal = Field(..., description="Total capital-gains tax for the FY (excludes slab-rate gains).")
    dividend_income: Decimal = Field(default=Decimal("0.00"), description="Dividends received (taxable at slab).")
    stcg_loss_carried_forward: Decimal = Field(default=Decimal("0.00"), description="Unabsorbed ST loss carried forward.")
    ltcg_loss_carried_forward: Decimal = Field(default=Decimal("0.00"), description="Unabsorbed LT loss carried forward.")


class TaxLotDetail(BaseModel):
    ticker: str
    asset_class: str = Field(default="EQUITY", description="EQUITY | EQUITY_MF | DEBT_MF | HYBRID_MF | OTHER_MF")
    buy_date: date
    sell_date: date
    quantity: Decimal
    cost_basis: Decimal = Field(..., description="Cost of acquisition incl. brokerage (and grandfathered FMV if applicable).")
    proceeds: Decimal = Field(..., description="Sale value net of brokerage.")
    gain: Decimal
    is_long_term: bool
    grandfathered: bool = Field(default=False, description="Whether Sec 112A FMV step-up was applied.")


class TaxReportResponse(BaseModel):
    portfolio_id: uuid.UUID
    # Backward-compatible aggregate fields (consumed by the existing dashboard).
    realized_stcg: Decimal = Field(..., description="Net realized Short-Term Capital Gains (held <= 12 months).")
    realized_ltcg: Decimal = Field(..., description="Net realized Long-Term Capital Gains (held > 12 months).")
    current_holdings: Dict[str, Decimal] = Field(..., description="Map of tickers and their remaining unsold quantities")
    # File-ready detail.
    financial_years: List[FinancialYearTax] = Field(default=[], description="Per-FY tax computation with set-off, exemption and carry-forward.")
    total_tax_payable: Decimal = Field(default=Decimal("0.00"), description="Total capital-gains tax across all financial years (excludes slab-rate gains).")
    slab_taxable_gain: Decimal = Field(default=Decimal("0.00"), description="Total non-equity gain taxed at the investor's slab (reported, apply your slab rate).")
    lots: List[TaxLotDetail] = Field(default=[], description="Lot-level realized gain rows (FIFO matched).")

    class Config:
        from_attributes = True


class ConsolidatedPortfolioSummary(BaseModel):
    portfolio_id: str
    name: str
    invested: float
    current_value: float
    xirr_percentage: float


class ConsolidatedResponse(BaseModel):
    total_net_worth: float = Field(..., description="Total current value across all portfolios.")
    total_invested: float
    total_current_value: float
    unrealized_pl: float
    blended_xirr: float = Field(..., description="Capital-weighted average XIRR across portfolios.")
    equity_value: float = Field(..., description="Current value held in equities / equity funds.")
    mutual_fund_value: float = Field(..., description="Current value held in non-equity mutual funds.")
    portfolio_count: int
    portfolios: List[ConsolidatedPortfolioSummary] = Field(default=[])


class HistoricalValuationPoint(BaseModel):
    date: str
    valuation: float

class HoldingValue(BaseModel):
    ticker: str
    quantity: float
    market_value: float
    asset_class: str = "EQUITY"


class XIRRReportResponse(BaseModel):
    portfolio_id: uuid.UUID
    xirr_percentage: float = Field(..., description="Annualized portfolio return rate as a percentage.")
    total_invested_capital: float = Field(..., description="Absolute sum of all capital deployed (includes brokerage).")
    current_market_value: float = Field(..., description="Value of all remaining holdings at the most recent cached market price.")
    valuation_history: List[HistoricalValuationPoint] = Field(default=[], description="Historical sequence of portfolio valuation")
    holdings: List[HoldingValue] = Field(default=[], description="Per-holding current market value for allocation.")

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "portfolio_id": "123e4567-e89b-12d3-a456-426614174000",
                "xirr_percentage": 14.25,
                "total_invested_capital": 55000.00,
                "current_market_value": 68500.50
            }
        }
    )


# ---------------------------------------------------------
# Security & Authentication Schemas
# ---------------------------------------------------------
class UserCreate(BaseModel):
    email: str = Field(..., description="A valid email address.")
    password: str = Field(..., min_length=8, description="Strong password (minimum 8 characters).")

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    user_id: str | None = None

# ---------------------------------------------------------
# Analytics Schemas
# ---------------------------------------------------------
class DragContribution(BaseModel):
    ticker: str
    shares_held: Decimal
    legacy_drift: Decimal
    intraday_impact: Decimal
    corporate_shield: Decimal
    net_contribution: Decimal

class PerformanceAttributionResponse(BaseModel):
    analysis_date: str
    primary_drag_ticker: Optional[str] = None
    absolute_impact: Decimal
    full_contribution_matrix: List[DragContribution]

class OrganicVariationResponse(BaseModel):
    ticker: str
    net_organic_contribution: Decimal

class BrinsonFachlerResponse(BaseModel):
    sector: str
    allocation_effect: Decimal
    selection_effect: Decimal
    interaction_effect: Decimal

class MWRSlicingResponse(BaseModel):
    ticker: str
    standalone_xirr: float
    mwr_contribution: Decimal

class LongTermAttributionResponse(BaseModel):
    portfolio_id: uuid.UUID
    start_date: date
    end_date: date
    organic_variation: List[OrganicVariationResponse]
    brinson_fachler: List[BrinsonFachlerResponse]
    mwr_slicing: List[MWRSlicingResponse]
    is_synthetic_cash_proxy: bool = False

class BehavioralAnalysisResponse(BaseModel):
    portfolio_id: uuid.UUID
    snapshot_date: date
    disposition_ratio: float
    momentum_bias_score: float
    revenge_trade_count: int
    panic_sell_score: float
    endowment_trap_count: int
    churn_rate: float
    win_rate: float
    winner_avg_capital: float
    loser_avg_capital: float
    holding_period_variance: float
    overconfidence_bias_count: int
    dividend_trap_count: int
    bandwagon_bias_count: int
    market_timing_futility_delta: float
    boredom_trade_count: int
    detailed_metrics: dict

    class Config:
        from_attributes = True


# ---------------------------------------------------------
# Risk Metrics Schemas
# ---------------------------------------------------------
class HoldingPeriodRow(BaseModel):
    ticker: str
    avg_holding_days: float
    max_holding_days: int
    open_position_qty: float
    is_still_held: bool


class RiskMetricsResponse(BaseModel):
    portfolio_id: str
    start_date: date
    end_date: date
    alpha: float
    beta: float
    max_drawdown: float
    annualised_volatility: float
    sharpe_ratio: float
    sortino_ratio: float
    holding_periods: List[HoldingPeriodRow]
