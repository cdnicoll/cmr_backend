"""Application configuration."""
from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings from environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Literal["develop", "production"] = Field(
        default="develop",
        validation_alias="ENVIRONMENT",
    )
    supabase_url: str = Field(..., validation_alias="SUPABASE_URL")
    supabase_publishable_key: str = Field(..., validation_alias="SUPABASE_PUBLISHABLE_KEY")
    supabase_secret_key: str = Field(..., validation_alias="SUPABASE_SECRET_KEY")
    transaction_pooler_url: str = Field(..., validation_alias="TRANSACTION_POOLER_URL")
    job_stuck_timeout_minutes: int = Field(
        default=15,
        validation_alias="JOB_STUCK_TIMEOUT_MINUTES",
    )
    modal_app_name: str = Field(default="API-develop", validation_alias="MODAL_APP_NAME")
    modal_project: str | None = Field(default=None, validation_alias="MODAL_PROJECT")  # e.g. cody-99083
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    scrape_min_word_count: int = Field(
        default=50,
        validation_alias="SCRAPE_MIN_WORD_COUNT",
    )
    scraping_proxy_url: str | None = Field(
        default=None,
        validation_alias="SCRAPING_PROXY_URL",
    )
    openrouter_api_key: str = Field(..., validation_alias="OPENROUTER_API_KEY")
    model_insight_extraction: str = Field(
        default="x-ai/grok-4-fast",
        validation_alias="MODEL_INSIGHT_EXTRACTION",
    )
    insight_min_word_count: int = Field(
        default=100,
        validation_alias="INSIGHT_MIN_WORD_COUNT",
    )
    insight_stuck_timeout_minutes: int = Field(
        default=30,
        validation_alias="INSIGHT_STUCK_TIMEOUT_MINUTES",
    )


@lru_cache
def load_settings() -> Settings:
    """Load and cache settings."""
    return Settings()
