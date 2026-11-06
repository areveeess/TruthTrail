"""``DATABASE_URL`` normalisation (D-19, RESEARCH Pattern 9, F-14, pitfall 16).

One function maps every accepted spelling to SQLAlchemy's psycopg 3 dialect. ``postgres://``
(used by many hosting providers) has no SQLAlchemy dialect of that name, so the scheme is
rewritten instead of passed through. The value is a credential: errors carry fixed text only and
are raised ``from None`` (SQLAlchemy's own parse error repeats the whole string), and the
returned ``URL`` masks the password in ``str`` and ``repr``.
"""

from pydantic import SecretStr
from sqlalchemy.engine import URL, make_url

from truthtrail.core.config import ConfigurationError

DRIVER_NAME = "postgresql+psycopg"
ACCEPTED_SCHEMES = frozenset({"postgresql", "postgres", DRIVER_NAME})
SCHEME_ERROR = (
    "DATABASE_URL must use the postgresql://, postgres:// or postgresql+psycopg:// scheme"
)


def normalise_database_url(raw: str | SecretStr | URL) -> URL:
    """Return ``raw`` as a ``postgresql+psycopg`` URL or raise ``ConfigurationError``.

    The error text is fixed and never contains any part of the value.
    """
    if isinstance(raw, SecretStr):
        raw = raw.get_secret_value()
    try:
        url = raw if isinstance(raw, URL) else make_url(raw.strip())
    except Exception:  # ArgumentError, ValueError: the message would repeat the value
        raise ConfigurationError(SCHEME_ERROR) from None
    if url.drivername.lower() not in ACCEPTED_SCHEMES:
        raise ConfigurationError(SCHEME_ERROR)
    return url.set(drivername=DRIVER_NAME)


def describe_database_url(url: URL) -> str:
    """Password-masked rendering for operator diagnostics only.

    Logs and error bodies never print even this (D-18): it still shows the host and user.
    """
    return url.render_as_string(hide_password=True)
