import os
import uuid
import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from langchain_community.utilities import SQLDatabase
from langchain_openai import ChatOpenAI
from langchain_community.agent_toolkits import create_sql_agent

from domain.models import Portfolio, TransactionLedger, MarketPrice

def get_isolated_db(user_id: uuid.UUID, db: Session) -> SQLDatabase:
    temp_engine = create_engine("sqlite:///:memory:")
    
    # Portfolios
    try:
        portfolios = db.query(Portfolio).filter(Portfolio.user_id == user_id).all()
    except Exception:
        portfolios = []
        db.rollback()
        
    if portfolios:
        df_p = pd.DataFrame([p.__dict__ for p in portfolios])
        df_p = df_p.drop(columns=['_sa_instance_state'], errors='ignore')
        df_p = df_p.astype(str)
        df_p.to_sql('portfolios', temp_engine, index=False)
    else:
        pd.DataFrame(columns=['id', 'user_id', 'name', 'tax_jurisdiction', 'created_at']).to_sql('portfolios', temp_engine, index=False)
        
    # Transactions
    try:
        portfolio_ids = [p.id for p in portfolios]
        transactions = db.query(TransactionLedger).filter(TransactionLedger.portfolio_id.in_(portfolio_ids)).all() if portfolio_ids else []
    except Exception:
        transactions = []
        db.rollback()
        
    if transactions:
        df_t = pd.DataFrame([t.__dict__ for t in transactions])
        df_t = df_t.drop(columns=['_sa_instance_state'], errors='ignore')
        df_t = df_t.astype(str)
        # Quantity and price should be numeric for SQL math
        if 'quantity' in df_t.columns:
            df_t['quantity'] = pd.to_numeric(df_t['quantity'], errors='coerce')
        if 'price_per_unit' in df_t.columns:
            df_t['price_per_unit'] = pd.to_numeric(df_t['price_per_unit'], errors='coerce')
        df_t.to_sql('transactions', temp_engine, index=False)
    else:
        pd.DataFrame(columns=['id', 'portfolio_id', 'ticker', 'transaction_type', 'quantity', 'price_per_unit']).to_sql('transactions', temp_engine, index=False)
        
    # Market Prices
    try:
        prices = db.query(MarketPrice).all()
    except Exception:
        prices = []
        db.rollback()
        
    if prices:
        df_m = pd.DataFrame([p.__dict__ for p in prices])
        df_m = df_m.drop(columns=['_sa_instance_state'], errors='ignore')
        df_m = df_m.astype(str)
        if 'current_price' in df_m.columns:
            df_m['current_price'] = pd.to_numeric(df_m['current_price'], errors='coerce')
        df_m.to_sql('market_prices', temp_engine, index=False)
    else:
        pd.DataFrame(columns=['ticker', 'current_price', 'last_updated', 'data_source']).to_sql('market_prices', temp_engine, index=False)
        
    return SQLDatabase(temp_engine)

class CopilotEngine:
    def __init__(self, db_session: Session, user_id: uuid.UUID):
        self.db_session = db_session
        self.user_id = user_id
        
    def chat(self, query: str) -> str:
        isolated_db = get_isolated_db(self.user_id, self.db_session)
        llm = ChatOpenAI(temperature=0, model="gpt-4o-mini", api_key=os.getenv("OPENAI_API_KEY", "dummy"))
        
        system_prompt = """You are a quantitative financial assistant for the FinTrace application.
You must return precise, mathematically sound answers based on the user's portfolio and transaction data.
You must explicitly refuse to answer any queries that are not related to finance, portfolios, or the provided database schema.
If the user asks something out of domain, reply with "I can only answer financial and portfolio-related queries."
"""
        
        agent_executor = create_sql_agent(
            llm=llm,
            db=isolated_db,
            agent_type="openai-tools",
            verbose=False,
            prefix=system_prompt
        )
        
        try:
            response = agent_executor.invoke({"input": query})
            return response.get("output", "I could not process your request.")
        except Exception as e:
            return f"An error occurred while processing your request: {str(e)}"
