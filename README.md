# FinTrace

FinTrace is a quantitative analytics application for retail investors. It allows users to track their portfolios, analyze historical performance, compute complex tax liabilities (FIFO, STCG, LTCG), and interact with a quantitative AI Copilot to query their data.

## Features
- **Portfolio Management**: Create and track multiple portfolios.
- **Transaction Ledger**: Upload transactions, track buys/sells across assets.
- **Quantitative Engine**: Calculate metrics like XIRR, Sharpe Ratio, and Maximum Drawdown.
- **Automated Live Pricing**: 2-tier waterfall fallback using Alpha Vantage and Yahoo Finance to fetch EOD closing prices.
- **Agentic Text-to-SQL Copilot**: RAG-powered Copilot that converts natural language into isolated SQL queries, ensuring zero cross-tenant data leakage.

## Tech Stack
- **Frontend**: Next.js 14 App Router, React, Tailwind CSS, Recharts
- **Backend**: FastAPI, PostgreSQL, SQLAlchemy, APScheduler
- **AI/LLM**: LangChain, OpenAI (GPT-4o-mini)
- **Data Engineering**: Pandas, yfinance

## Getting Started

1. Clone the repository.
2. Navigate to `backend/` and copy `.env.example` to `.env`. Update variables.
3. Start the backend: `uv run uvicorn api.main:app --reload`
4. Start the frontend: `npm install` and `npm run dev` in the `frontend/` directory.
