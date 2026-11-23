# Studying Redhead — Planetary CRS Policy

Status: Engineering safeguard implemented; Mars reprojection disabled.
Date: 2026-11-23

## Scientific context

The project investigates Martian orbital observations.

The engineering test pipeline currently processes an Earth-based
raster using EPSG:32618 as source and EPSG:3857 as destination.

These are Earth coordinate reference systems and must not
be interpreted as suitable spatial references for Mars.

## Supported processing

Earth:
- Recognized EPSG source and target CRS definitions.
- Existing Rasterio/GDAL reprojection workflow.
- Validated Earth engineering smoke-test configuration.

Mars:
- Explicit target-body declaration.
- Latitude-type metadata validation.
- Longitude-direction metadata validation.
- Longitude-domain metadata validation.
- Convention-review flags.
- No coordinate transformations permitted yet.

## Mars coordinate conventions

The proposed reference convention for future assessment is:

- Target body: Mars
- Latitude type: planetocentric
- Longitude direction: positive east
- Candidate longitude domain: 0 to 360 degrees

Other supported declarations can be flagged for further review.

Coordinate-domain normalization and conversion between
planetographic and planetocentric latitude are not implemented.

The coordinate metadata validator does not certify an actual
planetary raster's CRS or instrument label.

## Product-level prerequisites

Before enabling Mars reprojection, establish:

1. Original planetary product identifier and archive label.
2. Instrument and product processing level.
3. Target-body reference frame and adopted radii or ellipsoid.
4. Latitude type and longitude direction.
5. Longitude domain and prime-meridian convention.
6. Source and target projection definitions.
7. Pixel-to-map affine transform and valid spatial extent.
8. Units, missing-data definitions and spatial registration.
9. Independent validation against trusted planetary references.

## Security and scientific integrity

A Mars request must never silently invoke an Earth projection.

Recognized EPSG definitions provide a limited safeguard for
the legacy Earth processing path. They do not independently
prove that a raster's pixel coordinates are correctly labelled.

The current fail-closed policy is intentional.

## Relationship with project configuration

configs/config.yaml contains:
- geospatial.planet: Mars (overall research target).
- pipeline.profile: earth_smoke_test (current runnable profile).

These properties describe different scopes and must not be
silently treated as equivalent.

Future planetary processing requires a separate, audited
pipeline profile rather than modifying the Earth smoke test.

## References

USGS Mars coordinate system:
https://planetarynames.wr.usgs.gov/Page/MARS/system

USGS planetary map projection concepts:
https://astrogeology.usgs.gov/docs/concepts/camera-geometry-and-projections/learning-about-map-projections/

USGS planetary projection guidance:
https://astrogeology.usgs.gov/docs/concepts/camera-geometry-and-projections/proj-projections/

## Remaining limitations

- Mars raster reprojection is not implemented.
- Product-level coordinate metadata are not yet verified.
- Planetary CRS authority identification requires assessment.
- No transformation accuracy has been established for Mars.
- The Earth EPSG guard cannot detect every mislabeled dataset.
- No CTX or MOLA product has been approved for processing.
