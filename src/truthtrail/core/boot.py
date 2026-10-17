"""Construction-time settings: values ``create_app()`` needs before the app starts.

``BootSettings`` has no required fields, so building the app never fails because the
GNews key is missing. That check stays in the lifespan (strict ``Settings``), which keeps
``uvicorn main:app`` exiting with code 3 and "Application startup failed" instead of
failing during import. Error messages name the variable and the rule, never the value.

Proxy trust (D-10). ``TRUST_PROXY_HEADERS`` (default false) and ``FORWARDED_ALLOW_IPS`` are the
ONLY proxy-trust switches, because the server is ALWAYS started with ``--no-proxy-headers``.
uvicorn's own proxy handling is on by default, trusts 127.0.0.1 and ::1 and reads the same
``FORWARDED_ALLOW_IPS``; without the flag a spoofed ``X-Forwarded-For`` from a loopback peer
would replace the client address before this application sees it, whatever
``TRUST_PROXY_HEADERS`` says, and the per-IP rate limit could be bypassed. With the flag,
uvicorn ignores ``FORWARDED_ALLOW_IPS`` and only the middleware ``create_app()`` adds (the
same class uvicorn would use) acts on it.
"""

from typing import Annotated
from urllib.parse import urlsplit

from pydantic import ValidationError, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from truthtrail.core.config import ConfigurationError


def _origin_problem(origin: str) -> str | None:
    """Return the rule an origin breaks, or None when it is acceptable.

    CORSMiddleware compares exact strings, so an entry must equal what a browser sends in
    the Origin header: ``scheme://host[:port]`` with no path, query, fragment, userinfo or
    trailing slash.
    """
    if "*" in origin:
        return "wildcard origins are not allowed"
    try:
        parts = urlsplit(origin)
        parts.port  # noqa: B018 - raises ValueError for an invalid port
    except ValueError:
        return "each origin must be a valid scheme://host[:port]"
    if parts.scheme not in {"http", "https"}:
        return "each origin must use the http or https scheme"
    if not parts.hostname:
        return "each origin must include a host"
    if parts.username is not None or parts.password is not None or "@" in parts.netloc:
        return "origins must not contain credentials"
    if parts.path or parts.query or parts.fragment:
        return "origins must not have a path, query, fragment or trailing slash"
    if origin != f"{parts.scheme}://{parts.netloc}":
        return "each origin must be exactly scheme://host[:port]"
    return None


class BootSettings(BaseSettings):
    """Environment-driven values read when the app is constructed. No required fields."""

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        env_ignore_empty=True,
        hide_input_in_errors=True,
    )

    # NoDecode: a plain list[str] would demand JSON in the environment.
    cors_origins: Annotated[list[str], NoDecode] = []
    # Trust X-Forwarded-For only when true and only from the peers in forwarded_allow_ips.
    # The variable name FORWARDED_ALLOW_IPS deliberately matches the one uvicorn reads.
    trust_proxy_headers: bool = False
    forwarded_allow_ips: str = "127.0.0.1,::1"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        """Split a comma-separated string, strip each piece and drop empty ones."""
        if isinstance(value, str):
            return [piece.strip() for piece in value.split(",") if piece.strip()]
        return value

    @field_validator("cors_origins", mode="after")
    @classmethod
    def _check_origins(cls, value: list[str]) -> list[str]:
        for origin in value:
            problem = _origin_problem(origin)
            if problem is not None:
                raise ValueError(problem)  # fixed text: the offending value is never echoed
        return value


def get_boot_settings() -> BootSettings:
    """Build the boot settings (not cached, so tests that change the environment see it).

    Raises ``ConfigurationError`` naming the variable and the rule, never the value.
    """
    try:
        return BootSettings()
    except ValidationError as exc:
        error = exc.errors(include_input=False, include_url=False)[0]
        name = str(error["loc"][0]).upper() if error["loc"] else "CORS_ORIGINS"
        rule = str(error["msg"]).removeprefix("Value error, ")
        raise ConfigurationError(f"Invalid configuration ({name}: {rule})") from None
