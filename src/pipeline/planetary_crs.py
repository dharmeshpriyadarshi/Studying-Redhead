
"""Reference-body and coordinate-convention safeguards.

This module validates metadata. It does not perform
Mars coordinate transformations.
"""

from collections.abc import Mapping

from rasterio.crs import CRS


class PlanetaryCRSError(ValueError):
    """Raised for unsupported or inconsistent spatial references."""


VALID_BODIES = {"Earth", "Mars"}

MARS_LATITUDE_TYPES = {
    "planetocentric",
    "planetographic",
}

MARS_LONGITUDE_DIRECTIONS = {
    "positive_east",
    "positive_west",
}

MARS_LONGITUDE_DOMAINS = {
    "0_360",
    "-180_180",
}

REQUIRED_COORDINATE_FIELDS = {
    "target_body",
    "latitude_type",
    "longitude_direction",
    "longitude_domain",
}


def validate_target_body(target_body):
    """Require an explicitly recognized reference body."""

    if (
        not isinstance(target_body, str)
        or target_body not in VALID_BODIES
    ):
        raise PlanetaryCRSError(
            "Target body must be explicitly Earth or Mars."
        )

    return target_body


def audit_mars_coordinate_metadata(metadata):
    """Validate a declared Mars geographic-coordinate convention.

    Returns an audit of potential convention adjustments.
    No coordinate values are transformed.
    """

    if not isinstance(metadata, Mapping):
        raise PlanetaryCRSError(
            "Mars coordinate metadata must be a mapping."
        )

    missing = REQUIRED_COORDINATE_FIELDS - set(metadata)

    if missing:
        raise PlanetaryCRSError(
            f"Missing Mars coordinate fields: {sorted(missing)}"
        )

    if metadata["target_body"] != "Mars":
        raise PlanetaryCRSError(
            "Expected Mars coordinate metadata."
        )

    latitude_type = metadata["latitude_type"]
    longitude_direction = metadata["longitude_direction"]
    longitude_domain = metadata["longitude_domain"]

    if latitude_type not in MARS_LATITUDE_TYPES:
        raise PlanetaryCRSError(
            "Unsupported Mars latitude type."
        )

    if longitude_direction not in MARS_LONGITUDE_DIRECTIONS:
        raise PlanetaryCRSError(
            "Unsupported Mars longitude direction."
        )

    if longitude_domain not in MARS_LONGITUDE_DOMAINS:
        raise PlanetaryCRSError(
            "Unsupported Mars longitude domain."
        )

    convention_review_required = (
        latitude_type != "planetocentric"
        or longitude_direction != "positive_east"
    )

    domain_normalization_required = (
        longitude_domain != "0_360"
    )

    return {
        "target_body": "Mars",
        "latitude_type": latitude_type,
        "longitude_direction": longitude_direction,
        "longitude_domain": longitude_domain,
        "convention_review_required": convention_review_required,
        "domain_normalization_required": (
            domain_normalization_required
        ),
        "coordinates_transformed": False,
        "scientific_reprojection_enabled": False,
    }


def validate_reprojection_request(
    target_body,
    source_crs,
    target_crs,
):
    """Fail closed when a request exceeds supported functionality.

    Current engineering support is limited to recognized Earth
    EPSG references. Mars transformations are disabled.
    """

    body = validate_target_body(target_body)

    if body == "Mars":
        raise PlanetaryCRSError(
            "Mars raster reprojection is disabled until "
            "planetary CRS definitions and transformations "
            "are scientifically validated."
        )

    try:
        source = CRS.from_user_input(source_crs)
        target = CRS.from_user_input(target_crs)

        source_epsg = source.to_epsg()
        target_epsg = target.to_epsg()

    except Exception as exc:
        raise PlanetaryCRSError(
            "Invalid Earth CRS definition."
        ) from exc

    if source_epsg is None or target_epsg is None:
        raise PlanetaryCRSError(
            "Earth processing currently requires recognized "
            "EPSG CRS definitions. Custom planetary CRS "
            "definitions are not accepted."
        )

    return {
        "target_body": "Earth",
        "source_crs": source.to_string(),
        "target_crs": target.to_string(),
        "source_epsg": source_epsg,
        "target_epsg": target_epsg,
        "validated_for_earth_processing": True,
    }
