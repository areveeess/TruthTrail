"""The Phase 1 OpenAPI document is frozen as an immutable contract (D-08, D-20).

``tests/golden/openapi_phase1.json`` was dumped from the unmoved Phase 1 code and
is pinned by sha256 below. Later phases must not edit it: Phases 3-5 add their
own snapshots. The live document may differ from it only by the declared
additions: the new paths ``/health`` and ``/ready``, new ``429`` response
entries, and the ``const`` keyword on ``Problem.synthetic`` (D-20).

Hygiene: failure messages name differing top-level sections only and never dump
a whole document.
"""

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

GOLDEN_PATH = Path(__file__).parent / "golden" / "openapi_phase1.json"
GOLDEN_SHA256 = "dcd039653878201b74e6a49d3f033d556548ea8612912c2b6da6360683d7dad7"
ALLOWED_NEW_PATHS = {"/health", "/ready"}
ALLOWED_NEW_RESPONSE_CODES = {"429"}
HTTP_METHODS = {"get", "put", "post", "delete", "patch", "options", "head"}


def load_golden() -> dict[str, Any]:
    """Return the parsed frozen Phase 1 document."""
    return json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


def phase1_view(current: dict[str, Any], base: dict[str, Any]) -> dict[str, Any]:
    """Return ``current`` with only the declared additions removed."""
    view = copy.deepcopy(current)
    view["paths"] = {p: v for p, v in view["paths"].items() if p in base["paths"]}
    for path, item in view["paths"].items():
        for method, operation in item.items():
            if method not in HTTP_METHODS:
                continue
            base_codes = base["paths"][path].get(method, {}).get("responses", {})
            for code in list(operation.get("responses", {})):
                if code in ALLOWED_NEW_RESPONSE_CODES and code not in base_codes:
                    del operation["responses"][code]
    base_schemas = base["components"]["schemas"]
    view["components"]["schemas"] = {
        name: schema
        for name, schema in view["components"]["schemas"].items()
        if name in base_schemas
    }
    # Declared amendment D-20: Problem.synthetic becomes Literal[False].
    synthetic = view["components"]["schemas"].get("Problem", {}).get("properties", {}).get("synthetic")
    if isinstance(synthetic, dict):
        synthetic.pop("const", None)
    return view


def test_golden_file_is_the_pinned_phase1_snapshot() -> None:
    digest = hashlib.sha256(GOLDEN_PATH.read_bytes()).hexdigest()
    assert digest == GOLDEN_SHA256, "golden snapshot bytes changed; it is immutable"
    assert list(load_golden()["paths"]) == ["/analyze"]


def test_phase1_contract_is_preserved(client: Any) -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    base = load_golden()
    view = phase1_view(response.json(), base)
    differing = sorted(key for key in set(view) | set(base) if view.get(key) != base.get(key))
    assert not differing, f"Phase 1 contract changed in top-level sections: {differing}"


def test_only_declared_additions_exist(client: Any) -> None:
    current = client.get("/openapi.json").json()
    base = load_golden()
    new_paths = set(current["paths"]) - set(base["paths"])
    assert new_paths <= ALLOWED_NEW_PATHS, f"undeclared paths: {sorted(new_paths - ALLOWED_NEW_PATHS)}"
    for path, item in base["paths"].items():
        for method, operation in item.items():
            if method not in HTTP_METHODS:
                continue
            current_codes = set(current["paths"][path][method]["responses"])
            extra = current_codes - set(operation["responses"])
            assert extra <= ALLOWED_NEW_RESPONSE_CODES, (
                f"undeclared response codes on {method.upper()} {path}: "
                f"{sorted(extra - ALLOWED_NEW_RESPONSE_CODES)}"
            )
