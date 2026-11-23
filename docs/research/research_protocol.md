# Studying Redhead — Research Protocol

Status: Draft research protocol
Research domain: Martian orbital remote sensing
Evidence status: Engineering foundation verified; planetary study not yet executed

## Primary research question

To what extent can statistical and unsupervised machine learning
methods identify unusual morphological or textural patterns in
Martian orbital imagery while distinguishing surface features
from instrument, illumination, and preprocessing artefacts?

## Scientific scope

- Primary observation modality: MRO CTX grayscale imagery.
- Candidate contextual modality: MGS MOLA topography.
- Initial target: One bounded region selected after data audit.
- Measurement focus: Morphology, texture, brightness and terrain context.
- Out of scope initially: Mineral identification and hyperspectral inference.
- No geological discovery claims without independent evidence.

## Testable research hypotheses

H1: Some unsupervised methods will rank reference-associated
surface features above matched background regions.

H2: Advanced representation learning will not necessarily
outperform carefully constructed classical baselines.

H3: Anomaly rankings may change substantially with illumination,
resolution, masking, and preprocessing decisions.

H4: Geographically separated evaluation will produce a more
defensible estimate of generalization than random tile splitting.

These hypotheses are untested and may be rejected.

## Candidate datasets

1. CTX observations from authoritative NASA PDS collections.
2. MOLA gridded topography from authoritative NASA PDS collections.
3. Published geological maps or crater catalogues for contextual
   comparison and explicitly defined proxy evaluation.

Candidate datasets are not yet approved research inputs.

## Dataset acceptance criteria

Before accepting a dataset, record:
- Archive, collection, product identifier and version.
- Original access location and acquisition date.
- Instrument, mission and observation characteristics.
- Product processing level and calibration history.
- Spatial resolution, sampling and measurement units.
- CRS, coordinate convention, reference body and longitude direction.
- Spatial footprint, acquisition geometry and time.
- NoData definitions, masks and known artefacts.
- Data-use terms and redistribution requirements.
- Local checksum and processing provenance.

Unknown properties must remain explicitly unknown.

## Study region selection

Select a manageable geographical region only after reviewing:
- CTX coverage and product quality.
- Available contextual topography.
- Availability and suitability of independent references.
- Variation in illumination and surface characteristics.
- Feasibility of geographically separate evaluation areas.

Record the selection criteria and avoid choosing regions
solely because preliminary anomaly maps appear interesting.

## Methodological sequence

1. Audit authentic planetary products and provenance.
2. Inspect observational geometry, CRS and calibration.
3. Establish scientific preprocessing and valid-pixel masks.
4. Perform exploratory spatial data analysis.
5. Define observational units and spatial partitions.
6. Evaluate statistical and classical anomaly baselines.
7. Evaluate representation-learning methods if justified.
8. Compare models and analyse errors, uncertainty and artefacts.
9. Produce independently accessible scientific outputs.
10. Develop interactive visualization after validated modelling.

## Evidence and interpretation policy

Separate:
- Direct spacecraft observations and instrument metadata.
- Published geological interpretations and reference annotations.
- Model-generated anomaly scores and candidate detections.

An anomaly score is not a calibrated probability of discovery.
Results must be presented as conditional on data and methods.

## Reproducibility

Record dataset versions, configuration, source hashes,
software dependencies, split definitions, preprocessing settings,
model parameters, seeds, evaluation code and exclusions.

Existing Earth-based smoke tests are engineering evidence only.

## Current status

No planetary products have been integrated.
No scientific baselines or neural models have been evaluated.
No Martian geological anomalies have been established.
