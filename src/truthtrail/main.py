"""Canonical entrypoint: ``uvicorn truthtrail.main:app``."""

from truthtrail.api.app import create_app

app = create_app()
