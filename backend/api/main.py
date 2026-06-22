# api/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

from api.routers import portfolios, transactions, reports, auth, copilot
from engine.live_pricing import scheduled_market_data_update

# Define categorical metadata for the Swagger UI
tags_metadata = [
    {
        "name": "Authentication",
        "description": "Identity verification and JWT generation.",
    },
    {
        "name": "Portfolios",
        "description": "Operations to manage investment containers. A portfolio is required before you can ingest any transaction ledgers.",
    },
    {
        "name": "Transactions",
        "description": "Append-only ledger operations. Ingest and track chronological asset execution records.",
    },
    {
        "name": "System",
        "description": "Core infrastructure and health diagnostics.",
    },
    {
        "name": "Reports",
        "description": "Generate detailed financial reports and analytics.",
    }
]

@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        scheduled_market_data_update,
        trigger=CronTrigger(day_of_week='mon-fri', hour=15, minute=45, timezone=pytz.timezone('Asia/Kolkata')),
        id='market_data_job',
        replace_existing=True
    )
    scheduler.start()
    yield
    scheduler.shutdown()

app = FastAPI(
    title="FinTrace Quantitative Engine",
    description="""
    **FinTrace** is a deterministic financial calculation engine.

    It accepts transaction ledgers, computes risk-adjusted performance metrics (XIRR, Sharpe),
    and handles complex FIFO capital gains tracking for regulatory tax reporting.
    """,
    version="1.0.0",
    openapi_tags=tags_metadata,
    contact={
        "name": "FinTrace Engineering",
        "email": "engineering@fintrace.dev",
    },
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://192.168.1.3:3000"], # Permit the Next.js frontend
    allow_credentials=True,
    allow_methods=["*"], # Permit all HTTP methods (GET, POST, etc.)
    allow_headers=["*"], # Permit all headers (including Authorization)
)

app.include_router(
    auth.router,
    prefix="/api/v1/auth",
    tags=["Authentication"]
)

app.include_router(
    portfolios.router,
    prefix="/api/v1/portfolios",
    tags=["Portfolios"]
)

app.include_router(
    transactions.router,
    prefix="/api/v1/portfolios",
    tags=["Transactions"]
)

app.include_router(
    reports.router,
    prefix="/api/v1/portfolios",
    tags=["Reports"]
)

app.include_router(
    copilot.router,
    prefix="/api/v1/copilot",
    tags=["Copilot"]
)

@app.get("/health", tags=["System"], summary="Verify API Gateway health")
def health_check():
    return {
        "status": "healthy",
        "service": "FinTrace API Gateway",
        "version": "1.0.0"
    }
