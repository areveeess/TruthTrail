"""Installed-package smoke test: the local stand-in for the container image (D-01, D-22, ENG-05).

No Docker daemon exists in the dev container, so this script exercises what the image will run:
a NON-EDITABLE, --no-dev install of the application, started with the image's command (including
``--no-proxy-headers``, D-10) from a throwaway directory that is not the repository root, with a
scrubbed environment and DEMO_MODE=true. It proves:

* ``GET /health`` returns ``{"status": "ok"}`` and ``GET /ready`` is ready;
* ``GET /analyze?query=smoke`` returns synthetic fixture data, ``X-Cache: miss`` and then ``hit``;
* the legacy modules, pytest, ruff and scikit-learn are not importable, the package lives in
  ``site-packages`` (not editable) and ships ``data/demo_analyze.json``.

Build the environment, then run the script:

    UV_PROJECT_ENVIRONMENT=DIR uv sync --locked --no-dev --no-editable
    python scripts/smoke_app.py --python DIR/bin/python [--timeout SECONDS]

Exit codes: 0 every check passed, 1 a check failed. Standard library only. Failures print the
check name and a short message, never a response body.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

HOST = "127.0.0.1"
FORBIDDEN_MODULES = ("spread_simulator", "users", "risk_analyzer", "pytest", "ruff", "sklearn")

# Runs under ``python -I`` inside the installed environment.
IMPORT_CHECK = """
import importlib.resources
import importlib.util
import sys

modules = {modules!r}
present = [name for name in modules if importlib.util.find_spec(name) is not None]
if present:
    sys.exit("importable but must not be: " + ", ".join(present))
import truthtrail

if "site-packages" not in truthtrail.__file__.replace("\\\\", "/").split("/"):
    sys.exit("truthtrail is not installed under site-packages (editable install?)")
fixture = importlib.resources.files("truthtrail").joinpath("data", "demo_analyze.json")
if not fixture.is_file():
    sys.exit("package data data/demo_analyze.json is missing")
"""

# One opener without proxy handlers: ambient proxy variables must never intercept loopback.
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class SmokeError(Exception):
    """A check failed; the message is short and never carries a response body."""


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((HOST, 0))
        port: int = sock.getsockname()[1]
        return port


def _get(port: int, path: str) -> tuple[int, dict[str, str], Any]:
    """GET ``path`` on the local server; return (status, lower-cased headers, parsed JSON)."""
    url = f"http://{HOST}:{port}{path}"
    request = urllib.request.Request(url, method="GET")
    try:
        with _OPENER.open(request, timeout=5) as response:
            raw = response.read()
            status = response.status
            headers = {k.lower(): v for k, v in response.headers.items()}
    except urllib.error.HTTPError as exc:
        raise SmokeError(f"GET {path} returned HTTP {exc.code}") from None
    except (urllib.error.URLError, OSError) as exc:
        raise SmokeError(f"GET {path} failed: {type(exc).__name__}") from None
    try:
        body = json.loads(raw)
    except ValueError:
        raise SmokeError(f"GET {path} did not return JSON") from None
    return status, headers, body


def _wait_for_health(port: int, server: subprocess.Popen[bytes], timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if server.poll() is not None:
            raise SmokeError(f"server exited early with code {server.returncode}")
        try:
            status, _, _ = _get(port, "/health")
        except SmokeError:
            time.sleep(0.2)
            continue
        if status == 200:
            return
        time.sleep(0.2)
    raise SmokeError(f"/health did not answer 200 within {timeout:g}s")


def check_health(port: int) -> None:
    status, _, body = _get(port, "/health")
    if status != 200 or body != {"status": "ok"}:
        raise SmokeError("/health is not 200 with status ok")


def check_ready(port: int) -> None:
    status, _, body = _get(port, "/ready")
    if status != 200 or not isinstance(body, dict) or body.get("status") != "ready":
        raise SmokeError("/ready is not 200 with status ready")


def check_analyze(port: int) -> None:
    status, headers, body = _get(port, "/analyze?query=smoke")
    if status != 200:
        raise SmokeError(f"/analyze returned {status}")
    meta = body.get("meta") if isinstance(body, dict) else None
    if not isinstance(meta, dict) or meta.get("synthetic") is not True:
        raise SmokeError("/analyze meta.synthetic is not true")
    if meta.get("source_status") != "fixture":
        raise SmokeError("/analyze meta.source_status is not 'fixture'")
    if headers.get("x-cache") != "miss":
        raise SmokeError("first /analyze did not report X-Cache: miss")
    _, again, _ = _get(port, "/analyze?query=smoke")
    if again.get("x-cache") != "hit":
        raise SmokeError("second /analyze did not report X-Cache: hit")


def check_imports(python: str, workdir: str, env: dict[str, str]) -> None:
    code = IMPORT_CHECK.format(modules=FORBIDDEN_MODULES)
    result = subprocess.run(  # noqa: S603 - fixed argument vector, operator-supplied interpreter
        [python, "-I", "-c", code],
        cwd=workdir,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if result.returncode != 0:
        # The check script exits with a short, fixed message; show only its last line.
        lines = result.stderr.strip().splitlines()
        reason = lines[-1][:200] if lines else f"exit code {result.returncode}"
        raise SmokeError(reason)


def _stop(server: subprocess.Popen[bytes]) -> None:
    if server.poll() is not None:
        return
    server.terminate()
    try:
        server.wait(timeout=10)
    except subprocess.TimeoutExpired:
        server.kill()
        server.wait(timeout=10)


def _child_env() -> dict[str, str]:
    env = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONDONTWRITEBYTECODE": "1",
        "DEMO_MODE": "true",
    }
    if "SYSTEMROOT" in os.environ:
        env["SYSTEMROOT"] = os.environ["SYSTEMROOT"]
    return env


def main(argv: list[str] | None = None) -> int:
    """Run every check; return 0 when all pass and 1 on the first failure."""
    parser = argparse.ArgumentParser(description="Smoke-test an installed TruthTrail package.")
    parser.add_argument("--python", required=True, help="interpreter of the installed environment")
    parser.add_argument("--timeout", type=float, default=30.0, help="seconds to wait for /health")
    args = parser.parse_args(argv)

    env = _child_env()
    # Absolute but NOT symlink-resolved: a venv interpreter finds its site-packages through its
    # own path, and the children run from a different working directory.
    python = os.path.abspath(args.python)
    if not os.path.isfile(python):
        sys.stdout.write("FAIL: startup: --python does not name a file\n")
        return 1
    with tempfile.TemporaryDirectory(prefix="truthtrail-smoke-") as workdir:
        port = _free_port()
        command = [
            python,
            "-m",
            "uvicorn",
            "truthtrail.main:app",
            "--host",
            HOST,
            "--port",
            str(port),
            "--no-proxy-headers",
        ]
        server = subprocess.Popen(  # noqa: S603 - fixed argument vector, operator-supplied interpreter
            command,
            cwd=workdir,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        checks: list[tuple[str, Callable[[], None]]] = [
            ("health", lambda: check_health(port)),
            ("ready", lambda: check_ready(port)),
            ("analyze demo (X-Cache miss then hit)", lambda: check_analyze(port)),
            (
                "installed non-editable, package data present, legacy/dev/train not importable",
                lambda: check_imports(python, workdir, env),
            ),
        ]
        try:
            _wait_for_health(port, server, args.timeout)
            for name, run in checks:
                try:
                    run()
                except SmokeError as exc:
                    sys.stdout.write(f"FAIL: {name}: {exc}\n")
                    return 1
                sys.stdout.write(f"ok: {name}\n")
        except SmokeError as exc:
            sys.stdout.write(f"FAIL: startup: {exc}\n")
            return 1
        finally:
            _stop(server)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
