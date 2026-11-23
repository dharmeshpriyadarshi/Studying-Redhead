# Studying Redhead — Scientific Limitations Register

Status: Active register; update whenever new evidence emerges.

## L01 — Earth-based engineering validation

Current processing tests use an Earth-referenced RGB raster.
They do not establish scientific validity for Martian observations.

Mitigation: Preserve these tests but audit real NASA products
before introducing planetary scientific claims.

## L02 — Planetary coordinate systems

The existing smoke-test transformation uses Earth EPSG codes.
Martian products require reference-body-aware projection handling.

Mitigation: Validate body, datum, coordinate convention,
projection definition, extent and measurement units.

## L03 — Instrument calibration

Current uint8 division by 255 is an engineering normalization,
not a CTX radiometric calibration procedure.

Mitigation: Use documented instrument-specific processing
and retain calibration and observation provenance.

## L04 — Unequal spatial resolution

CTX imagery and MOLA elevation have substantially different
sampling scales. Resampling does not create new observations.

Mitigation: Evaluate scale-aware contextual information
before attempting multimodal fusion.

## L05 — Ambiguous anomaly definitions

Unusual image patterns are not necessarily novel geology.
Some model outputs may correspond to artefacts.

Mitigation: Define proxy tasks, reference evidence and
false-positive review criteria before modelling.

## L06 — Geographic data leakage

Neighboring tiles or repeated observations can share
strong spatial dependencies.

Mitigation: Use geographical splits and audit overlapping
source footprints and observation lineage.

## L07 — Observational variability

Illumination, viewing geometry, resolution and image
processing may affect anomaly scores.

Mitigation: Conduct sensitivity experiments and document
potential confounders.

## L08 — Insufficient scientific training data

The existing reference raster produces only a small number
of usable tiles and is not planetary research data.

Mitigation: Select authentic products and assess statistical
coverage and sampling bias before model training.

## L09 — Engineering limitations

Large-file performance, concurrency, cache invalidation,
planetary product parsing and negative-case coverage
remain incomplete.

Mitigation: Expand the regression suite as capabilities
are introduced, preserving previous verified behavior.

## L10 — Evaluation uncertainty

Reference catalogues may omit features or contain positional,
interpretive and scale-related uncertainty.

Mitigation: Distinguish proxy performance from scientific
validity and quantify uncertainty where defensible.

## L11 — Spectral interpretation

CTX is a broad-band grayscale imaging instrument.
Detailed mineralogical or spectral interpretation is outside
the scope of the initial CTX-based experiment.

Mitigation: Introduce a suitable spectral instrument only
if a subsequent research question and data audit justify it.

## Research integrity requirement

Do not promote any limitation to resolved until supported
by a documented experiment, independent evidence or
verified engineering result.
