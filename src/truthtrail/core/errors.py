"""RFC 9457 problem+json rendering for every error the API can return.

All errors share one shape: ``type`` (``about:blank``), ``title`` (the HTTP status
phrase), integer ``status``, human ``detail`` and a stable machine-readable
``code``, plus the provenance members ``synthetic`` (false), ``source_status`` and
``data_as_of`` (null) so an error can never be mistaken for data.

Nothing here puts a credential, a provider URL, a query string or an exception
message into a body or a log line.
"""

from http import HTTPStatus
from typing import Any, Optional

from fastapi.responses import JSONResponse

PROBLEM_MEDIA_TYPE = "application/problem+json"


class UpstreamError(Exception):
    """The news provider failed or answered badly.

    ``status`` is the HTTP status this API answers with (502 for a bad answer, 503
    for unreachable or throttling). ``str(exc)`` is only ``"<upstream> <code>"`` so
    it can never hold a URL or a key.
    """

    def __init__(
        self,
        status: int,
        code: str,
        detail: str,
        retry_after: Optional[int] = None,
        upstream: str = "gnews",
    ) -> None:
        super().__init__(f"{upstream} {code}")
        self.status = status
        self.code = code
        self.detail = detail
        self.retry_after = retry_after
        self.upstream = upstream


def problem_body(
    status: int, detail: str, code: str, *, source_status: str, **extensions: Any
) -> dict:
    """Build an RFC 9457 body with the provenance members always present."""
    return {
        "type": "about:blank",
        "title": HTTPStatus(status).phrase,
        "status": status,
        "detail": detail,
        "code": code,
        **extensions,
        "synthetic": False,
        "source_status": source_status,
        "data_as_of": None,
    }


def problem_response(
    status: int, body: dict, headers: Optional[dict] = None
) -> JSONResponse:
    """Render a problem body with the problem+json media type."""
    return JSONResponse(
        body, status_code=status, media_type=PROBLEM_MEDIA_TYPE, headers=headers
    )
