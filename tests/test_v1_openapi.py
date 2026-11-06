"""The /v1 OpenAPI contract, provenance on every route and the rate limit (D-23, D-24, D-27,
threats T-03-46, T-03-49, T-03-50 and T-03-52).

The walk proves: every operation below /v1 declares exactly 200, 422, 429, 500 and 503 (never
502), Retry-After on 429 and 503, only application/problem+json on the errors, a 200 body whose
``meta`` is ``V1Meta`` (``synthetic`` a constant false, ``data_as_of`` a nullable date-time), no
extra members on any /v1 model, no ``risk``, ``risk_method`` or ``claim_scores`` property, a
summary on every operation and a description on every parameter. The document is deterministic
and passes the copy guard. Every GET route answers with the provenance members over the seeded
database and with the 500 ``not_configured`` problem without an engine; the limiter answers 429
problem+json with Retry-After.
"""

import subprocess
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.pool import NullPool

PROBLEM_JSON = "application/problem+json"
HTTP_METHODS = {"get", "put", "post", "delete", "patch", "options", "head"}
V1_CODES = {"200", "422", "429", "500", "503"}
FORBIDDEN_PROPERTIES = {"risk", "risk_method", "claim_scores"}
REPO_ROOT = Path(__file__).resolve().parent.parent
EXPECTED_PATHS = {
    "/v1/cascades",
    "/v1/cascades/{cascade_id}",
    "/v1/cascades/{cascade_id}/tree",
    "/v1/cascades/{cascade_id}/timeline",
    "/v1/stats",
}


@pytest.fixture
def spec(client: Any) -> dict[str, Any]:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    document: dict[str, Any] = response.json()
    return document


def v1_operations(spec: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    return [
        (path, method, operation)
        for path, item in spec["paths"].items()
        if path.startswith("/v1/")
        for method, operation in item.items()
        if method in HTTP_METHODS
    ]


def schema_name(ref: str) -> str:
    return ref.rsplit("/", 1)[-1]


def reachable_schemas(spec: dict[str, Any], roots: list[str]) -> set[str]:
    schemas = spec["components"]["schemas"]
    seen: set[str] = set()
    stack = list(roots)
    while stack:
        name = stack.pop()
        if name in seen:
            continue
        seen.add(name)

        def refs(node: Any) -> Iterator[str]:
            if isinstance(node, dict):
                for key, value in node.items():
                    if key == "$ref" and isinstance(value, str):
                        yield schema_name(value)
                    else:
                        yield from refs(value)
            elif isinstance(node, list):
                for value in node:
                    yield from refs(value)

        stack.extend(refs(schemas[name]))
    return seen


def success_models(spec: dict[str, Any]) -> list[str]:
    return [
        schema_name(op["responses"]["200"]["content"]["application/json"]["schema"]["$ref"])
        for _p, _m, op in v1_operations(spec)
    ]


def test_the_v1_paths_are_exactly_the_planned_routes(spec: dict[str, Any]) -> None:
    assert {p for p in spec["paths"] if p.startswith("/v1")} == EXPECTED_PATHS
    for path, method, _op in v1_operations(spec):
        assert method == "get", path


def test_every_v1_operation_declares_exactly_the_contract_codes(spec: dict[str, Any]) -> None:
    operations = v1_operations(spec)
    assert len(operations) == len(EXPECTED_PATHS)
    for path, _method, operation in operations:
        responses = operation["responses"]
        assert set(responses) == V1_CODES, path
        assert "502" not in responses
        for code in ("429", "503"):
            header = responses[code]["headers"]["Retry-After"]
            assert header["schema"] == {"type": "integer"}, (path, code)
        for code in ("422", "429", "500", "503"):
            content = responses[code]["content"]
            assert set(content) == {PROBLEM_JSON}, (path, code)
            assert content[PROBLEM_JSON]["schema"] == {"$ref": "#/components/schemas/Problem"}
        assert "database" in responses["503"]["description"]
        assert set(responses["200"]["content"]) == {"application/json"}


def test_every_200_body_carries_a_v1_meta(spec: dict[str, Any]) -> None:
    schemas = spec["components"]["schemas"]
    for model in success_models(spec):
        meta = schemas[model]["properties"]["meta"]
        assert meta == {"$ref": "#/components/schemas/V1Meta"}, model
        assert "meta" in schemas[model]["required"], model
    v1_meta = schemas["V1Meta"]
    assert v1_meta["properties"]["synthetic"]["type"] == "boolean"
    assert v1_meta["properties"]["synthetic"]["const"] is False
    assert "default" not in v1_meta["properties"]["synthetic"]
    assert {"synthetic", "data_as_of", "source_status", "source_mode"} <= set(v1_meta["required"])
    variants = v1_meta["properties"]["data_as_of"]["anyOf"]
    assert {"type": "string", "format": "date-time"} in variants
    assert {"type": "null"} in variants
    assert v1_meta["properties"]["source_status"]["enum"] == ["ok", "empty", "stale"]
    assert v1_meta["properties"]["source_mode"]["enum"] == ["live", "replay"]


def test_every_v1_model_forbids_extra_members_and_has_no_risk_property(
    spec: dict[str, Any],
) -> None:
    schemas = spec["components"]["schemas"]
    reachable = reachable_schemas(spec, success_models(spec))
    assert {"V1Meta", "CascadeSummary", "TreeNode", "TimelineBucket", "LastRun"} <= reachable
    assert "LiveResult" not in reachable
    for name in reachable:
        schema = schemas[name]
        if "enum" in schema:
            continue
        assert schema.get("additionalProperties") is False, name
        properties = schema.get("properties", {})
        assert not FORBIDDEN_PROPERTIES & set(properties), name
        for prop, body in properties.items():
            assert body.get("description") or "$ref" in body, (name, prop)


def test_every_operation_has_a_summary_and_every_parameter_a_description(
    spec: dict[str, Any],
) -> None:
    for path, _method, operation in v1_operations(spec):
        assert operation.get("summary"), path
        assert "flag for human review" in operation["summary"], path
        assert "Observed subset of public Bluesky posts" in operation["description"], path
        for parameter in operation.get("parameters", []):
            assert parameter.get("description"), (path, parameter["name"])


def test_the_document_is_deterministic(client_factory: Callable[..., Any]) -> None:
    one = client_factory().get("/openapi.json").json()
    two = client_factory().get("/openapi.json").json()
    assert one == two


def test_the_copy_guard_passes_on_the_full_document(subprocess_env: dict[str, str]) -> None:
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "copy_guard.py")],
        cwd=REPO_ROOT,
        env={**subprocess_env, "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "copy-guard: clean" in result.stdout


# --- provenance on every route --------------------------------------------------------------
def concrete_paths(spec: dict[str, Any], cascade_id: int) -> list[str]:
    return sorted(p.replace("{cascade_id}", str(cascade_id)) for p in EXPECTED_PATHS)


@pytest.fixture(scope="module")
def seeded(seeded_db_url: str) -> Iterator[Engine]:
    engine = create_engine(seeded_db_url, poolclass=NullPool)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.mark.requires_db
def test_every_v1_route_answers_with_provenance(
    v1_client: Callable[..., Any], seeded_db_url: str, seeded: Engine, spec: dict[str, Any]
) -> None:
    with seeded.connect() as connection:
        cascade_id = int(connection.execute(text("SELECT min(id) FROM cascades")).scalar_one())
    client = v1_client(seeded_db_url)
    paths = concrete_paths(spec, cascade_id)
    assert len(paths) == len(EXPECTED_PATHS)
    for path in paths:
        response = client.get(path)
        assert response.status_code == 200, path
        meta = response.json()["meta"]
        assert set(meta) == {
            "synthetic",
            "data_as_of",
            "source_status",
            "source_mode",
            "observed_since",
        }, path
        assert meta["synthetic"] is False
        assert meta["data_as_of"] is not None
        assert meta["source_status"] in {"ok", "stale"}
        assert meta["source_mode"] == "replay"


def test_without_an_engine_every_route_is_not_configured(client: Any, spec: dict[str, Any]) -> None:
    for path in concrete_paths(spec, 1):
        response = client.get(path)
        assert response.status_code == 500, path
        assert response.headers["content-type"].startswith(PROBLEM_JSON)
        body = response.json()
        assert body["code"] == "not_configured"
        assert body["synthetic"] is False
        assert body["data_as_of"] is None
        assert "meta" not in body


# --- the rate limit -------------------------------------------------------------------------
def test_a_data_route_is_rate_limited_with_problem_json(
    client_factory: Callable[..., Any],
) -> None:
    client = client_factory(env={"RATE_LIMIT_V1": "2/minute"})
    statuses = [client.get("/v1/stats").status_code for _ in range(2)]
    limited = client.get("/v1/stats")
    assert statuses == [500, 500]  # no engine here: not_configured, but limited first
    assert limited.status_code == 429
    assert limited.headers["content-type"].startswith(PROBLEM_JSON)
    assert int(limited.headers["retry-after"]) >= 1
    assert limited.json()["code"] == "rate_limited"


@pytest.mark.requires_db
def test_the_limit_applies_before_any_database_work(
    v1_client: Callable[..., Any], seeded_db_url: str
) -> None:
    from sqlalchemy import event

    client = v1_client(seeded_db_url, env={"RATE_LIMIT_V1": "2/minute"})
    checkouts: list[int] = []
    event.listen(client.app.state.engine, "checkout", lambda *a: checkouts.append(1))
    assert [client.get("/v1/cascades").status_code for _ in range(2)] == [200, 200]
    before = len(checkouts)
    for _ in range(3):
        assert client.get("/v1/cascades").status_code == 429
    assert len(checkouts) == before  # a rejected request never takes a pool connection


def test_invalid_parameters_are_rejected_before_the_limiter_counts(
    client_factory: Callable[..., Any],
) -> None:
    """Parameter validation runs before the limiter wrapper (FastAPI resolves parameters first,
    as on the Phase 2 /analyze route), so a 422 costs no quota and touches no database; a check
    made inside the handler (the claim_id policy, a cursor of another sort) is counted."""
    client = client_factory(env={"RATE_LIMIT_V1": "2/minute"})
    invalid = [client.get("/v1/cascades", params={"limit": 0}).status_code for _ in range(5)]
    assert invalid == [422] * 5
    assert [client.get("/v1/cascades").status_code for _ in range(2)] == [500, 500]
    assert client.get("/v1/cascades").status_code == 429
    in_handler = client_factory(env={"RATE_LIMIT_V1": "2/minute", "CASCADE_MERGE_POLICY": "none"})
    counted = [in_handler.get("/v1/cascades", params={"claim_id": 1}).status_code for _ in range(3)]
    assert counted == [422, 422, 429]
