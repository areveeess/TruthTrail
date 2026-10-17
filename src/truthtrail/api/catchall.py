"""Pure-ASGI catch-all that renders unhandled errors as problem+json inside CORS.

A handler registered for ``Exception`` renders in Starlette's outermost
ServerErrorMiddleware, outside every user middleware, so its 500 would carry no CORS
headers and a browser frontend could not read it. This middleware sits just inside
``CORSMiddleware`` instead. Only the exception class name is logged; no exception text
ever reaches a body or a log line.
"""

import logging

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from truthtrail.core.errors import problem_body, problem_response

logger = logging.getLogger(__name__)


class CatchAllMiddleware:
    """Turn any unhandled exception into the generic 500 problem body."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = False

        async def send_wrapper(message: Message) -> None:
            nonlocal started
            started = started or message["type"] == "http.response.start"
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as exc:
            logger.error("unexpected error: %s", type(exc).__name__)
            if started:
                raise
            body = problem_body(500, "Unexpected error.", "internal_error", source_status="error")
            await problem_response(500, body)(scope, receive, send)
