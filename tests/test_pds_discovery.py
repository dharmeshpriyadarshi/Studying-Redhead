
"""Offline tests for NASA PDS4 metadata discovery."""

import json
import sys

import pytest
import requests

from src.pipeline import pds_discovery as discovery


COLLECTION_ID = (
    "urn:nasa:pds:mgs_mola_topography_derived:"
    "data_meg128::1.0"
)


class FakeResponse:
    def __init__(
        self, payload=None, status=200,
        content_type="application/json", raw=None
    ):
        self.status_code = status
        self.headers = {"Content-Type": content_type}

        self.raw = (
            raw if raw is not None
            else json.dumps(payload).encode("utf-8")
        )

        self.closed = False

    def iter_content(self, chunk_size=65536):
        for offset in range(0, len(self.raw), chunk_size):
            yield self.raw[offset:offset + chunk_size]

    def close(self):
        self.closed = True


class FakeSession:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []
        self.closed = False

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses.pop(0)

    def close(self):
        self.closed = True


@pytest.fixture
def record():
    return {
        "record_id": "mola_meg128_candidate",
        "status": "source_candidate",
        "instrument": "MOLA",
        "collection_identifier": COLLECTION_ID,
    }


def successful_session():
    return FakeSession(
        FakeResponse({"id": COLLECTION_ID}),
        FakeResponse({
            "summary": {"hits": 2},
            "data": [
                {
                    "id": (
                        "urn:nasa:pds:mgs_mola_topography_derived:"
                        "data_meg128:example_a::1.0"
                    )
                },
                {
                    "id": (
                        "urn:nasa:pds:mgs_mola_topography_derived:"
                        "data_meg128:example_b::1.0"
                    )
                },
            ],
        }),
    )


def test_select_collection(record):
    selected = discovery.select_collection(
        [record], "mola_meg128_candidate"
    )

    assert selected is record


def test_missing_collection_rejected(record):
    record["collection_identifier"] = None

    with pytest.raises(
        discovery.DiscoveryError, match="No valid"
    ):
        discovery.select_collection(
            [record], "mola_meg128_candidate"
        )


def test_unknown_record_rejected(record):
    with pytest.raises(
        discovery.DiscoveryError, match="Unknown"
    ):
        discovery.select_collection([record], "other")


def test_discovery_is_unapproved(record):
    session = successful_session()
    original = record.copy()

    report = discovery.discover_collection(
        record, limit=2, session=session
    )

    assert report["audit_status"] == "discovery_only"
    assert report["scientific_processing_approved"] is False
    assert report["collection_identifier"] == COLLECTION_ID
    assert report["members"]["returned_count"] == 2
    assert report["members"]["reported_total_hits"] == 2
    assert report["members"]["sample_is_exhaustive"] is True
    assert len(report["outstanding_reviews"]) >= 5

    assert record == original
    assert len(session.calls) == 2
    assert session.calls[1][1]["params"] == {"limit": 2}

    for _, kwargs in session.calls:
        assert kwargs["allow_redirects"] is False
        assert kwargs["stream"] is True


def test_collection_identifier_mismatch(record):
    session = FakeSession(
        FakeResponse({"id": "urn:nasa:pds:other::1.0"})
    )

    with pytest.raises(
        discovery.DiscoveryError, match="mismatch"
    ):
        discovery.discover_collection(
            record, session=session
        )

    assert len(session.calls) == 1


@pytest.mark.parametrize(
    "response, expected",
    [
        (
            FakeResponse(status=302),
            "HTTP 302",
        ),
        (
            FakeResponse(content_type="text/html"),
            "did not return JSON",
        ),
        (
            FakeResponse(raw=b"{invalid-json"),
            "Invalid PDS API JSON",
        ),
    ],
)
def test_invalid_http_response(response, expected):
    session = FakeSession(response)

    with pytest.raises(
        discovery.DiscoveryError, match=expected
    ):
        discovery.bounded_json_get(
            session, discovery.API_ROOT
        )

    assert response.closed


def test_oversized_response_rejected(monkeypatch):
    monkeypatch.setattr(
        discovery, "MAX_RESPONSE_BYTES", 20
    )

    session = FakeSession(
        FakeResponse({"data": "x" * 100})
    )

    with pytest.raises(
        discovery.DiscoveryError, match="size limit"
    ):
        discovery.bounded_json_get(
            session, discovery.API_ROOT
        )


@pytest.mark.parametrize(
    "payload",
    [
        {"data": {}},
        {"data": [{"note": "missing identifier"}]},
        {
            "data": [
                {"id": "urn:nasa:pds:duplicate"},
                {"id": "urn:nasa:pds:duplicate"},
            ]
        },
    ],
)
def test_invalid_members_rejected(payload):
    with pytest.raises(discovery.DiscoveryError):
        discovery.extract_members(payload, 3)


def test_invalid_hit_count_rejected():
    payload = {
        "data": [{"id": "urn:nasa:pds:example"}],
        "summary": {"hits": 0},
    }

    with pytest.raises(
        discovery.DiscoveryError, match="hit count"
    ):
        discovery.extract_members(payload, 3)


@pytest.mark.parametrize("limit", [0, 11, True])
def test_bad_discovery_limit(record, limit):
    with pytest.raises(
        discovery.DiscoveryError, match="limit"
    ):
        discovery.discover_collection(record, limit)


def test_request_timeout_rejected():
    class TimeoutSession:
        def get(self, *args, **kwargs):
            raise requests.Timeout("Simulated timeout")

    with pytest.raises(
        discovery.DiscoveryError, match="Timeout"
    ):
        discovery.bounded_json_get(
            TimeoutSession(), discovery.API_ROOT
        )


def test_audit_written_atomically(record, tmp_path, monkeypatch):
    monkeypatch.setattr(
        discovery,
        "resolve_path",
        lambda _: tmp_path / "discovery",
    )

    report = discovery.discover_collection(
        record, limit=2, session=successful_session()
    )

    path = discovery.save_audit(report)

    assert path.is_file()
    assert not list(path.parent.glob("*.part"))

    saved = json.loads(path.read_text(encoding="utf-8"))

    assert saved["scientific_processing_approved"] is False
    assert saved["collection_identifier"] == COLLECTION_ID


def test_offline_cli_does_not_use_network(
    record, monkeypatch, capsys
):
    monkeypatch.setattr(
        discovery, "load_catalog", lambda _: [record]
    )

    monkeypatch.setattr(
        sys, "argv", ["pds_discovery"]
    )

    discovery.main()

    output = json.loads(capsys.readouterr().out)

    assert output["mode"] == "offline"
    assert output["network_requests"] == 0


def test_live_cli_uses_review_only_report(
    record, monkeypatch, capsys, tmp_path
):
    monkeypatch.setattr(
        discovery, "load_catalog", lambda _: [record]
    )

    monkeypatch.setattr(
        discovery,
        "discover_collection",
        lambda selected, limit: {
            "source_record_id": selected["record_id"],
            "audit_status": "discovery_only",
            "collection_identifier": COLLECTION_ID,
            "members": {"identifiers": []},
            "scientific_processing_approved": False,
        },
    )

    monkeypatch.setattr(
        discovery,
        "save_audit",
        lambda _: tmp_path / "audit.json",
    )

    monkeypatch.setattr(
        sys, "argv", [
            "pds_discovery", "--live",
            "--record", record["record_id"]
        ]
    )

    discovery.main()

    output = json.loads(capsys.readouterr().out)

    assert output["scientific_processing_approved"] is False

def test_verified_nasa_redirect():
    redirect = FakeResponse(status=307)
    redirect.headers["Location"] = (
        "https://pds.mcp.nasa.gov/api/search/1/products"
    )

    final = FakeResponse({"id": "test"})
    session = FakeSession(redirect, final)

    result = discovery.bounded_json_get(
        session, discovery.API_ROOT
    )

    assert result["id"] == "test"
    assert len(session.calls) == 2
    assert session.calls[1][0].startswith(
        "https://pds.mcp.nasa.gov/"
    )
    assert redirect.closed
    assert final.closed


@pytest.mark.parametrize("destination", [
    "https://evil.example/api/search/1/products",
    "https://pds.mcp.nasa.gov.evil.example/api/search/1/products",
    "http://pds.mcp.nasa.gov/api/search/1/products",
    "https://pds.mcp.nasa.gov/api/other",
])
def test_unsafe_redirect_rejected(destination):
    redirect = FakeResponse(status=307)
    redirect.headers["Location"] = destination

    session = FakeSession(redirect)

    with pytest.raises(
        discovery.DiscoveryError,
        match="Unsafe or unexpected",
    ):
        discovery.bounded_json_get(
            session, discovery.API_ROOT
        )

    assert len(session.calls) == 1
    assert redirect.closed


def test_multiple_redirects_rejected():
    first = FakeResponse(status=307)
    first.headers["Location"] = (
        "https://pds.mcp.nasa.gov/api/search/1/products"
    )

    second = FakeResponse(status=307)
    second.headers["Location"] = (
        "https://pds.mcp.nasa.gov/api/search/1/products"
    )

    session = FakeSession(first, second)

    with pytest.raises(
        discovery.DiscoveryError,
        match="redirect limit exceeded",
    ):
        discovery.bounded_json_get(
            session, discovery.API_ROOT
        )

    assert len(session.calls) == 2
    assert first.closed
    assert second.closed


def test_redirect_preserves_query_parameters():
    first = FakeResponse(status=307)
    first.headers["Location"] = (
        "https://pds.mcp.nasa.gov/api/search/1/products"
        "?limit=3"
    )

    final = FakeResponse({"data": []})
    session = FakeSession(first, final)

    result = discovery.bounded_json_get(
        session,
        discovery.API_ROOT,
        params={"limit": 3},
    )

    assert result == {"data": []}
    assert session.calls[1][1]["params"] is None
    assert len(session.calls) == 2

def test_zero_registry_hits_are_not_archive_completeness():
    result = discovery.extract_members(
        {
            "data": [],
            "summary": {"hits": 0},
        },
        limit=3,
    )

    assert result["returned_count"] == 0
    assert result["reported_total_hits"] == 0
    assert result["identifiers"] == []
    assert result["sample_is_exhaustive"] is False