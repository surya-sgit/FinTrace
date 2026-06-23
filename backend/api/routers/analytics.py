import uuid
import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from api.dependencies import get_current_user
from db.session import get_db
from domain import models, schemas
from engine.analytics.attribution import PerformanceAttributionEngine

router = APIRouter()

@router.get(
    "/{portfolio_id}/attribution",
    response_model=schemas.PerformanceAttributionResponse,
    summary="Generate Performance Attribution Analysis",
    description="Calculates a highly robust, deterministic performance attribution matrix to identify primary portfolio drags."
)
def get_portfolio_attribution(
    portfolio_id: uuid.UUID,
    target_date: datetime.date,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # 1. Temporal Guardrail
    if target_date > datetime.date.today():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Target date cannot be in the future."
        )

    # 2. Strict Tenant Isolation
    portfolio = db.query(models.Portfolio).filter(
        models.Portfolio.id == portfolio_id,
        models.Portfolio.user_id == current_user.id
    ).first()
    
    if not portfolio:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Portfolio not found or access denied."
        )

    # 3. Engine Execution & Fault Translation
    try:
        engine = PerformanceAttributionEngine(db_session=db, portfolio_id=str(portfolio_id))
        result = engine.identify_top_drags(target_date=target_date)
        return schemas.PerformanceAttributionResponse(**result)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e)
        )

from engine.analytics.long_term_attribution import LongTermAttributionEngine
from engine.analytics.risk_metrics import RiskMetricsEngine
from starlette.concurrency import run_in_threadpool
from typing import Optional

@router.get(
    "/{portfolio_id}/long-term-attribution",
    response_model=schemas.LongTermAttributionResponse,
    summary="Generate Long-Term Value Investing Analytics",
    description="Calculates Multi-Period Organic Variation, Brinson-Fachler Decomposition, and MWR."
)
async def get_long_term_attribution(
    portfolio_id: uuid.UUID,
    start_date: Optional[datetime.date] = None,
    end_date: Optional[datetime.date] = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    portfolio = db.query(models.Portfolio).filter(
        models.Portfolio.id == portfolio_id,
        models.Portfolio.user_id == current_user.id
    ).first()

    if not portfolio:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Portfolio not found or access denied."
        )

    try:
        engine = LongTermAttributionEngine(db_session=db, portfolio_id=str(portfolio_id))
        result = await run_in_threadpool(
            engine.execute_full_long_term_analysis,
            start_date=start_date,
            end_date=end_date
        )
        return schemas.LongTermAttributionResponse(**result)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e)
        )


@router.get(
    "/{portfolio_id}/risk-metrics",
    response_model=schemas.RiskMetricsResponse,
    summary="Portfolio Risk Metrics",
    description="Computes Alpha/Beta vs NIFTY 50, Max Drawdown, Sharpe, Sortino, and Holding Period analysis."
)
async def get_risk_metrics(
    portfolio_id: uuid.UUID,
    start_date: Optional[datetime.date] = None,
    end_date: Optional[datetime.date] = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    portfolio = db.query(models.Portfolio).filter(
        models.Portfolio.id == portfolio_id,
        models.Portfolio.user_id == current_user.id
    ).first()

    if not portfolio:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Portfolio not found or access denied."
        )

    try:
        engine = RiskMetricsEngine(db_session=db, portfolio_id=str(portfolio_id))
        result = await run_in_threadpool(
            engine.compute,
            start_date=start_date,
            end_date=end_date
        )
        return schemas.RiskMetricsResponse(**result)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Risk metrics computation failed: {str(e)}"
        )
