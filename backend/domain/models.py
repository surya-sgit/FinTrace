import uuid
from datetime import datetime
from sqlalchemy import Column, String, Numeric, DateTime, Date, ForeignKey, BigInteger, UniqueConstraint, Float, Integer
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func
from sqlalchemy.ext.compiler import compiles

@compiles(BigInteger, "sqlite")
def compile_bigint_sqlite(type_, compiler, **kw):
    return "INTEGER"

@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"

Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    portfolios = relationship("Portfolio", back_populates="owner")


class Portfolio(Base):
    __tablename__ = "portfolios"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    name = Column(String(128), nullable=False)
    tax_jurisdiction = Column(String(8), default="IN")
    created_at = Column(DateTime, default=datetime.utcnow)

    owner = relationship("User", back_populates="portfolios")
    transactions = relationship("TransactionLedger", back_populates="portfolio")
    snapshots = relationship("PortfolioSnapshot", back_populates="portfolio")


class TransactionLedger(Base):
    __tablename__ = "transaction_ledger"
    """
    Append-only ledger. Records are never updated or deleted directly.
    """
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    portfolio_id = Column(UUID(as_uuid=True), ForeignKey("portfolios.id"), nullable=False)
    ticker = Column(String(128), index=True, nullable=False) # ticker, ISIN, or MF scheme name
    transaction_type = Column(String(16), nullable=False)  # BUY, SELL, DIVIDEND

    # Precision numeric scales to prevent binary floating-point issues
    quantity = Column(Numeric(18, 4), nullable=False)
    price_per_unit = Column(Numeric(18, 4), nullable=False)
    brokerage_fees = Column(Numeric(10, 2), default=0.00)

    # Tax routing class: EQUITY (stocks/equity funds) | EQUITY_MF | DEBT_MF | HYBRID_MF | OTHER_MF
    asset_class = Column(String(16), nullable=False, server_default="EQUITY", default="EQUITY")

    execution_date = Column(Date, nullable=False)   # For FIFO tracking
    settlement_date = Column(Date, nullable=False)  # For corporate action mapping

    sequence_number = Column(Integer, default=0, nullable=False)
    checksum = Column(String(64), unique=True, nullable=False) # Idempotency guard

    portfolio = relationship("Portfolio", back_populates="transactions")


class CalculationEngine(Base):
    __tablename__ = "calculation_engines"
    """
    Tracks metadata regarding the current state of the math formulas
    and libraries used to verify absolute auditability.
    """
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engine_version = Column(String(32), nullable=False)    # e.g., 'v1.0.0'
    math_library_specs = Column(JSONB, nullable=False)      # e.g., {"pyxirr": "0.2.1"}
    tax_method = Column(String(16), default="FIFO")
    created_at = Column(DateTime, default=datetime.utcnow)


class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"
    """
    Immutable frozen snapshot of the calculation engine output.
    """
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    portfolio_id = Column(UUID(as_uuid=True), ForeignKey("portfolios.id"), nullable=False)
    calculation_engine_id = Column(UUID(as_uuid=True), ForeignKey("calculation_engines.id"), nullable=False)
    snapshot_timestamp = Column(DateTime, default=datetime.utcnow)

    total_invested_value = Column(Numeric(18, 4), nullable=False)
    total_current_value = Column(Numeric(18, 4), nullable=False)
    net_absolute_return = Column(Numeric(18, 4), nullable=False)

    tax_metrics = Column(JSONB, nullable=False)      # Realized STCG, LTCG parameters
    performance_metrics = Column(JSONB, nullable=False)  # XIRR, Sharpe, Max Drawdown

    portfolio = relationship("Portfolio", back_populates="snapshots")


class PortfolioPositionSnapshot(Base):
    __tablename__ = "portfolio_position_snapshots"
    """
    Daily materialized view of asset quantities to prevent O(N) ledger replay.
    """
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    portfolio_id = Column(UUID(as_uuid=True), ForeignKey("portfolios.id"), nullable=False)
    snapshot_date = Column(Date, nullable=False, index=True)
    
    # Store ticker -> quantity mappings (e.g. {"TCS.NS": "100.0000"})
    positions = Column(JSONB, nullable=False) 

    __table_args__ = (
        UniqueConstraint('portfolio_id', 'snapshot_date', name='uq_portfolio_snapshot_date'),
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    action_type = Column(String(64), nullable=False)      # e.g., 'CSV_UPLOAD_INITIATED'
    target_entity = Column(String(64), nullable=False)     # e.g., 'transaction_ledger'
    target_entity_id = Column(UUID(as_uuid=True), nullable=False)
    state_differential = Column(JSONB, nullable=False)     # Historical state modifications
    created_at = Column(DateTime, default=datetime.utcnow)



class AssetPrices(Base):
    __tablename__ = "asset_prices"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    ticker = Column(String(32), index=True, nullable=False)
    price_date = Column(Date, index=True, nullable=False)

    open_price = Column(Numeric(18, 4), nullable=False)
    high_price = Column(Numeric(18, 4), nullable=False)
    low_price = Column(Numeric(18, 4), nullable=False)
    close_price = Column(Numeric(18, 4), nullable=False)
    adjusted_close = Column(Numeric(18, 4), nullable=False)
    volume = Column(BigInteger, nullable=False)

    # Ensure we never insert duplicate prices for the same ticker on the same day
    __table_args__ = (
        UniqueConstraint('ticker', 'price_date', name='uq_ticker_date'),
    )


class MarketPrice(Base):
    __tablename__ = "market_prices"

    # We use the ticker as the primary key since we only need the latest price
    ticker = Column(String, primary_key=True, index=True)
    current_price = Column(Float, nullable=False)
    
    # Automatically updates the timestamp whenever the price changes
    last_updated = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    data_source = Column(String, nullable=False, default="YFINANCE")

class BehavioralAnalysisSnapshot(Base):
    __tablename__ = "behavioral_analysis_snapshots"
    """
    Stores pre-computed behavioral trading analytics (Disposition Effect, Momentum Bias, etc).
    """
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    portfolio_id = Column(UUID(as_uuid=True), ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False)
    snapshot_date = Column(Date, nullable=False, default=datetime.utcnow)

    # Metrics
    disposition_ratio = Column(Float, nullable=False, default=0.0)
    momentum_bias_score = Column(Float, nullable=False, default=0.0)
    revenge_trade_count = Column(Integer, nullable=False, default=0)
    panic_sell_score = Column(Float, nullable=False, default=0.0)
    endowment_trap_count = Column(Integer, nullable=False, default=0)

    # Phase 3 & 4 additions
    churn_rate = Column(Float, nullable=False, default=0.0)
    win_rate = Column(Float, nullable=False, default=0.0)
    winner_avg_capital = Column(Float, nullable=False, default=0.0)
    loser_avg_capital = Column(Float, nullable=False, default=0.0)
    holding_period_variance = Column(Float, nullable=False, default=0.0)
    overconfidence_bias_count = Column(Integer, nullable=False, default=0)
    dividend_trap_count = Column(Integer, nullable=False, default=0)
    bandwagon_bias_count = Column(Integer, nullable=False, default=0)
    market_timing_futility_delta = Column(Float, nullable=False, default=0.0)
    boredom_trade_count = Column(Integer, nullable=False, default=0)
    
    # Detailed granular trace data for rendering charts and exposing specific trades
    detailed_metrics = Column(JSONB, nullable=False, default=dict)

    # Ensure one snapshot per portfolio
    __table_args__ = (
        UniqueConstraint('portfolio_id', name='uq_behavioral_portfolio_id'),
    )


class AssetMetadata(Base):
    __tablename__ = "asset_metadata"
    """
    Maps tickers to their respective macroeconomic sectors and industries for Brinson-Fachler attribution.
    """
    ticker = Column(String(32), primary_key=True, index=True)
    sector = Column(String(64), nullable=False)   # e.g., 'Information Technology'
    industry = Column(String(64), nullable=False) # e.g., 'Software & Services'


class BenchmarkIndex(Base):
    __tablename__ = "benchmark_index"
    """
    Stores historical daily or monthly sector weights and returns for a macro benchmark (e.g., Nifty 500).
    """
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    benchmark_name = Column(String(64), index=True, nullable=False)
    price_date = Column(Date, index=True, nullable=False)
    
    sector = Column(String(64), nullable=False)
    sector_weight = Column(Numeric(18, 4), nullable=False)  # Weight of the sector in the index (e.g. 0.15 for 15%)
    sector_return = Column(Numeric(18, 4), nullable=False)  # Return of the sector over the period
    is_tri = Column(String(5), default="True") 

    __table_args__ = (
        UniqueConstraint('benchmark_name', 'price_date', 'sector', name='uq_benchmark_date_sector'),
    )


class CorporateActionEvent(Base):
    __tablename__ = "corporate_action_events"
    """
    Tracks structural corporate actions (SPLIT, BONUS) that require historical price and quantity adjustments.
    """
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticker = Column(String(32), index=True, nullable=False)
    ex_date = Column(Date, index=True, nullable=False)
    action_type = Column(String(16), nullable=False) # 'SPLIT' or 'BONUS'
    adjustment_factor = Column(Numeric(18, 4), nullable=False) # e.g. 10.0 for a 1:10 split

    __table_args__ = (
        UniqueConstraint('ticker', 'ex_date', 'action_type', name='uq_corp_action_ticker_date'),
    )


class PortfolioRiskSnapshot(Base):
    """
    Cached risk metrics for a portfolio.
    Computed once and served from DB on subsequent requests.
    Invalidated (deleted) whenever new transactions are uploaded.
    TTL-based re-computation: if computed_at is older than CACHE_TTL_HOURS, recompute.
    """
    __tablename__ = "portfolio_risk_snapshots"

    portfolio_id = Column(UUID(as_uuid=True), ForeignKey("portfolios.id"), primary_key=True)
    computed_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)

    alpha = Column(Numeric(18, 6), nullable=False, default=0)
    beta = Column(Numeric(18, 6), nullable=False, default=1)
    max_drawdown = Column(Numeric(18, 6), nullable=False, default=0)
    annualised_volatility = Column(Numeric(18, 6), nullable=False, default=0)
    sharpe_ratio = Column(Numeric(18, 4), nullable=False, default=0)
    sortino_ratio = Column(Numeric(18, 4), nullable=False, default=0)
    holding_periods = Column(JSONB, nullable=False, default=list)

