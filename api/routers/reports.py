import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from db.session import get_db
from domain import models, schemas
from engine.math_core.tax_engine import FIFOTaxEngine

router = APIRouter()

@router.get(
    "/{portfolio_id}/tax-report",
    response_model=schemas.TaxReportResponse,
    summary="Generate FIFO Tax Report",
    description="""
    Instantiates the quantitative math engine to process the portfolio's transaction ledger.
    Applies strict FIFO matching to calculate realized Short-Term and Long-Term Capital Gains.
    """
)
def generate_tax_report(portfolio_id: uuid.UUID, db: Session = Depends(get_db)):
    # 1. Verify Portfolio
    portfolio = db.query(models.Portfolio).filter(models.Portfolio.id == portfolio_id).first()
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found.")

    # 2. Execute the Math Engine
    try:
        engine = FIFOTaxEngine(db_session=db, portfolio_id=str(portfolio_id))
        report_data = engine.compute_realized_gains()
    except ValueError as e:
        # Catch any ledger corruption errors (e.g., selling unowned shares)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Engine calculation failed.")

    # 3. Return strictly typed Pydantic response
    return schemas.TaxReportResponse(
        portfolio_id=portfolio_id,
        realized_stcg=report_data["realized_stcg"],
        realized_ltcg=report_data["realized_ltcg"],
        current_holdings=report_data["current_holdings"]
    )
