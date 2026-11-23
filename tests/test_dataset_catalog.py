
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
