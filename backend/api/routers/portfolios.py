# api/routers/portfolios.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from db.session import get_db
from domain import models, schemas
from api.dependencies import get_current_user

router = APIRouter()

@router.post(
    "/",
    response_model=schemas.PortfolioResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Initialize a new investment portfolio",
    description="""
    Creates a new, empty portfolio container for the authenticated user.

    This portfolio acts as the isolated environment for a specific set of transaction ledgers.
    Calculations and tax snapshots cannot cross-pollinate between distinct portfolios.
    """,
    response_description="The fully instantiated portfolio object including its UUID."
)
def create_portfolio(portfolio: schemas.PortfolioCreate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    new_portfolio = models.Portfolio(
        user_id=current_user.id,
        name=portfolio.name,
        tax_jurisdiction=portfolio.tax_jurisdiction.value
    )

    db.add(new_portfolio)
    db.commit()
    db.refresh(new_portfolio)
    return new_portfolio

@router.get(
    "/",
    response_model=List[schemas.PortfolioResponse],
    status_code=status.HTTP_200_OK,
    summary="Retrieve all portfolios",
    description="Fetches a list of all active portfolios belonging to the currently authenticated user session.",
    response_description="A list of portfolio objects."
)
def get_portfolios(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    portfolios = db.query(models.Portfolio).filter(models.Portfolio.user_id == current_user.id).all()
    return portfolios

@router.get(
    "/{portfolio_id}",
    response_model=schemas.PortfolioResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve a specific portfolio",
    description="Fetches a specific portfolio by its UUID for the currently authenticated user.",
    response_description="The requested portfolio object."
)
def get_portfolio(portfolio_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    portfolio = db.query(models.Portfolio).filter(
        models.Portfolio.id == portfolio_id,
        models.Portfolio.user_id == current_user.id
    ).first()
    
    if not portfolio:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Portfolio not found or you do not have permission to access it."
        )
        
    return portfolio
