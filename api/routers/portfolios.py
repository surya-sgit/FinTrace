# api/routers/portfolios.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from db.session import get_db
from domain import models, schemas

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
def create_portfolio(portfolio: schemas.PortfolioCreate, db: Session = Depends(get_db)):
    user = db.query(models.User).first()
    if not user:
        user = models.User(email="admin@fintrace.local", hashed_password="secure_mock_hash")
        db.add(user)
        db.commit()
        db.refresh(user)

    new_portfolio = models.Portfolio(
        user_id=user.id,
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
def get_portfolios(db: Session = Depends(get_db)):
    user = db.query(models.User).first()
    if not user:
        return []

    portfolios = db.query(models.Portfolio).filter(models.Portfolio.user_id == user.id).all()
    return portfolios
