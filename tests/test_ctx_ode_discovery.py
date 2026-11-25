
"""Offline tests for bounded NASA CTX ODE discovery."""

import copy
import json

import pytest
import requests

from src.pipeline import ctx_ode_discovery as ctx


@pytest.fixture
def product():
    return {
        "Data_Set_Id": ctx.EXPECTED_DATASET,
        "ihid": "MRO",
        "iid": "CTX",
        "pt": "EDR",
        "Target_name": "MARS",
        "pdsid": "T01_000883_2006_XI_20N281W",
        "PDSVolume_Id": "MROX_0005",
        "LabelFileName": "t01_000883_2006_xi_20n281w.img",
        "Product_creation_time": "2007-05-18T01:07:39.000",
        "Product_files": {
            "Product_file": [
                {
                    "Type": "Product",
                    "FileName": "T01_000883_2006_XI_20N281W.IMG",
                    "KBytes": "35001",
                    "URL": (
                        "https://planetarydata.jpl.nasa.gov/"
                        "img/data/mro/ctx/example.IMG"
                    ),
                },
                {
                    "Type": "Browse",
                    "FileName": "example.jpeg",
                    "KBytes": "19",
                    "URL": (
                        "https://planetarydata.jpl.nasa.gov/"
                        "img/data/mro/ctx/example.jpeg"
                    ),
                },
                {
                    "Type": "Derived",
                    "FileName": "example.kml",
                    "KBytes": "3",
                    "URL": (
                        "https://ode.rsl.wustl.edu/"
                        "mars/datafile/kmlfiles/example.kml"
                    ),
                },
            ]
        },
    }


@pytest.fixture
def payload(product):
    return {
        "ODEResults": {
            "Products": {
                "Product": [product],
            }
        }
    }


def raw_json(payload):
    return json.dumps(payload).encode("utf-8")


class FakeResponse:
    def __init__(
        self,
        raw=b"",
        status=200,
        content_type="application/json; charset=utf-8",
        content_length=None,
    ):
        self.raw = raw
        self.status_code = status
        self.headers = {"Content-Type": content_type}

        if content_length is not None:
            self.headers["Content-Length"] = str(content_length)

        self.closed = False

    def iter_content(self, chunk_size):
        for index in range(0, len(self.raw), chunk_size):
            yield self.raw[index:index + chunk_size]

    def close(self):
        self.closed = True


class FakeSession:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))

        if self.error is not None:
            raise self.error

        return self.response


def test_real_response_shape_normalized(payload):
    result = ctx.parse_ode_response(payload)

    assert len(result) == 1
    assert result[0]["product_id"] == (
        "T01_000883_2006_XI_20N281W"
    )
    assert result[0]["dataset_id"] == ctx.EXPECTED_DATASET
    assert len(result[0]["files"]) == 3
    assert result[0]["scientific_processing_approved"] is False


def test_single_product_mapping_supported(payload):
    item = payload["ODEResults"]["Products"]["Product"][0]
    payload["ODEResults"]["Products"]["Product"] = item

    assert len(ctx.parse_ode_response(payload)) == 1


def test_empty_product_list_is_not_scientific_approval():
    result = ctx.analyze_response_bytes(raw_json({
        "ODEResults": {"Products": {"Product": []}}
    }))

    assert result["returned_products"] == 0
    assert result["geographic_footprints_verified"] is False
    assert result["scientific_processing_approved"] is False


def test_sorted_product_ids(product):
    first = copy.deepcopy(product)
    second = copy.deepcopy(product)
    second["pdsid"] = "P02_001754_2021_XI_22N281W"

    result = ctx.parse_ode_response({
        "ODEResults": {
            "Products": {"Product": [first, second]}
        }
    })

    assert [item["product_id"] for item in result] == [
        "P02_001754_2021_XI_22N281W",
        "T01_000883_2006_XI_20N281W",
    ]


def test_duplicate_product_rejected(product):
    with pytest.raises(
        ctx.CTXDiscoveryError, match="Duplicate"
    ):
        ctx.parse_ode_response({
            "ODEResults": {
                "Products": {
                    "Product": [product, copy.deepcopy(product)]
                }
            }
        })


def test_excessive_products_rejected(product):
    with pytest.raises(
        ctx.CTXDiscoveryError, match="count"
    ):
        ctx.parse_ode_response({
            "ODEResults": {
                "Products": {
                    "Product": [product] * 4
                }
            }
        })


@pytest.mark.parametrize("field,value", [
    ("ihid", "MGS"),
    ("iid", "MOLA"),
    ("pt", "RDR"),
    ("Target_name", "EARTH"),
    ("Data_Set_Id", "UNVERIFIED"),
])
def test_wrong_observation_metadata_rejected(
    payload, field, value
):
    payload["ODEResults"]["Products"]["Product"][0][
        field
    ] = value

    with pytest.raises(
        ctx.CTXDiscoveryError, match="instrument"
    ):
        ctx.parse_ode_response(payload)


@pytest.mark.parametrize("url", [
    "http://planetarydata.jpl.nasa.gov/example.IMG",
    "https://evil.example/example.IMG",
    "https://planetarydata.jpl.nasa.gov.evil.example/file",
    "https://user@planetarydata.jpl.nasa.gov/file",
    "https://ode.rsl.wustl.edu:8443/file",
])
def test_untrusted_resource_url_rejected(payload, url):
    item = payload["ODEResults"]["Products"][
        "Product"
    ][0]["Product_files"]["Product_file"][0]

    item["URL"] = url

    with pytest.raises(
        ctx.CTXDiscoveryError, match="unsafe"
    ):
        ctx.parse_ode_response(payload)


def test_missing_primary_archive_file_rejected(payload):
    files = payload["ODEResults"]["Products"][
        "Product"
    ][0]["Product_files"]["Product_file"]

    payload["ODEResults"]["Products"][
        "Product"
    ][0]["Product_files"]["Product_file"] = files[1:]

    with pytest.raises(
        ctx.CTXDiscoveryError, match="primary"
    ):
        ctx.parse_ode_response(payload)


def test_invalid_file_size_rejected(payload):
    payload["ODEResults"]["Products"][
        "Product"
    ][0]["Product_files"]["Product_file"][0][
        "KBytes"
    ] = "unknown"

    with pytest.raises(
        ctx.CTXDiscoveryError, match="file-size"
    ):
        ctx.parse_ode_response(payload)


def test_missing_ode_root_rejected():
    with pytest.raises(
        ctx.CTXDiscoveryError, match="ODEResults"
    ):
        ctx.parse_ode_response({})


def test_invalid_json_rejected():
    with pytest.raises(
        ctx.CTXDiscoveryError, match="invalid JSON"
    ):
        ctx.analyze_response_bytes(b"{broken")


def test_fetch_metadata_is_bounded(payload):
    raw = raw_json(payload)
    response = FakeResponse(
        raw,
        content_length=len(raw),
    )

    session = FakeSession(response=response)
    result = ctx.fetch_ode_metadata(session=session)

    assert result == raw
    assert response.closed

    url, arguments = session.calls[0]

    assert url == ctx.ODE_URL
    assert arguments["allow_redirects"] is False
    assert arguments["stream"] is True
    assert arguments["params"]["limit"] == 3


@pytest.mark.parametrize("status", [301, 307, 403, 500])
def test_http_errors_rejected(status):
    response = FakeResponse(status=status)

    with pytest.raises(
        ctx.CTXDiscoveryError, match="HTTP"
    ):
        ctx.fetch_ode_metadata(
            session=FakeSession(response=response)
        )

    assert response.closed


def test_html_response_rejected():
    response = FakeResponse(
        b"<html></html>",
        content_type="text/html",
    )

    with pytest.raises(
        ctx.CTXDiscoveryError, match="JSON"
    ):
        ctx.fetch_ode_metadata(
            session=FakeSession(response=response)
        )


def test_oversized_response_rejected():
    response = FakeResponse(
        raw=b"x" * (ctx.MAX_RESPONSE_BYTES + 1)
    )

    with pytest.raises(
        ctx.CTXDiscoveryError, match="size limit"
    ):
        ctx.fetch_ode_metadata(
            session=FakeSession(response=response)
        )


def test_content_length_mismatch_rejected(payload):
    raw = raw_json(payload)

    response = FakeResponse(
        raw,
        content_length=len(raw) + 1,
    )

    with pytest.raises(
        ctx.CTXDiscoveryError, match="Content-Length"
    ):
        ctx.fetch_ode_metadata(
            session=FakeSession(response=response)
        )


def test_timeout_rejected():
    session = FakeSession(
        error=requests.Timeout("synthetic timeout")
    )

    with pytest.raises(
        ctx.CTXDiscoveryError, match="request failed"
    ):
        ctx.fetch_ode_metadata(session=session)


def test_offline_discovery_is_deterministic(payload, tmp_path):
    raw_path = tmp_path / ctx.RAW_FILE
    raw_path.write_bytes(raw_json(payload))

    first = ctx.discover_ctx(tmp_path)
    first_report = (
        tmp_path / ctx.AUDIT_FILE
    ).read_bytes()

    second = ctx.discover_ctx(tmp_path)

    assert first == second
    assert (tmp_path / ctx.AUDIT_FILE).read_bytes() == first_report


def test_offline_missing_response_rejected(tmp_path):
    with pytest.raises(
        ctx.CTXDiscoveryError, match="missing"
    ):
        ctx.discover_ctx(tmp_path)


def test_live_discovery_saves_metadata(payload, tmp_path):
    raw = raw_json(payload)
    session = FakeSession(
        response=FakeResponse(raw)
    )

    result = ctx.discover_ctx(
        tmp_path,
        live=True,
        session=session,
    )

    assert result["returned_products"] == 1
    assert result["acquisition_mode"] == "live"
    assert result["scientific_processing_approved"] is False
    assert (tmp_path / ctx.RAW_FILE).read_bytes() == raw


def test_invalid_live_response_saves_nothing(tmp_path):
    session = FakeSession(
        response=FakeResponse(b"invalid")
    )

    with pytest.raises(ctx.CTXDiscoveryError):
        ctx.discover_ctx(
            tmp_path,
            live=True,
            session=session,
        )

    assert not (tmp_path / ctx.RAW_FILE).exists()


def test_offline_cli(payload, tmp_path, capsys):
    (tmp_path / ctx.RAW_FILE).write_bytes(
        raw_json(payload)
    )

    report = ctx.main([
        "--destination", str(tmp_path)
    ])

    captured = capsys.readouterr().out

    assert report["acquisition_mode"] == "offline"
    assert '"returned_products": 1' in captured
