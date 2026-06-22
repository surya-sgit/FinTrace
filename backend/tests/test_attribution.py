import pytest
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.analytics.attribution import PerformanceAttributionEngine
from domain.models import TransactionLedger

def test_attribution_engine_success():
    # 1. Setup Mock Data
    db_mock = MagicMock()
    
    target_date = date(2024, 1, 15)
    yesterday = target_date - timedelta(days=1)
    
    # Transactions
    tx1 = TransactionLedger(
        ticker="AAPL",
        transaction_type="BUY",
        quantity=Decimal("10.0"),
        price_per_unit=Decimal("150.0"),
        execution_date=date(2024, 1, 1) # Legacy
    )
    tx2 = TransactionLedger(
        ticker="AAPL",
        transaction_type="SELL",
        quantity=Decimal("2.0"),
        price_per_unit=Decimal("160.0"),
        execution_date=date(2024, 1, 10) # Legacy
    )
    tx3 = TransactionLedger(
        ticker="TSLA",
        transaction_type="BUY",
        quantity=Decimal("5.0"),
        price_per_unit=Decimal("200.0"),
        execution_date=target_date # Intraday
    )
    tx4 = TransactionLedger(
        ticker="AAPL",
        transaction_type="DIVIDEND",
        quantity=Decimal("8.0"), # Remaining legacy AAPL shares
        price_per_unit=Decimal("1.5"), # $1.5 dividend per share
        execution_date=target_date # Intraday
    )
    
    # Mocking db.query().filter().order_by().all()
    query_mock = MagicMock()
    filter_mock = MagicMock()
    order_mock = MagicMock()
    
    db_mock.query.return_value = query_mock
    query_mock.filter.return_value = filter_mock
    filter_mock.order_by.return_value = order_mock
    order_mock.all.return_value = [tx1, tx2, tx3, tx4]
    
    # Initialize Engine and override market service
    engine = PerformanceAttributionEngine(db_session=db_mock, portfolio_id="mock_portfolio")
    engine.market_service = MagicMock()
    
    def mock_get_price(ticker, dt):
        prices = {
            "AAPL": {
                yesterday: Decimal("165.0"),
                target_date: Decimal("160.0") # Price dropped, likely ex-dividend
            },
            "TSLA": {
                yesterday: Decimal("190.0"),
                target_date: Decimal("210.0") # Intraday gain
            }
        }
        return prices[ticker][dt]
        
    engine.market_service.get_price.side_effect = mock_get_price
    
    # 2. Execute
    result = engine.identify_top_drags(target_date)
    
    # 3. Assertions
    assert result["analysis_date"] == target_date.isoformat()
    
    # AAPL legacy shares = 10 - 2 = 8
    # AAPL legacy drift = 8 * (160 - 165) = -40.0
    # AAPL corporate shield = 8 * 1.5 = 12.0
    # AAPL intraday = 0
    # AAPL net = -40 + 12 = -28.0
    
    # TSLA legacy shares = 0
    # TSLA legacy drift = 0
    # TSLA corporate shield = 0
    # TSLA intraday buy = 5 * (210 - 200) = 50.0
    # TSLA net = 50.0
    
    # Sorted order (worst first): AAPL (-28.0), TSLA (50.0)
    matrix = result["full_contribution_matrix"]
    assert len(matrix) == 2
    assert matrix[0]["ticker"] == "AAPL"
    assert matrix[0]["net_contribution"] == -28.0
    assert matrix[0]["corporate_shield"] == 12.0
    assert matrix[0]["legacy_drift"] == -40.0
    
    assert matrix[1]["ticker"] == "TSLA"
    assert matrix[1]["net_contribution"] == 50.0
    assert matrix[1]["intraday_impact"] == 50.0
    
    assert result["primary_drag_ticker"] == "AAPL"
    assert result["absolute_impact"] == 28.0

def test_attribution_engine_ledger_corruption():
    db_mock = MagicMock()
    target_date = date(2024, 1, 15)
    
    tx1 = TransactionLedger(
        ticker="AAPL",
        transaction_type="SELL",
        quantity=Decimal("10.0"),
        price_per_unit=Decimal("150.0"),
        execution_date=date(2024, 1, 1)
    )
    db_mock.query().filter().order_by().all.return_value = [tx1]
    
    engine = PerformanceAttributionEngine(db_session=db_mock, portfolio_id="mock")
    
    with pytest.raises(ValueError, match="ledger corruption"):
        engine.identify_top_drags(target_date)
