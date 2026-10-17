"""The root ``main.py`` shim keeps ``uvicorn main:app`` working (D-05)."""

import main
import truthtrail.main


def test_shim_reexports_the_package_app() -> None:
    assert main.app is truthtrail.main.app
    assert main.__all__ == ["app"]
