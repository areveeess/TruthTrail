"""Application settings, read lazily from the environment (or a local, git-ignored .env).

Nothing here reads the environment at import time. ``get_settings()`` builds and
caches the settings on first use and is called once from the app lifespan so a
missing or invalid configuration stops startup instead of failing a request.
"""

from functools import lru_cache
from typing import Any, Optional

from pydantic import SecretStr, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigurationError(RuntimeError):
    """Raised at startup when required configuration is missing or invalid."""


class Settings(BaseSettings):
    """Environment-driven configuration. Secret values are masked in repr and errors."""

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        env_ignore_empty=True,
        hide_input_in_errors=True,
    )

    gnews_api_key: Optional[SecretStr] = None
    demo_mode: bool = False
    bluesky_handle: Optional[str] = None
    bluesky_app_password: Optional[SecretStr] = None
    database_url: Optional[SecretStr] = None

    @field_validator("gnews_api_key", mode="before")
    @classmethod
    def _blank_key_is_missing(cls, value: Any) -> Any:
        """Treat an empty or whitespace-only key as not configured."""
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @model_validator(mode="after")
    def _key_required_unless_demo(self) -> "Settings":
        """Require the news key unless the service runs in demo mode."""
        if not self.demo_mode and self.gnews_api_key is None:
            raise ValueError("GNEWS_API_KEY is required unless DEMO_MODE=true")
        return self


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings or raise ConfigurationError without echoing any value."""
    try:
        return Settings()
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(map(str, err['loc'])) or 'settings'}: {err['msg']}"
            for err in exc.errors()
        )
        raise ConfigurationError(
            f"Invalid configuration ({problems}). "
            "Set the variables listed in .env.example."
        ) from None
