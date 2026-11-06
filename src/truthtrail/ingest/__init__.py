"""Bluesky Jetstream ingest layer: dialect, keyed pseudonymiser, normaliser, selection, sources.

Kept import-light on purpose: the spike scripts import ``truthtrail.ingest.selection`` under
``uv run --no-project`` (only the standard library and websockets available), so this package
module imports nothing. The API process never imports this package (D-31).
"""
