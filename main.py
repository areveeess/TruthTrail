"""Compatibility shim for `uvicorn main:app`; remove when the dashboard phase lands."""

from truthtrail.main import app

__all__ = ["app"]
