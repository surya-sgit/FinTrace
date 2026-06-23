from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # API Keys
    ALPHA_VANTAGE_API_KEY: str = "demo"
    OPENAI_API_KEY: str = ""

    # Database
    DATABASE_URL: str = "sqlite:///./fintrace.db"

    # JWT Authentication
    SECRET_KEY: str = "supersecretkey_please_change"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
