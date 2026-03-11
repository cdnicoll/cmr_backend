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
    ingest_min_word_count: int = Field(
        default=100,
        validation_alias="INGEST_MIN_WORD_COUNT",
    )
    scrape_stuck_timeout_minutes: int = Field(
        default=15,
        validation_alias="SCRAPE_STUCK_TIMEOUT_MINUTES",
    )
    ingest_stuck_timeout_minutes: int = Field(
        default=30,
        validation_alias="INGEST_STUCK_TIMEOUT_MINUTES",
    )
    neo4j_uri: str = Field(default="", validation_alias="NEO4J_URI")
    neo4j_username: str = Field(default="", validation_alias="NEO4J_USERNAME")
    neo4j_password: str = Field(default="", validation_alias="NEO4J_PASSWORD")
    neo4j_database: str = Field(default="neo4j", validation_alias="NEO4J_DATABASE")
    openai_api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")
    # Discovery defaults (per research.md and plan)
    discovery_days_back_default: int = Field(
        default=14,
        validation_alias="DISCOVERY_DAYS_BACK_DEFAULT",
    )
    discovery_batch_size: int = Field(
        default=50,
        validation_alias="DISCOVERY_BATCH_SIZE",
    )
    # First-run vs ongoing: tight limits on first discovery run per source
    discovery_initial_days_back: int = Field(
        default=1,
        validation_alias="DISCOVERY_INITIAL_DAYS_BACK",
    )
    discovery_initial_max_urls: int = Field(
        default=20,
        validation_alias="DISCOVERY_INITIAL_MAX_URLS",
    )
    discovery_initial_max_videos: int = Field(
        default=10,
        validation_alias="DISCOVERY_INITIAL_MAX_VIDEOS",
    )


@lru_cache
def load_settings() -> Settings:
    """Load and cache settings."""
    return Settings()
