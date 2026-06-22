import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# Initialize environment variables from a local .env file if it exists
load_dotenv()

# Default to a local SQLite database for local development.
# In production, set DATABASE_URL=postgresql://user:password@localhost:5432/fintrace
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./fintrace_local.db")

# SQLite requires specific connection arguments to function safely with FastAPI's async routing
if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        connect_args={"check_same_thread": False}
    )
else:
    # Production PostgreSQL engine configuration
    engine = create_engine(SQLALCHEMY_DATABASE_URL)

# Configure the session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    """
    Generator function to provide an isolated database session for each HTTP request.
    Ensures the connection is safely closed after the request lifecycle completes,
    preventing memory leaks and connection pool exhaustion.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
