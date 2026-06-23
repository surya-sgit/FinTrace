import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
import uuid
from datetime import date, timedelta
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from api.main import app
from api.dependencies import get_current_user
from db.session import get_db
from domain.models import User
from unittest.mock import MagicMock

test_user = User(id=uuid.uuid4(), email="test@example.com")

def override_get_current_user():
    return test_user

def override_get_db():
    mock_db = MagicMock()
    # Mocking db.query().filter().first() -> None (to trigger 404)
    mock_db.query.return_value.filter.return_value.first.return_value = None
    yield mock_db

@pytest.fixture(autouse=True)
def setup_overrides():
    original_overrides = app.dependency_overrides.copy()
    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.clear()
    app.dependency_overrides.update(original_overrides)

@pytest_asyncio.fixture
async def async_client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

@pytest.mark.asyncio
async def test_attribution_future_date_rejected(async_client):
    portfolio_id = uuid.uuid4()
    future_date = date.today() + timedelta(days=5)
    
    response = await async_client.get(f"/api/v1/analytics/{portfolio_id}/attribution?target_date={future_date.isoformat()}")
    assert response.status_code == 400
    assert "future" in response.json()["detail"].lower()

@pytest.mark.asyncio
async def test_attribution_tenant_isolation(async_client):
    # This portfolio does not exist in the test DB for the dummy user, so it should return 404
    portfolio_id = uuid.uuid4()
    today = date.today()
    
    response = await async_client.get(f"/api/v1/analytics/{portfolio_id}/attribution?target_date={today.isoformat()}")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()
