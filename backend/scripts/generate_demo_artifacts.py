import os
import sys
import uuid
import json
import logging
from datetime import date
from decimal import Decimal
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Ensure backend root is in sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from domain.models import Base, User, Portfolio, TransactionLedger
from engine.math_core.tax_engine import FIFOTaxEngine
from engine.documents.pdf_generator import create_tax_csv

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    # 1. Setup in-memory DB
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()

    try:
        # 2. Create User and Portfolio
        user = User(email="demo@fintrace.example", hashed_password="hashed")
        db.add(user)
        db.commit()

        portfolio = Portfolio(user_id=user.id, name="Demo Showcase Portfolio", tax_jurisdiction="IN")
        db.add(portfolio)
        db.commit()

        logger.info(f"Created demo portfolio with ID: {portfolio.id}")

        # 3. Seed realistic transactions
        transactions = [
            TransactionLedger(portfolio_id=portfolio.id, ticker="TCS.NS", transaction_type="BUY", quantity=100, price_per_unit=3000, execution_date=date(2023, 1, 15), settlement_date=date(2023, 1, 16), sequence_number=1, checksum="1"),
            TransactionLedger(portfolio_id=portfolio.id, ticker="TCS.NS", transaction_type="BUY", quantity=50, price_per_unit=3200, execution_date=date(2023, 5, 20), settlement_date=date(2023, 5, 21), sequence_number=2, checksum="2"),
            TransactionLedger(portfolio_id=portfolio.id, ticker="TCS.NS", transaction_type="SELL", quantity=120, price_per_unit=3500, execution_date=date(2024, 2, 10), settlement_date=date(2024, 2, 11), sequence_number=3, checksum="3"),
            
            TransactionLedger(portfolio_id=portfolio.id, ticker="RELIANCE.NS", transaction_type="BUY", quantity=200, price_per_unit=2500, execution_date=date(2022, 11, 5), settlement_date=date(2022, 11, 6), sequence_number=4, checksum="4"),
            TransactionLedger(portfolio_id=portfolio.id, ticker="RELIANCE.NS", transaction_type="SELL", quantity=50, price_per_unit=2800, execution_date=date(2023, 2, 15), settlement_date=date(2023, 2, 16), sequence_number=5, checksum="5"),
        ]
        db.bulk_save_objects(transactions)
        db.commit()

        # 4. Run Tax Engine
        tax_engine = FIFOTaxEngine(db_session=db, portfolio_id=portfolio.id)
        report_data = tax_engine.compute_tax_report()
        
        # Ensure 'demo' dir exists at project root
        demo_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'demo'))
        os.makedirs(demo_dir, exist_ok=True)

        # 5. Generate JSON 
        def default_serializer(obj):
            if isinstance(obj, Decimal): return float(obj)
            if isinstance(obj, date): return obj.isoformat()
            if isinstance(obj, uuid.UUID): return str(obj)
            raise TypeError(f"Type {type(obj)} not serializable")
            
        json_path = os.path.join(demo_dir, 'sample_tax_report.json')
        with open(json_path, 'w') as f:
            json.dump(report_data, f, indent=4, default=default_serializer)
        logger.info(f"Saved JSON report to {json_path}")

        # 6. Generate CSV
        csv_buffer = create_tax_csv(report_data)
        csv_path = os.path.join(demo_dir, 'tax_working_paper.csv')
        with open(csv_path, 'wb') as f:
            f.write(csv_buffer.getvalue())
        logger.info(f"Saved CSV report to {csv_path}")

    finally:
        db.close()

if __name__ == "__main__":
    main()
