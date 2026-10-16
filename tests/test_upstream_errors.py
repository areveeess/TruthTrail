"""Upstream failures become honest problem+json answers, never a fabricated 200.

Hygiene (T-01-02, T-01-18): no raw request URL, params dict or header dict appears
in an assert expression or message; booleans and single values are computed first.
"""

import logging

import pytest
import requests

import gnews_fetcher
from problems import UpstreamError


def test_gnews_401_returns_502_not_200(
    client, mock_gnews, gnews_url, fake_key, caplog
) -> None:
    """D-07 / ROADMAP success criterion 2: a GNews 401 is a 502, never a 200."""
    caplog.set_level(logging.DEBUG)
    mock_gnews.get(
        gnews_url, json={"errors": ["Invalid credentials (simulated)"]}, status=401
    )

    response = client.get("/analyze", params={"query": "x"})

    body = response.json()
    content_type = response.headers["content-type"]
    key_in_body = fake_key in response.text
    host_in_body = "gnews.io" in response.text
    key_in_logs = fake_key in caplog.text
    assert response.status_code == 502
    assert content_type.startswith("application/problem+json")
    assert body["type"] == "about:blank"
    assert body["title"] == "Bad Gateway"
    assert body["status"] == 502
    assert body["code"] == "upstream_unauthorized"
    assert body["upstream"] == "gnews"
    assert body["synthetic"] is False
    assert body["source_status"] == "upstream_error"
    assert body["data_as_of"] is None
    assert "results" not in body
    assert not key_in_body
    assert not host_in_body
    assert not key_in_logs


def test_adapter_error_carries_no_key_or_url(mock_gnews, gnews_url, fake_key) -> None:
    mock_gnews.get(gnews_url, json={"errors": ["simulated"]}, status=401)

    with pytest.raises(UpstreamError) as excinfo:
        gnews_fetcher.fetch_news("x", fake_key)

    exc = excinfo.value
    text = f"{exc!s} {exc!r}"
    key_leaked = fake_key in text
    host_leaked = "gnews.io" in text
    assert exc.status == 502
    assert exc.__cause__ is None
    assert exc.__suppress_context__ is True
    assert not key_leaked
    assert not host_leaked


def _leaky(exc_type: type[Exception], fake_key: str) -> Exception:
    """An exception whose text carries the key and the provider URL, as requests can."""
    return exc_type(f"simulated https://gnews.io/api/v4/search?q=x&apikey={fake_key}")


def _bad_article(mutate):
    """Case factory: one article from the builder, altered by ``mutate``."""

    def build(article, payload, key):
        item = article()
        mutate(item)
        return {"status": 200, "json": payload(item)}

    return build


def _drop_source(item: dict) -> None:
    del item["source"]


def _null_source_name(item: dict) -> None:
    item["source"]["name"] = None


def _status(code: int, **extra):
    def build(article, payload, key):
        return {"status": code, "json": {"errors": ["simulated provider error"]}, **extra}

    return build


def _raises(exc_type: type[Exception]):
    def build(article, payload, key):
        return {"body": _leaky(exc_type, key)}

    return build


def _body(body: str, status: int = 200):
    def build(article, payload, key):
        return {"status": status, "body": body}

    return build


def _json(value):
    def build(article, payload, key):
        return {"status": 200, "json": value}

    return build


BAD_502 = (502, "upstream_bad_response", None)

FAILURE_CASES = [
    pytest.param(_status(401), 502, "upstream_unauthorized", None, id="401"),
    pytest.param(_status(403), 502, "upstream_forbidden", None, id="403"),
    pytest.param(_status(400), *BAD_502, id="400-bad-request"),
    pytest.param(_status(404), *BAD_502, id="404"),
    pytest.param(_status(500), *BAD_502, id="500"),
    pytest.param(_status(503), *BAD_502, id="503"),
    pytest.param(
        _status(429, headers={"Retry-After": "7"}),
        503, "upstream_rate_limited", "7",
        id="429-retry-after-7",
    ),
    pytest.param(_status(429), 503, "upstream_rate_limited", "30", id="429-no-header"),
    pytest.param(
        _status(429, headers={"Retry-After": "99999"}),
        503, "upstream_rate_limited", "3600",
        id="429-capped-at-3600",
    ),
    pytest.param(
        _status(429, headers={"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}),
        503, "upstream_rate_limited", "30",
        id="429-http-date",
    ),
    pytest.param(
        _raises(requests.exceptions.ConnectTimeout), 503, "upstream_timeout", "30",
        id="connect-timeout",
    ),
    pytest.param(
        _raises(requests.exceptions.ReadTimeout), 503, "upstream_timeout", "30",
        id="read-timeout",
    ),
    pytest.param(
        _raises(requests.exceptions.ConnectionError), 503, "upstream_unreachable", "30",
        id="connection-error",
    ),
    pytest.param(
        _raises(requests.exceptions.SSLError), 503, "upstream_unreachable", "30",
        id="ssl-error",
    ),
    pytest.param(_body("<html>not json</html>"), *BAD_502, id="200-not-json"),
    pytest.param(_json([{"title": "a"}]), *BAD_502, id="200-json-list"),
    pytest.param(_json({}), *BAD_502, id="200-empty-object"),
    pytest.param(_json({"totalArticles": 3}), *BAD_502, id="200-no-articles-key"),
    pytest.param(
        _bad_article(lambda item: item.update(title=None)), *BAD_502, id="null-title"
    ),
    pytest.param(
        _bad_article(lambda item: item.update(title="   ")),
        *BAD_502,
        id="whitespace-title",
    ),
    pytest.param(_bad_article(_drop_source), *BAD_502, id="missing-source"),
    pytest.param(_bad_article(_null_source_name), *BAD_502, id="null-source-name"),
    pytest.param(
        _bad_article(lambda item: item.update(publishedAt="not-a-date")),
        *BAD_502,
        id="unparseable-published-at",
    ),
    pytest.param(
        _bad_article(lambda item: item.update(publishedAt="2026-10-11T09:30:00")),
        *BAD_502,
        id="naive-published-at",
    ),
]


@pytest.mark.parametrize(("build", "status", "code", "retry_after"), FAILURE_CASES)
def test_upstream_failures_are_honest(
    client,
    mock_gnews,
    gnews_url,
    gnews_article,
    gnews_payload,
    fake_key,
    build,
    status: int,
    code: str,
    retry_after,
) -> None:
    mock_gnews.get(gnews_url, **build(gnews_article, gnews_payload, fake_key))

    response = client.get("/analyze", params={"query": "x"})

    body = response.json()
    key_in_body = fake_key in response.text
    host_in_body = "gnews.io" in response.text
    assert response.status_code == status
    assert response.headers["content-type"].startswith("application/problem+json")
    assert body["code"] == code
    assert body["upstream"] == "gnews"
    assert body["status"] == status
    assert "results" not in body
    assert body["synthetic"] is False
    assert body["source_status"] == "upstream_error"
    assert body["data_as_of"] is None
    assert not key_in_body
    assert not host_in_body
    assert response.headers.get("retry-after") == retry_after


SUCCESS_CASES = [
    pytest.param(
        lambda article, payload: {"totalArticles": 0, "articles": []}, [], id="total-0-empty"
    ),
    pytest.param(lambda article, payload: {"totalArticles": 0}, [], id="total-0-no-articles"),
    pytest.param(lambda article, payload: {"articles": []}, [], id="empty-articles-only"),
    pytest.param(
        lambda article, payload: payload(
            article(title="  Padded headline  ", source="Example Wire")
        ),
        [
            {
                "title": "Padded headline",
                "source": "Example Wire",
                "publishedAt": "2026-10-11T09:30:00Z",
            }
        ],
        id="title-stripped-extra-fields-ignored",
    ),
    pytest.param(
        lambda article, payload: payload(
            article(published_at="2026-10-11T11:30:00+02:00")
        ),
        [
            {
                "title": "Local bakery wins award",
                "source": "Example Wire",
                "publishedAt": "2026-10-11T09:30:00Z",
            }
        ],
        id="published-at-converted-to-utc",
    ),
]


@pytest.mark.parametrize(("build", "expected"), SUCCESS_CASES)
def test_adapter_success_shapes(
    mock_gnews, gnews_url, gnews_article, gnews_payload, fake_key, build, expected
) -> None:
    mock_gnews.get(gnews_url, json=build(gnews_article, gnews_payload))

    result = gnews_fetcher.fetch_news("x", fake_key)

    assert result == expected


def test_request_uses_timeout_header_and_fixed_params(
    mock_gnews, gnews_url, gnews_article, gnews_payload, fake_key
) -> None:
    mock_gnews.get(gnews_url, json=gnews_payload(gnews_article()))

    gnews_fetcher.fetch_news("climate change", fake_key)

    request = mock_gnews.calls[0].request
    timeout_ok = request.req_kwargs["timeout"] == (3.05, 10)
    header_ok = request.headers.get("X-Api-Key") == fake_key
    params = dict(request.params)
    params_ok = params == {"q": "climate change", "lang": "en", "max": "1"}
    assert timeout_ok
    assert header_ok
    assert params_ok


LEAK_CASES = [
    pytest.param(_status(401), id="401"),
    pytest.param(_raises(requests.exceptions.ConnectTimeout), id="timeout"),
    pytest.param(_body("<html>not json</html>"), id="non-json"),
]


@pytest.mark.parametrize("build", LEAK_CASES)
def test_no_key_or_url_in_logs(
    mock_gnews, gnews_url, gnews_article, gnews_payload, fake_key, caplog, build
) -> None:
    caplog.set_level(logging.DEBUG)
    mock_gnews.get(gnews_url, **build(gnews_article, gnews_payload, fake_key))

    with pytest.raises(UpstreamError):
        gnews_fetcher.fetch_news("x", fake_key)

    adapter_records = [r for r in caplog.records if r.name == "gnews_fetcher"]
    messages = [r.getMessage() for r in adapter_records]
    key_in_logs = fake_key in caplog.text
    url_in_messages = any("http" in m or "gnews.io" in m for m in messages)
    has_warning = any(r.levelno == logging.WARNING for r in adapter_records)
    assert not key_in_logs
    assert not url_in_messages
    assert has_warning


RAISE_FROM_NONE_CASES = [
    pytest.param(_raises(requests.exceptions.ConnectTimeout), id="timeout"),
    pytest.param(_raises(requests.exceptions.ConnectionError), id="connection-error"),
    pytest.param(_body("<html>not json</html>"), id="non-json"),
]


@pytest.mark.parametrize("build", RAISE_FROM_NONE_CASES)
def test_adapter_exceptions_are_raised_from_none(
    mock_gnews, gnews_url, gnews_article, gnews_payload, fake_key, build
) -> None:
    mock_gnews.get(gnews_url, **build(gnews_article, gnews_payload, fake_key))

    with pytest.raises(UpstreamError) as excinfo:
        gnews_fetcher.fetch_news("x", fake_key)

    exc = excinfo.value
    text = f"{exc!s} {exc!r}"
    key_leaked = fake_key in text
    host_leaked = "gnews.io" in text
    assert exc.__cause__ is None
    assert exc.__suppress_context__ is True
    assert not key_leaked
    assert not host_leaked


@pytest.mark.parametrize("redirect_status", [301, 302, 307, 308])
def test_redirect_is_not_followed_and_maps_to_502(
    client, mock_gnews, gnews_url, gnews_article, gnews_payload, fake_key, redirect_status
) -> None:
    """WR-01 / D-16: X-Api-Key must never be re-sent to a redirect target."""
    target = "https://elsewhere.example.org/api"
    mock_gnews.get(
        gnews_url, status=redirect_status, headers={"Location": target}, body=""
    )
    mock_gnews.get(target, json=gnews_payload(gnews_article()))

    response = client.get("/analyze", params={"query": "x"})

    body = response.json()
    urls_called = [call.request.url for call in mock_gnews.calls]
    redirect_followed = any(url.startswith(target) for url in urls_called)
    key_in_body = fake_key in response.text
    assert response.status_code == 502
    assert body["code"] == "upstream_bad_response"
    assert len(urls_called) == 1
    assert not redirect_followed
    assert not key_in_body
