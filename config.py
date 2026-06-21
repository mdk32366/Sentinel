from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql://postgres:postgres@localhost:5432/treasury_monitor"
    
    # API
    fred_api_key: str = "your_fred_api_key_here"  # Get free at https://fred.stlouisfed.org/docs/api/
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    
    # Scheduler
    scheduler_enabled: bool = True
    fred_fetch_hour: int = 2  # Run FRED fetch at 2 AM
    treasury_fetch_day: int = 15  # Run Treasury fetch on 15th of month
    gold_fetch_day: int = 1  # Run gold fetch on 1st of month
    
    # Logging
    log_level: str = "INFO"
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
