
"""Offline tests for pinned NASA MOLA label acquisition."""

import hashlib
import json

import pytest
import requests

from src.pipeline import pds_archive_discovery as archive


@pytest.fixture
def valid_xml():
    ns = archive.PDS_NAMESPACE

    return (
        f'<Product_Observational xmlns="{ns}">'
        "<Identification_Area>"
        f"<logical_identifier>{archive.EXPECTED_LID}"
        "</logical_identifier>"
        "</Identification_Area>"
        "</Product_Observational>"
    ).encode("utf-8")


class FakeResponse:
    def __init__(
        self,
        raw=b"",
        status=200,
        content_type="application/xml",
        declared_size=None,
    ):
        self.raw = raw
        self.status_code = status
        self.headers = {
            "Content-Type": content_type,
        }

        if declared_size is not None:
            self.headers["Content-Length"] = str(
                declared_size
            )

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


def test_valid_pds4_identity(valid_xml):
    result = archive.inspect_label(valid_xml)

    assert result["identity_verified"] is True
    assert result["logical_identifier"] == archive.EXPECTED_LID
    assert result["size_bytes"] == len(valid_xml)


def test_matching_sha256(valid_xml):
    digest = hashlib.sha256(valid_xml).hexdigest()

    result = archive.inspect_label(
        valid_xml,
        expected_sha256=digest,
    )

    assert result["sha256"] == digest


def test_checksum_mismatch_rejected(valid_xml):
    with pytest.raises(
        archive.ArchiveDiscoveryError,
        match="SHA-256",
    ):
        archive.inspect_label(
            valid_xml,
            expected_sha256="0" * 64,
        )


@pytest.mark.parametrize("raw", [
    b"",
    b"not XML",
    b"<Product_Observational>",
    b"<!DOCTYPE example><example/>",
    b"<!ENTITY example 'unsafe'>",
])
def test_invalid_xml_rejected(raw):
    with pytest.raises(archive.ArchiveDiscoveryError):
        archive.inspect_label(raw)


def test_oversized_xml_rejected(valid_xml):
    with pytest.raises(
        archive.ArchiveDiscoveryError,
        match="size limit",
    ):
        archive.inspect_label(
            valid_xml + b" " * archive.MAX_LABEL_BYTES
        )


def test_wrong_product_root_rejected(valid_xml):
    raw = valid_xml.replace(
        b"Product_Observational",
        b"Product_Collection",
    )

    with pytest.raises(
        archive.ArchiveDiscoveryError,
        match="Product_Observational",
    ):
        archive.inspect_label(raw)


def test_wrong_product_identifier_rejected(valid_xml):
    raw = valid_xml.replace(
        archive.EXPECTED_LID.encode(),
        b"urn:nasa:pds:synthetic:incorrect",
    )

    with pytest.raises(
        archive.ArchiveDiscoveryError,
        match="logical identifier",
    ):
        archive.inspect_label(raw)


def test_missing_identification_area_rejected(valid_xml):
    raw = (
        f'<Product_Observational xmlns="'
        f'{archive.PDS_NAMESPACE}"/>'
    ).encode()

    with pytest.raises(
        archive.ArchiveDiscoveryError,
        match="Identification_Area",
    ):
        archive.inspect_label(raw)


def test_bounded_fetch_success(valid_xml):
    response = FakeResponse(
        valid_xml,
        declared_size=len(valid_xml),
    )
    session = FakeSession(response=response)

    result = archive.fetch_label(session=session)

    assert result == valid_xml
    assert response.closed
    assert len(session.calls) == 1

    url, kwargs = session.calls[0]

    assert url == archive.LABEL_URL
    assert kwargs["allow_redirects"] is False
    assert kwargs["stream"] is True


@pytest.mark.parametrize("status", [301, 307, 403, 404, 500])
def test_http_failures_rejected(status):
    response = FakeResponse(status=status)

    with pytest.raises(
        archive.ArchiveDiscoveryError,
        match="HTTP",
    ):
        archive.fetch_label(
            session=FakeSession(response=response)
        )

    assert response.closed


def test_html_response_rejected():
    response = FakeResponse(
        b"<html></html>",
        content_type="text/html",
    )

    with pytest.raises(
        archive.ArchiveDiscoveryError,
        match="XML metadata",
    ):
        archive.fetch_label(
            session=FakeSession(response=response)
        )

    assert response.closed


def test_large_declared_response_rejected():
    response = FakeResponse(
        declared_size=archive.MAX_LABEL_BYTES + 1
    )

    with pytest.raises(
        archive.ArchiveDiscoveryError,
        match="size",
    ):
        archive.fetch_label(
            session=FakeSession(response=response)
        )


def test_stream_size_limit_rejected():
    response = FakeResponse(
        raw=b"x" * (archive.MAX_LABEL_BYTES + 1)
    )

    with pytest.raises(
        archive.ArchiveDiscoveryError,
        match="size limit",
    ):
        archive.fetch_label(
            session=FakeSession(response=response)
        )


def test_content_length_mismatch_rejected(valid_xml):
    response = FakeResponse(
        valid_xml,
        declared_size=len(valid_xml) + 1,
    )

    with pytest.raises(
        archive.ArchiveDiscoveryError,
        match="Content-Length",
    ):
        archive.fetch_label(
            session=FakeSession(response=response)
        )


def test_network_timeout_rejected():
    session = FakeSession(
        error=requests.Timeout("synthetic timeout")
    )

    with pytest.raises(
        archive.ArchiveDiscoveryError,
        match="request failed",
    ):
        archive.fetch_label(session=session)


def test_offline_audit_is_deterministic(valid_xml, tmp_path):
    destination = tmp_path / "archive"
    destination.mkdir()

    (destination / archive.LABEL_NAME).write_bytes(
        valid_xml
    )

    digest = hashlib.sha256(valid_xml).hexdigest()

    first = archive.acquire_reference_label(
        destination,
        expected_sha256=digest,
    )

    audit_file = (
        destination / "verified_mola_label_audit.json"
    )

    first_bytes = audit_file.read_bytes()

    second = archive.acquire_reference_label(
        destination,
        expected_sha256=digest,
    )

    assert first == second
    assert audit_file.read_bytes() == first_bytes
    assert first["scientific_processing_approved"] is False
    assert first["acquisition_mode"] == "offline"
    assert json.loads(first_bytes) == first


def test_offline_rejects_missing_label(tmp_path):
    with pytest.raises(
        archive.ArchiveDiscoveryError,
        match="Local MOLA label missing",
    ):
        archive.acquire_reference_label(tmp_path)


def test_live_acquisition_saves_verified_label(
    valid_xml, tmp_path
):
    response = FakeResponse(
        valid_xml,
        declared_size=len(valid_xml),
    )

    digest = hashlib.sha256(valid_xml).hexdigest()

    result = archive.acquire_reference_label(
        tmp_path,
        live=True,
        session=FakeSession(response=response),
        expected_sha256=digest,
    )

    saved = (
        tmp_path / archive.LABEL_NAME
    ).read_bytes()

    assert saved == valid_xml
    assert result["acquisition_mode"] == "live"
    assert result["scientific_processing_approved"] is False


def test_failed_live_verification_saves_nothing(
    valid_xml, tmp_path
):
    response = FakeResponse(valid_xml)

    with pytest.raises(
        archive.ArchiveDiscoveryError,
        match="SHA-256",
    ):
        archive.acquire_reference_label(
            tmp_path,
            live=True,
            session=FakeSession(response=response),
            expected_sha256="0" * 64,
        )

    assert not (tmp_path / archive.LABEL_NAME).exists()


def test_cli_offline_mode(valid_xml, tmp_path, monkeypatch, capsys):
    (tmp_path / archive.LABEL_NAME).write_bytes(
        valid_xml
    )

    monkeypatch.setattr(
        archive,
        "PINNED_SHA256",
        hashlib.sha256(valid_xml).hexdigest(),
    )

    result = archive.main([
        "--destination", str(tmp_path),
    ])

    output = capsys.readouterr().out

    assert result["acquisition_mode"] == "offline"
    assert '"identity_verified": true' in output
