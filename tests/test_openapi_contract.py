"""The OpenAPI document is a faithful, typed contract (FND-04, ROADMAP SC4).

Hygiene (T-01-02): no raw request URL, params dict or header dict appears in an
assert expression or message.
"""

import pytest
import responses

from truthtrail.schemas.models import AnalyzeResponse, Problem

HTTP_METHODS = {"get", "put", "post", "delete", "patch", "options", "head"}
PROBLEM = "application/problem+json"
ERROR_CODES = ("422", "500", "502", "503")


@pytest.fixture
def spec(client) -> dict:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    return response.json()


def _resolve(spec: dict, node: dict) -> dict:
    while isinstance(node, dict) and "$ref" in node:
        node = spec["components"]["schemas"][node["$ref"].rsplit("/", 1)[-1]]
    return node


def _analyze_get(spec: dict) -> dict:
    return spec["paths"]["/analyze"]["get"]


def test_every_operation_has_typed_2xx_response(spec) -> None:
    operations = [
        (path, method, operation)
        for path, item in spec["paths"].items()
        for method, operation in item.items()
        if method in HTTP_METHODS
    ]
    assert operations
    for path, method, operation in operations:
        success = {c: r for c, r in operation["responses"].items() if c.startswith("2")}
        assert success, f"{method.upper()} {path}: no 2xx response"
        for code, response in success.items():
            if code == "204":
                continue
            schema = _resolve(spec, response["content"]["application/json"]["schema"])
            typed = (
                schema.get("properties")
                or schema.get("items")
                or schema.get("anyOf")
                or schema.get("oneOf")
                or schema.get("allOf")
            )
            assert typed, f"{method.upper()} {path} {code}: untyped schema"


def test_analyze_200_is_analyze_response(spec) -> None:
    ok = _analyze_get(spec)["responses"]["200"]["content"]["application/json"]["schema"]
    assert ok == {"$ref": "#/components/schemas/AnalyzeResponse"}
    envelope = _resolve(spec, ok)
    assert {"results", "meta"} <= set(envelope["properties"])

    items = envelope["properties"]["results"]["items"]
    variants = {variant["$ref"].rsplit("/", 1)[-1] for variant in items["anyOf"]}
    assert variants == {"DemoResult", "LiveResult"}

    schemas = spec["components"]["schemas"]
    assert "events" not in schemas["LiveResult"]["properties"]
    assert "events" in schemas["DemoResult"]["properties"]

    meta = _resolve(spec, envelope["properties"]["meta"])
    assert {"synthetic", "data_as_of", "source_status"} <= set(meta["required"])
    assert meta["properties"]["source_status"]["enum"] == ["ok", "empty", "fixture"]


def test_error_responses_are_problem_json(spec) -> None:
    responses = _analyze_get(spec)["responses"]
    for code in ERROR_CODES:
        assert code in responses, f"{code} is not declared"
        content = responses[code]["content"]
        assert set(content) == {PROBLEM}, f"{code} declares a media type the handlers never return"
        schema = _resolve(spec, content[PROBLEM]["schema"])
        assert {"code", "status", "synthetic", "source_status", "data_as_of"} <= set(
            schema["properties"]
        )
        assert content[PROBLEM]["schema"] == {"$ref": "#/components/schemas/Problem"}

    retry_after = responses["503"]["headers"]["Retry-After"]
    assert retry_after["schema"] == {"type": "integer"}


def test_query_parameter_is_constrained(spec) -> None:
    parameters = {p["name"]: p for p in _analyze_get(spec)["parameters"]}
    query = parameters["query"]
    assert query["required"] is True
    assert query["in"] == "query"
    assert query["schema"]["minLength"] == 1
    assert query["schema"]["maxLength"] == 200
    assert query["schema"]["pattern"]


def test_actual_bodies_match_declared_models(
    client, client_factory, mock_gnews, gnews_url, gnews_payload, gnews_article
) -> None:
    mock_gnews.get(
        gnews_url,
        json=gnews_payload(gnews_article(title="Mayor dies after long illness")),
    )
    live = client.get("/analyze", params={"query": "mayor"})
    assert live.status_code == 200
    live_model = AnalyzeResponse.model_validate(live.json())
    assert live_model.meta.synthetic is False

    mock_gnews.replace(responses.GET, gnews_url, json={"errors": ["x"]}, status=401)
    bad_key = client.get("/analyze", params={"query": "mayor"})
    assert bad_key.status_code == 502
    assert bad_key.headers["content-type"].startswith(PROBLEM)
    Problem.model_validate(bad_key.json())

    invalid = client.get("/analyze", params={"query": ""})
    assert invalid.status_code == 422
    Problem.model_validate(invalid.json())

    missing = client.get("/nope")
    assert missing.status_code == 404
    Problem.model_validate(missing.json())

    # Demo mode is switched on last: it changes the environment for the rest of the test.
    demo_client = client_factory(gnews_api_key=None, demo_mode="true")
    demo = demo_client.get("/analyze", params={"query": "anything"})
    assert demo.status_code == 200
    demo_model = AnalyzeResponse.model_validate(demo.json())
    assert demo_model.meta.synthetic is True


def test_openapi_copy_is_honest(spec) -> None:
    info = spec["info"]
    assert info["title"] == "TruthTrail API"
    assert "flag for human review" in info["description"]
    assert "flag for human review" in _analyze_get(spec)["summary"]


def test_description_matches_what_the_endpoint_does(
    spec, client, mock_gnews, gnews_url, gnews_article, gnews_payload
) -> None:
    """WR-04: the copy claims one article and no ranking; the request must really ask for one."""
    mock_gnews.get(gnews_url, json=gnews_payload(gnews_article()))
    client.get("/analyze", params={"query": "x"})
    asked_for = dict(mock_gnews.calls[0].request.params)["max"]

    description = spec["info"]["description"]
    summary = _analyze_get(spec)["summary"]
    assert asked_for == "1"
    assert "one article" in description
    assert "Nothing is ranked" in description
    assert "most recent matching headline" in summary
    # Any positive ranking claim would be false: nothing is sorted, and one article cannot be ordered.
    positive_claims = [w for w in ("Ranks ", "ranks ", "Ranking ", "prioritised list") if w in description + summary]
    assert positive_claims == []
