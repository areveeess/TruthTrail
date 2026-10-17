"""Content pins for the files that plan 02-02 moves (D-01, D-02, D-21, D-22).

"Identical" means identical after CR+LF to LF normalisation (D-21): the legacy
files were CR+LF in Phase 1 and are LF since the line-ending commit. The demo
fixture was always LF, so its bytes are hashed as they are.

Plan 02-02 edits exactly the keys of ``LEGACY_FILES`` (the new locations) and
nothing else, so a move that alters content fails here.
"""

import hashlib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

LEGACY_FILES = {
    "src/truthtrail/services/keyword_baseline.py": "7398c2cfd920b56d971324935956a1342159eef0b808da53b95ed91fab46f23a",
    "legacy/spread_simulator.py": "e8e61cde19601bfe99311df21fc79ec95ce49ba0f62fdace663c4033a53e362c",
    "legacy/users.py": "e222249346536212bc1e3d2c7beab00202f647023f9ecbc28bb9797d7a0abfae",
}
FIXTURE_FILE = "src/truthtrail/data/demo_analyze.json"
FIXTURE_SHA256 = "f47fc6926acf3ba976ef28db7d6382f1fcf2da28fad4f493e01fbdb7023f7ec2"


@pytest.mark.parametrize("relpath", sorted(LEGACY_FILES))
def test_legacy_files_are_frozen(relpath: str) -> None:
    data = (REPO_ROOT / relpath).read_bytes().replace(b"\r\n", b"\n")
    digest = hashlib.sha256(data).hexdigest()
    assert digest == LEGACY_FILES[relpath], f"{relpath} content changed"


def test_demo_fixture_bytes_are_unchanged() -> None:
    digest = hashlib.sha256((REPO_ROOT / FIXTURE_FILE).read_bytes()).hexdigest()
    assert digest == FIXTURE_SHA256, f"{FIXTURE_FILE} content changed"
