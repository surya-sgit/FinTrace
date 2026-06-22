import asyncio
import sys
import os

# Ensure backend path is in sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from api.main import app, lifespan

async def test_startup():
    try:
        async with lifespan(app):
            print("Lifespan started successfully with APScheduler initialized!")
    except Exception as e:
        print(f"Error during startup: {e}")

if __name__ == "__main__":
    asyncio.run(test_startup())
