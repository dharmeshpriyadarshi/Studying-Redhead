
"""Tests for scientific planetary source provenance."""

from copy import deepcopy

import pytest
import yaml

from src.pipeline.dataset_catalog import (
    load_catalog,
    summarize_catalog,
    validate_catalog,
)


@pytest.fixture
def candidate():
    return {
        "record_id": "ctx_candidate",
        "status": "source_candidate",
        "target_body": "Mars",
        "mission": "Mars Reconnaissance Orbiter",
        "instrument": "CTX",
        "modality": "orbital_imagery",
        "archive": "NASA PDS",
        "landing_page": (
            "https://pds.nasa.gov/example"
        ),
        "collection_identifier": None,
        "identifier_scheme": None,
        "product_identifier": None,
        "product_label_url": None,
        "processing_level": None,
        "spatial_reference": None,
        "resolution": None,
        "measurement_units": None,
        "observation_time": None,
        "footprint": None,
        "calibration_status": "not_assessed",
        "usage_review": "pending",
        "sha256": None,
        "notes": "Synthetic test candidate.",
    }


def test_valid_candidate(candidate):
    records = validate_catalog({
        "schema_version": 1,
        "records": [candidate],
    })

    assert len(records) == 1

    summary = summarize_catalog(records)

    assert summary["source_candidates"] == 1
    assert summary["metadata_documented"] == 0


def test_load_yaml(tmp_path, candidate):
    path = tmp_path / "catalog.yaml"

    path.write_text(
        yaml.safe_dump({
            "schema_version": 1,
            "records": [candidate],
        }),
        encoding="utf-8",
    )

    assert len(load_catalog(path)) == 1


def test_duplicate_record_rejected(candidate):
    with pytest.raises(ValueError, match="Duplicate"):
        validate_catalog({
            "schema_version": 1,
            "records": [candidate, deepcopy(candidate)],
        })


def test_missing_field_rejected(candidate):
    candidate.pop("archive")

    with pytest.raises(ValueError, match="fields"):
        validate_catalog({
            "schema_version": 1,
            "records": [candidate],
        })


def test_unknown_field_rejected(candidate):
    candidate["fake_verified"] = True

    with pytest.raises(ValueError, match="fields"):
        validate_catalog({
            "schema_version": 1,
            "records": [candidate],
        })


def test_non_https_rejected(candidate):
    candidate["landing_page"] = (
        "http://pds.nasa.gov/example"
    )

    with pytest.raises(ValueError, match="untrusted"):
        validate_catalog({
            "schema_version": 1,
            "records": [candidate],
        })


def test_lookalike_host_rejected(candidate):
    candidate["landing_page"] = (
        "https://pds.nasa.gov.attacker.example/data"
    )

    with pytest.raises(ValueError, match="untrusted"):
        validate_catalog({
            "schema_version": 1,
            "records": [candidate],
        })


def test_candidate_cannot_claim_product(candidate):
    candidate["product_identifier"] = "UNVERIFIED_PRODUCT"

    with pytest.raises(ValueError, match="must not claim"):
        validate_catalog({
            "schema_version": 1,
            "records": [candidate],
        })


def test_unreviewed_metadata_rejected(candidate):
    candidate["status"] = "metadata_documented"

    with pytest.raises(ValueError, match="requires"):
        validate_catalog({
            "schema_version": 1,
            "records": [candidate],
        })


def test_invalid_target_body(candidate):
    candidate["target_body"] = "Earth"

    with pytest.raises(ValueError, match="Mars"):
        validate_catalog({
            "schema_version": 1,
            "records": [candidate],
        })


def test_instrument_modality_mismatch(candidate):
    candidate["modality"] = "topography_grid"

    with pytest.raises(ValueError, match="mismatch"):
        validate_catalog({
            "schema_version": 1,
            "records": [candidate],
        })


def test_invalid_schema_version(candidate):
    with pytest.raises(ValueError, match="version"):
        validate_catalog({
            "schema_version": 2,
            "records": [candidate],
        })

# Supplementary scientific provenance and negative-case tests.
# All product identifiers and metadata below are synthetic test fixtures.

from src.pipeline.dataset_catalog import (
    main as catalog_main,
    trusted_https,
    validate_record,
)


@pytest.fixture
def reviewed_product(candidate):
    candidate.update({
        "status": "metadata_documented",
        "identifier_scheme": "PDS4",
        "product_identifier": "urn:nasa:pds:synthetic:example::1.0",
        "product_label_url": "https://pds.nasa.gov/example.xml",
        "processing_level": "derived",
        "spatial_reference": "Synthetic Mars reference",
        "resolution": "Synthetic resolution",
        "measurement_units": "metres",
        "footprint": "Synthetic footprint",
        "calibration_status": "reviewed",
        "usage_review": "reviewed",
    })
    return candidate


@pytest.mark.parametrize("scheme", ["PDS3", "PDS4"])
def test_documented_product_is_accepted(reviewed_product, scheme):
    reviewed_product["identifier_scheme"] = scheme

    if scheme == "PDS3":
        reviewed_product["product_identifier"] = "SYNTHETIC_PRODUCT"

    result = validate_record(reviewed_product)
    assert result["status"] == "metadata_documented"


def test_documented_product_valid_checksum(reviewed_product):
    reviewed_product["sha256"] = "a" * 64
    assert validate_record(reviewed_product)["sha256"] == "a" * 64


@pytest.mark.parametrize("value", [
    None,
    [],
    "not_a_mapping",
])
def test_record_rejects_non_mapping(value):
    with pytest.raises(ValueError, match="mapping"):
        validate_record(value)


@pytest.mark.parametrize("record_id", [
    "Invalid_ID",
    "invalid-id",
    "1invalid",
    "invalid id",
])
def test_rejects_invalid_record_id(candidate, record_id):
    candidate["record_id"] = record_id

    with pytest.raises(ValueError, match="record_id"):
        validate_record(candidate)


@pytest.mark.parametrize("field,value", [
    ("mission", ""),
    ("archive", " "),
    ("notes", None),
    ("instrument", ""),
])
def test_rejects_missing_identity_information(candidate, field, value):
    candidate[field] = value

    with pytest.raises(ValueError, match="Missing or invalid"):
        validate_record(candidate)


def test_rejects_unsupported_instrument(candidate):
    candidate["instrument"] = "UNSUPPORTED_INSTRUMENT"

    with pytest.raises(ValueError, match="Unsupported instrument"):
        validate_record(candidate)


def test_rejects_invalid_collection_identifier(candidate):
    candidate["collection_identifier"] = "not-a-pds-identifier"

    with pytest.raises(ValueError, match="collection identifier"):
        validate_record(candidate)


@pytest.mark.parametrize("checksum", [
    "abc123",
    "z" * 64,
])
def test_rejects_invalid_checksum(candidate, checksum):
    candidate["sha256"] = checksum

    with pytest.raises(ValueError, match="SHA-256"):
        validate_record(candidate)


@pytest.mark.parametrize("field,value", [
    ("product_identifier", "UNVERIFIED"),
    ("resolution", "6 metres"),
    ("observation_time", "2026-01-01"),
    ("sha256", "a" * 64),
])
def test_candidate_cannot_claim_reviewed_metadata(candidate, field, value):
    candidate[field] = value

    with pytest.raises(ValueError, match="must not claim"):
        validate_record(candidate)


def test_candidate_cannot_claim_calibration(candidate):
    candidate["calibration_status"] = "reviewed"

    with pytest.raises(ValueError, match="calibration"):
        validate_record(candidate)


def test_candidate_cannot_claim_usage_review(candidate):
    candidate["usage_review"] = "reviewed"

    with pytest.raises(ValueError, match="usage review"):
        validate_record(candidate)


@pytest.mark.parametrize("field", [
    "product_label_url",
    "processing_level",
    "spatial_reference",
    "resolution",
    "measurement_units",
    "footprint",
])
def test_documented_product_requires_metadata(reviewed_product, field):
    reviewed_product[field] = None

    with pytest.raises(ValueError, match="requires"):
        validate_record(reviewed_product)


def test_rejects_untrusted_product_label(reviewed_product):
    reviewed_product["product_label_url"] = (
        "https://untrusted.example/product.xml"
    )

    with pytest.raises(ValueError, match="product label URL"):
        validate_record(reviewed_product)


def test_rejects_unknown_identifier_scheme(reviewed_product):
    reviewed_product["identifier_scheme"] = "UNKNOWN"

    with pytest.raises(ValueError, match="identifier scheme"):
        validate_record(reviewed_product)


def test_rejects_invalid_pds4_product_identifier(reviewed_product):
    reviewed_product["product_identifier"] = "SYNTHETIC_PRODUCT"

    with pytest.raises(ValueError, match="PDS4 product identifier"):
        validate_record(reviewed_product)


def test_rejects_unreviewed_calibration(reviewed_product):
    reviewed_product["calibration_status"] = "not_assessed"

    with pytest.raises(ValueError, match="Calibration status"):
        validate_record(reviewed_product)


def test_rejects_unreviewed_data_use(reviewed_product):
    reviewed_product["usage_review"] = "pending"

    with pytest.raises(ValueError, match="Data-use review"):
        validate_record(reviewed_product)


def test_rejects_unknown_status(candidate):
    candidate["status"] = "scientifically_approved"

    with pytest.raises(ValueError, match="Unsupported status"):
        validate_record(candidate)


@pytest.mark.parametrize("payload", [
    None,
    [],
    "invalid_catalog",
])
def test_rejects_invalid_catalog_root(payload):
    with pytest.raises(ValueError, match="mapping"):
        validate_catalog(payload)


def test_rejects_unknown_catalog_keys(candidate):
    payload = {
        "schema_version": 1,
        "records": [candidate],
        "unverified_property": True,
    }

    with pytest.raises(ValueError, match="structure"):
        validate_catalog(payload)


def test_rejects_boolean_schema_version(candidate):
    with pytest.raises(ValueError, match="schema version"):
        validate_catalog({
            "schema_version": True,
            "records": [candidate],
        })


@pytest.mark.parametrize("records", [
    [],
    {},
    "not_a_list",
])
def test_rejects_invalid_record_inventory(records):
    with pytest.raises(ValueError, match="at least one"):
        validate_catalog({
            "schema_version": 1,
            "records": records,
        })


@pytest.mark.parametrize("url", [
    None,
    "http://pds.nasa.gov/example",
    "https://user@pds.nasa.gov/example",
    "https://pds.nasa.gov:invalid/example",
    "https://pds.nasa.gov.evil.example/example",
])
def test_rejects_untrusted_url_forms(url):
    assert trusted_https(url) is False


def test_valid_mola_candidate(candidate):
    candidate["instrument"] = "MOLA"
    candidate["mission"] = "Mars Global Surveyor"
    candidate["modality"] = "topography_grid"
    candidate["collection_identifier"] = (
        "urn:nasa:pds:synthetic:collection::1.0"
    )

    assert validate_record(candidate)["instrument"] == "MOLA"


def test_catalog_cli_summary(candidate, tmp_path, monkeypatch, capsys):
    import sys

    path = tmp_path / "synthetic_catalog.yaml"

    path.write_text(
        yaml.safe_dump({
            "schema_version": 1,
            "records": [candidate],
        }),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "dataset_catalog",
            "--config",
            str(path),
        ],
    )

    catalog_main()

    output = capsys.readouterr().out

    assert '"total_records": 1' in output
    assert '"source_candidates": 1' in output
