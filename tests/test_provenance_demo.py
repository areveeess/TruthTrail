"""Provenance envelope on /analyze: live results, empty results, demo fixture gating.

Hygiene (T-01-02): no raw request URL, params dict or header dict appears in an
assert expression or message.
"""

import re
from datetime import datetime, timedelta, timezone

DATA_AS_OF_FORMAT = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def _live_response(client, mock_gnews, gnews_url, gnews_payload, gnews_article):
    mock_gnews.get(
        gnews_url,
        json=gnews_payload(
            gnews_article(
                title="Mayor dies after long illness",
                source="Example Wire",
                published_at="2026-10-11T09:30:00Z",
            )
        ),
    )
    return client.get("/analyze", params={"query": "mayor"})


def test_live_result_contract(
    client, mock_gnews, gnews_url, gnews_payload, gnews_article
) -> None:
    response = _live_response(client, mock_gnews, gnews_url, gnews_payload, gnews_article)

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"results", "meta"}
    assert body["results"] == [
        {
            "headline": "Mayor dies after long illness",
            "source": "Example Wire",
            "published_at": "2026-10-11T09:30:00Z",
            "risk": "High",
            "risk_method": "keyword_baseline",
        }
    ]
    meta = body["meta"]
    assert meta["synthetic"] is False
    assert meta["source_status"] == "ok"
    assert DATA_AS_OF_FORMAT.match(meta["data_as_of"])
    data_as_of = datetime.strptime(meta["data_as_of"], "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=timezone.utc
    )
    assert abs(datetime.now(timezone.utc) - data_as_of) < timedelta(seconds=60)
    assert "2025-01-01" not in response.text


def test_live_result_has_no_events_key(
    client, mock_gnews, gnews_url, gnews_payload, gnews_article
) -> None:
    response = _live_response(client, mock_gnews, gnews_url, gnews_payload, gnews_article)

    result = response.json()["results"][0]
    assert set(result) == {"headline", "source", "published_at", "risk", "risk_method"}
