from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql://postgres:postgres@localhost:5432/treasury_monitor"

    # API Keys
    fred_api_key: str = "your_fred_api_key_here"
    anthropic_api_key: str = ""
    # D-0069 removed the only READER of this, but the field has to stay:
    # a local .env still defines GROK_API_KEY, and Settings forbids extra
    # inputs, so deleting the field stops the app booting anywhere that
    # variable is still present. Unread, retained, and documented as such.
    grok_api_key: str = ""

    # Basic Auth (set via Fly.io secrets)
    auth_username: str = "sentinel"
    # ORDER-03 A3 / F-0009: no default. A missing AUTH_PASSWORD is a startup
    # failure, not a fallback to a credential published in a public repo.
    auth_password: str

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
  

    # Scheduler
    scheduler_enabled: bool = True
    fred_fetch_hour: int = 2
    treasury_fetch_day: int = 15
    gold_fetch_day: int = 1
    cds_fetch_hour: int = 3
    
    # Logging
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
