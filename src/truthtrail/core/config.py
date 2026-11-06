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


def configuration_error(exc: ValidationError) -> ConfigurationError:
    """Build ``ConfigurationError("Invalid configuration (NAME: rule)")`` from the first error.

    The variable is the field name in upper case. A model-level rule has no field location and
    carries its own ``NAME: rule`` text. Input values are never included (callers raise the
    result ``from None`` so the original error, which may hold the value, is not chained).
    """
    error = exc.errors(include_input=False, include_url=False, include_context=False)[0]
    rule = str(error["msg"]).removeprefix("Value error, ")
    if error["loc"]:
        rule = f"{str(error['loc'][0]).upper()}: {rule}"
    return ConfigurationError(f"Invalid configuration ({rule})")


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


# Sent inside the collector's User-Agent header (D-07): printable ASCII including the space,
# no CR, LF or other control characters, so header injection is impossible.
_HEADER_SAFE_TEXT = re.compile(r"[\x20-\x7e]{1,200}")


class DatabaseSettings(BaseSettings):
    """What every database entrypoint needs (D-27): only ``DATABASE_URL``, required.

    The collector, enrich, purge, migrate and erase commands build on this class, so none of
    them depends on the API's ``Settings`` (which still requires the news key).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        env_ignore_empty=True,
        hide_input_in_errors=True,
    )

    database_url: SecretStr


class IngestSettings(DatabaseSettings):
    """Collector and erase entrypoints: the database plus the pseudonym key (D-17, D-07).

    The API process never builds this class, so it never holds ``PSEUDONYM_SECRET``. The key's
    length and encoding are validated by the pseudonymiser, not here.
    """

    pseudonym_secret: SecretStr
    collector_contact: str | None = None

    @field_validator("collector_contact", mode="before")
    @classmethod
    def _header_safe_contact(cls, value: Any) -> Any:
        """Strip; blank means None; otherwise at most 200 printable ASCII characters."""
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return None
            if not _HEADER_SAFE_TEXT.fullmatch(value):
                raise ValueError(
                    "must be at most 200 printable ASCII characters without line breaks or "
                    "control characters"
                )
        return value


def get_database_settings() -> DatabaseSettings:
    """Build the database settings (not cached) or raise ``ConfigurationError`` naming the
    variable, never the value."""
    try:
        return DatabaseSettings()
    except ValidationError as exc:
        raise configuration_error(exc) from None


def get_ingest_settings() -> IngestSettings:
    """Build the ingest settings (not cached) or raise ``ConfigurationError`` naming the
    variable, never the value."""
    try:
        return IngestSettings()
    except ValidationError as exc:
        raise configuration_error(exc) from None
