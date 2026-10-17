"""Application settings, read lazily from the environment (or a local, git-ignored .env).

Nothing here reads the environment at import time. ``get_settings()`` builds and
caches the settings on first use and is called once from the app lifespan so a
missing or invalid configuration stops startup instead of failing a request.
"""

import re
from functools import lru_cache
from typing import Any

from limits import parse_many
from pydantic import SecretStr, ValidationError, ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigurationError(RuntimeError):
    """Raised at startup when required configuration is missing or invalid."""


# An API key travels in an HTTP header: printable ASCII only, no whitespace of any kind.
# Settings trims surrounding whitespace first (a pasted newline or space); whitespace inside
# the key and non-ASCII characters would otherwise make `requests` fail at send time with an
# error that looks like a provider outage, so they are rejected at configuration time.
_HEADER_SAFE_KEY = re.compile(r"[\x21-\x7e]+")


def is_header_safe_key(value: str) -> bool:
    """True when ``value`` can be sent verbatim as an HTTP header value."""
    return _HEADER_SAFE_KEY.fullmatch(value) is not None


class Settings(BaseSettings):
    """Environment-driven configuration. Secret values are masked in repr and errors."""

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        env_ignore_empty=True,
        hide_input_in_errors=True,
    )

    gnews_api_key: SecretStr | None = None
    demo_mode: bool = False
    bluesky_handle: str | None = None
    bluesky_app_password: SecretStr | None = None
    database_url: SecretStr | None = None
    # Per-client-IP limits, "N/minute" style. Read per request (callable limits), validated here.
    rate_limit_analyze: str = "10/minute"
    rate_limit_v1: str = "60/minute"

    @field_validator("rate_limit_analyze", "rate_limit_v1")
    @classmethod
    def _valid_rate_limit(cls, value: str, info: ValidationInfo) -> str:
        """Reject a rate limit string the limiter cannot parse; name the variable, not the value."""
        try:
            parse_many(value)
        except ValueError:
            name = (info.field_name or "rate limit").upper()
            raise ValueError(f"{name} is not a valid rate limit") from None
        return value

    @field_validator("gnews_api_key", mode="before")
    @classmethod
    def _blank_key_is_missing(cls, value: Any) -> Any:
        """Trim surrounding whitespace; treat a blank key as not configured.

        Reject the key if it is unsafe.

        A key that still cannot be an HTTP header value after trimming (whitespace inside it,
        non-ASCII characters) is rejected. The message never contains the value.
        """
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return None
            if not is_header_safe_key(value):
                raise ValueError(
                    "GNEWS_API_KEY must be printable ASCII without spaces or line breaks "
                    "inside the key"
                )
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
            f"{'.'.join(map(str, err['loc'])) or 'settings'}: {err['msg']}" for err in exc.errors()
        )
        raise ConfigurationError(
            f"Invalid configuration ({problems}). Set the variables listed in .env.example."
        ) from None
