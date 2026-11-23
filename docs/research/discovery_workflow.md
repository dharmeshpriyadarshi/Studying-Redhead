# Studying Redhead — Planetary Metadata Discovery

Status: Engineering workflow; no science products approved.
Last reviewed: 2026-11-23

## Source systems

1. NASA PDS Search API:
   https://pds.nasa.gov/api/search/1/products

2. NASA PDS Geosciences Node Mars ODE:
   https://ode.rsl.wustl.edu/mars/

3. NASA PDS MOLA archive:
   https://pds-geosciences.wustl.edu/missions/mgs/megdr.html

## Current scope

The machine-readable catalog contains discovery candidates
for CTX and MOLA.

The MOLA MEG128 collection has an identified PDS4 LIDVID.
Individual science products are not yet approved.

CTX has no selected PDS4 collection identifier in the catalog.
Its PDS3/PDS4 discovery route requires a separate ODE audit.

## Discovery workflow

1. Validate the source catalog offline.
2. Select a versioned PDS4 collection identifier.
3. Request collection metadata from NASA PDS.
4. Request a bounded sample of collection members.
5. Reject unexpected identifiers and malformed responses.
6. Write a local machine-readable discovery report.
7. Keep the curated source catalog unchanged.
8. Independently inspect selected product labels.

## Scientific review requirements

For individual MOLA products, inspect:
- Product type: topography, planetary radius, counts, etc.
- Measurement units and reference surface.
- Resolution, grid dimensions and coverage.
- Projection, Mars datum and longitude convention.
- Scaling, offset and missing-data definitions.
- Observation history and derivation.
- Product version and provenance.

For CTX products, inspect:
- Original observation identifier and archive.
- EDR/RDR or other processing status.
- Radiometric calibration and map projection.
- Observation geometry and acquisition time.
- Image resolution, valid masks and artefacts.
- Coverage overlap with the proposed study region.

## Failure handling

A registry timeout, HTTP error, missing collection or empty
result must not be interpreted as proof that a planetary
dataset does not exist.

The PDS Search API may not index every archived product.
ODE and archive labels are additional authoritative sources.

## Interpretation restrictions

A successful discovery query proves only that the requested
metadata were available from the queried registry endpoint.

It does not establish:
- Scientific calibration.
- Accurate georeferencing.
- Product suitability.
- Valid pixel data.
- Geological significance.

Discovery outputs must never automatically become approved
science products.

## Observed registry limitation — 2026-11-23

A live NASA PDS Search API query successfully resolved
the MOLA MEG128 PDS4 collection identifier.

The collection-members endpoint reported:
- Returned members: 0
- Registry-reported hits: 0

This result is inconclusive regarding the contents
or completeness of the underlying MOLA archive.

The first discovery audit was produced before the
zero-hit completeness interpretation was corrected.
Its recorded sample_is_exhaustive value must not be
interpreted as evidence of archive completeness.

The original audit is retained unchanged.

Next scientific action:
Inspect the authoritative PDS Geosciences archive
and actual product labels independently.

No individual planetary science product is approved.
