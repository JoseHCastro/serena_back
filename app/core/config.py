"""
Application configuration module.

Loads and validates all environment variables using pydantic-settings,
providing type-safe, centralized access to configuration throughout the app.
"""

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from the .env file.

    Attributes:
        APP_NAME: Human-readable application name.
        APP_VERSION: Current semantic version string.
        DEBUG: Enables debug mode, verbose SQL logging, and reload.
        DATABASE_URL: Async PostgreSQL DSN (asyncpg driver, used by SQLAlchemy).
        SYNC_DATABASE_URL: Sync PostgreSQL DSN (psycopg2 driver, used by Alembic).
        SECRET_KEY: HMAC secret for JWT signing — must be at least 32 characters.
        ALGORITHM: JWT signing algorithm (default HS256).
        ACCESS_TOKEN_EXPIRE_MINUTES: Lifetime of access tokens in minutes.
        REFRESH_TOKEN_EXPIRE_DAYS: Lifetime of refresh tokens in days.
        REDIS_URL: Redis DSN used as Celery broker and result backend.
        CLOUDINARY_CLOUD_NAME: Cloudinary account cloud name.
        CLOUDINARY_API_KEY: Cloudinary API key.
        CLOUDINARY_API_SECRET: Cloudinary API secret.
        ALLOWED_ORIGINS: List of CORS-allowed frontend origins.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    # Application
    APP_NAME: str = "Serena API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str
    SYNC_DATABASE_URL: str

    # Security
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Redis / Celery
    REDIS_URL: str = "redis://redis:6379/0"

    # Cloudinary
    CLOUDINARY_CLOUD_NAME: str
    CLOUDINARY_API_KEY: str
    CLOUDINARY_API_SECRET: str

    # CORS
    ALLOWED_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    # Biometrics
    FRAME_SAMPLING_INTERVAL: float = 1.0


    @field_validator("SECRET_KEY")
    @classmethod
    def secret_key_min_length(cls, v: str) -> str:
        """Validate that SECRET_KEY is at least 32 characters long.

        Args:
            v: The raw SECRET_KEY value from the environment.

        Returns:
            The validated SECRET_KEY string.

        Raises:
            ValueError: If the key is shorter than 32 characters.
        """
        if len(v) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters long.")
        return v


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings singleton.

    Uses lru_cache to ensure the .env file is read only once per process,
    avoiding repeated I/O on every dependency call.

    Returns:
        Settings: The singleton Settings instance.
    """
    return Settings()


# Convenience module-level instance for imports across the project
settings: Settings = get_settings()
