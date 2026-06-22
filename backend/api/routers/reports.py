import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from db.session import get_db
from domain import models, schemas
from engine.math_core.tax_engine import FIFOTaxEngine
from engine.math_core.xirr_engine import XIRREngine
from api.dependencies import get_current_user
from engine.documents.pdf_generator import create_tax_pdf

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
def generate_tax_report(portfolio_id: uuid.UUID, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    # 1. Verify Portfolio
    portfolio = db.query(models.Portfolio).filter(models.Portfolio.id == portfolio_id, models.Portfolio.user_id == current_user.id).first()
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found or access denied.")

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


@router.get(
    "/{portfolio_id}/xirr-report",
    response_model=schemas.XIRRReportResponse,
    summary="Compute Annualized Performance (XIRR)",
    description="""
    Calculates the exact time-weighted annualized return of the portfolio.
    It builds an exact chronological array of cash outflows (buys) and inflows (sells/dividends),
    evaluating the terminal value of the portfolio using the latest cached market data.
    """
)
def generate_xirr_report(portfolio_id: uuid.UUID, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    portfolio = db.query(models.Portfolio).filter(models.Portfolio.id == portfolio_id, models.Portfolio.user_id == current_user.id).first()
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found or access denied.")

    try:
        engine = XIRREngine(db_session=db, portfolio_id=str(portfolio_id))
        report_data = engine.calculate_portfolio_xirr()
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="XIRR calculation failed.")

    # Map the accurate 'current_cost_basis' to your schema's total_invested_capital field
    return schemas.XIRRReportResponse(
        portfolio_id=portfolio_id,
        xirr_percentage=report_data["xirr_percentage"],
        total_invested_capital=report_data["current_cost_basis"], # Updated from "total_invested"
        current_market_value=report_data["current_value"]
    )



@router.get(
    "/{portfolio_id}/tax-report/pdf",
    summary="Download PDF Tax Report",
    description="Generates and streams a formatted PDF document containing the FIFO tax ledger."
)
def download_tax_report_pdf(
    portfolio_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # 1. Verify Portfolio Ownership
    portfolio = db.query(models.Portfolio).filter(
        models.Portfolio.id == portfolio_id,
        models.Portfolio.user_id == current_user.id
    ).first()

    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found or access denied.")

    # 2. Run the math engine to get the raw numbers
    try:
        engine = FIFOTaxEngine(db_session=db, portfolio_id=str(portfolio_id))
        report_data = engine.compute_realized_gains()
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Engine calculation failed.")

    # 3. Generate the PDF buffer
    pdf_buffer = create_tax_pdf(report_data, current_user.email)

    # 4. Stream the file directly to the client
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=FinTrace_Tax_Report_{portfolio_id}.pdf"}
    )
