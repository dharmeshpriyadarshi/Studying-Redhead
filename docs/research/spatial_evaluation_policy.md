# Studying Redhead — Spatial Evaluation Policy

Status: Synthetic engineering validation only.
Date: 2026-11-23

## Objective

Prevent spatial and source-scene leakage between
training, validation and held-out test observations.

A random observation-level split is not the project's
default scientific evaluation method.

## Partition requirements

1. All observations must use a common reference body,
   coordinate system and declared metric units.

2. All samples derived from the same source scene
   must remain in the same partition.

3. Samples intersecting common spatial grid blocks
   must remain in the same partition.

4. Overlapping or touching raster footprints must
   remain in the same partition.

5. A configured separation buffer is enforced
   between observations in different partitions.

6. Overlapping constraints are transitively grouped:
   if A conflicts with B and B conflicts with C,
   the entire connected group stays together.

7. At least three independent spatial components
   are needed for train, validation and test sets.

8. The partition must be deterministic for an
   unchanged input set, seed and configuration.

9. The generated manifest contains a cryptographic
   digest, assignment details and leakage audit.

## Important restrictions

- Coordinates are treated as planar metres.
- The program does not validate a planetary datum.
- The program does not transform coordinates.
- A user-supplied CRS name is a declaration,
  not independent scientific evidence.
- Only rectangular footprints are implemented.
- Spatial proximity alone does not exclude all
  forms of temporal, sensor or processing leakage.
- Transitive grouping may create very large groups.
- Requested split proportions are approximate.
- Actual partition counts must be reported.

## Scientific validation prerequisites

Before adopting this splitter for real Mars imagery:

- Obtain and independently review actual PDS labels.
- Establish the reference body and map projection.
- Verify planetary coordinate conventions and units.
- Validate spatial footprints and georegistration.
- Define source scene/acquisition relationships.
- Select spatial block size and exclusion buffer
  based on observation resolution, spatial
  correlation and research objectives.
- Verify train/test geographic independence.
- Freeze held-out test regions before tuning models.
- Document any unequal geographic coverage.

## Evaluation sequence

1. Authenticate and validate the source products.
2. Establish a defensible geographic region.
3. Audit the coordinates and observation footprints.
4. Select spatial blocks and separation buffers.
5. Generate and freeze the split manifest.
6. Fit all preprocessing on training data only.
7. Tune model selection on spatial validation data.
8. Evaluate once on untouched held-out regions.
9. Report per-region variability and uncertainty.

## Current status

Synthetic tests can exercise spatial partition rules.

No real Mars observation has been validated.
No scientific training or anomaly detection is
approved by this module alone.
