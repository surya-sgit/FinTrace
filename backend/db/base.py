"""
Centralized metadata registry for SQLAlchemy.
Importing all models here ensures they are registered with the declarative Base
prior to table creation or Alembic migrations.
"""

from domain.models import Base
from domain.models import (
    User,
    Portfolio,
    TransactionLedger,
    CalculationEngine,
    PortfolioSnapshot,
    AuditLog,
    AssetPrices
)
