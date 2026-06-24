from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql://postgres:postgres@localhost:5432/treasury_monitor"

    # API Keys
    fred_api_key: str = "your_fred_api_key_here"
    anthropic_api_key: str = ""

    # Basic Auth (set via Fly.io secrets)
    auth_username: str = "sentinel"
    auth_password: str = "changeme"

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Scheduler
    scheduler_enabled: bool = True
    fred_fetch_hour: int = 2
    treasury_fetch_day: int = 15
    gold_fetch_day: int = 1

    # Logging
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
