
"""Tests for planetary reference-body and CRS safeguards."""

import pytest

from src.pipeline.planetary_crs import (
    PlanetaryCRSError,
    audit_mars_coordinate_metadata,
    validate_target_body,
    validate_reprojection_request,
)

from src.pipeline.geospatial_projection import (
    GeospatialProjector,
)


@pytest.fixture
def modern_mars_metadata():
    return {
        "target_body": "Mars",
        "latitude_type": "planetocentric",
        "longitude_direction": "positive_east",
        "longitude_domain": "0_360",
    }


def test_modern_mars_metadata_audit(modern_mars_metadata):
    result = audit_mars_coordinate_metadata(
        modern_mars_metadata
    )

    assert result["target_body"] == "Mars"
    assert result["convention_review_required"] is False
    assert result["domain_normalization_required"] is False
    assert result["coordinates_transformed"] is False
    assert result["scientific_reprojection_enabled"] is False


def test_legacy_mars_convention_flagged(modern_mars_metadata):
    modern_mars_metadata["latitude_type"] = "planetographic"
    modern_mars_metadata["longitude_direction"] = "positive_west"

    result = audit_mars_coordinate_metadata(
        modern_mars_metadata
    )

    assert result["convention_review_required"] is True
    assert result["coordinates_transformed"] is False


def test_alternate_longitude_domain_flagged(
    modern_mars_metadata
):
    modern_mars_metadata["longitude_domain"] = "-180_180"

    result = audit_mars_coordinate_metadata(
        modern_mars_metadata
    )

    assert result["domain_normalization_required"] is True


@pytest.mark.parametrize("field", [
    "target_body",
    "latitude_type",
    "longitude_direction",
    "longitude_domain",
])
def test_missing_coordinate_field_rejected(
    modern_mars_metadata, field
):
    modern_mars_metadata.pop(field)

    with pytest.raises(
        PlanetaryCRSError, match="Missing"
    ):
        audit_mars_coordinate_metadata(modern_mars_metadata)


@pytest.mark.parametrize("field,value", [
    ("latitude_type", "geocentric"),
    ("longitude_direction", "unknown"),
    ("longitude_domain", "unbounded"),
])
def test_invalid_mars_convention_rejected(
    modern_mars_metadata, field, value
):
    modern_mars_metadata[field] = value

    with pytest.raises(PlanetaryCRSError, match="Unsupported"):
        audit_mars_coordinate_metadata(modern_mars_metadata)


def test_earth_metadata_rejected_as_mars(
    modern_mars_metadata
):
    modern_mars_metadata["target_body"] = "Earth"

    with pytest.raises(PlanetaryCRSError, match="Expected Mars"):
        audit_mars_coordinate_metadata(modern_mars_metadata)


@pytest.mark.parametrize("metadata", [
    None,
    [],
    "Mars",
])
def test_non_mapping_metadata_rejected(metadata):
    with pytest.raises(PlanetaryCRSError, match="mapping"):
        audit_mars_coordinate_metadata(metadata)


@pytest.mark.parametrize("body", ["Earth", "Mars"])
def test_known_target_body_accepted(body):
    assert validate_target_body(body) == body


@pytest.mark.parametrize("body", [
    "Jupiter",
    "mars",
    "",
    None,
    42,
])
def test_unknown_target_body_rejected(body):
    with pytest.raises(
        PlanetaryCRSError, match="Target body"
    ):
        validate_target_body(body)


def test_existing_earth_projection_pair_allowed():
    report = validate_reprojection_request(
        "Earth",
        "EPSG:32618",
        "EPSG:3857",
    )

    assert report["target_body"] == "Earth"
    assert report["source_epsg"] == 32618
    assert report["target_epsg"] == 3857
    assert report["validated_for_earth_processing"] is True


def test_mars_reprojection_rejected():
    with pytest.raises(
        PlanetaryCRSError, match="Mars raster reprojection"
    ):
        validate_reprojection_request(
            "Mars",
            "EPSG:32618",
            "EPSG:3857",
        )


def test_unrecognized_reference_body_rejected():
    with pytest.raises(PlanetaryCRSError, match="Target body"):
        validate_reprojection_request(
            "Venus",
            "EPSG:32618",
            "EPSG:3857",
        )


def test_custom_planetary_crs_rejected_as_earth():
    synthetic_mars_crs = (
        "+proj=longlat +a=3396190 "
        "+b=3376200 +no_defs +type=crs"
    )

    with pytest.raises(
        PlanetaryCRSError,
        match="recognized EPSG",
    ):
        validate_reprojection_request(
            "Earth",
            synthetic_mars_crs,
            "EPSG:3857",
        )


def test_projector_rejects_mars_before_processing():
    with pytest.raises(
        PlanetaryCRSError, match="Mars raster reprojection"
    ):
        GeospatialProjector(
            target_crs="EPSG:3857",
            target_body="Mars",
        )


def test_projector_preserves_earth_default():
    projector = GeospatialProjector("EPSG:3857")

    assert projector.target_body == "Earth"


def test_projector_accepts_explicit_earth():
    projector = GeospatialProjector(
        target_crs="EPSG:3857",
        target_body="Earth",
    )

    assert projector.target_body == "Earth"
