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
    ticker: str = Field(..., min_length=1, max_length=32)
    transaction_type: TransactionType
    quantity: Decimal = Field(..., gt=0, description="Must be greater than 0")
    price_per_unit: Decimal = Field(..., ge=0, description="Must be 0 or greater")
    brokerage_fees: Decimal = Field(default=Decimal('0.00'), ge=0)
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

class TransactionResponse(TransactionCreate):
    id: uuid.UUID
    portfolio_id: uuid.UUID
    checksum: str

    class Config:
        from_attributes = True


# ---------------------------------------------------------
# Report Validation Schemas
# ---------------------------------------------------------
class TaxReportResponse(BaseModel):
    portfolio_id: uuid.UUID
    realized_stcg: Decimal = Field(..., description="Total Short-Term Capital Gains (Held < 365 days)")
    realized_ltcg: Decimal = Field(..., description="Total Long-Term Capital Gains (Held >= 365 days)")
    current_holdings: Dict[str, Decimal] = Field(..., description="Map of tickers and their remaining unsold quantities")

    class Config:
        from_attributes = True


class XIRRReportResponse(BaseModel):
    portfolio_id: uuid.UUID
    xirr_percentage: float = Field(..., description="Annualized portfolio return rate as a percentage.")
    total_invested_capital: float = Field(..., description="Absolute sum of all capital deployed (includes brokerage).")
    current_market_value: float = Field(..., description="Value of all remaining holdings at the most recent cached market price.")

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
