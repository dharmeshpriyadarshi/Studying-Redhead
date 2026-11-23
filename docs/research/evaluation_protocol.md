# Studying Redhead — Evaluation Protocol

Status: Proposed; no scientific experiments completed.

## Evaluation objectives

Evaluate whether methods identify useful unusual surface
patterns, generalize across regions and remain robust
to observational and processing variability.

## Baseline sequence

1. Local mean and variance statistics.
2. Robust median and median absolute deviation.
3. Image gradients and local texture descriptors.
4. PCA reconstruction residuals.
5. Isolation Forest and other justified classical methods.
6. Convolutional Autoencoder, if warranted.
7. Variational Autoencoder, if warranted.

Use comparable input observations and evaluation partitions.

## Geographic independence

- Partition by geographically distinct regions.
- Audit overlapping CTX footprints and repeated observations.
- Prevent overlapping source observations from crossing splits.
- Consider spatial buffers based on measured dependence.
- Fit preprocessing statistics using training data only.
- Keep final evaluation regions untouched during model selection.
- Retain immutable split manifests for reproducibility.

Random tile splitting is not the primary scientific evaluation.

## Reference evidence

Potential references include published crater catalogues,
geological maps and explicitly documented proxy tasks.

Known craters are not universally labelled anomalies.
Reference precision, mapping scale and annotation uncertainty
must be considered when interpreting results.

## Metrics

Where suitable labels exist:
- Precision at K and Recall at K.
- Average precision and AUPRC.
- AUROC where class definitions justify its use.

For reconstruction models:
- Masked reconstruction error.
- Error distributions across geographical regions.
- Stability of anomaly rankings.

For reliability:
- False-positive review.
- Uncertainty and variability across random seeds.
- Confidence intervals using suitable spatial resampling.

Do not report classification metrics without defensible labels.

## Robustness and artefact assessment

Investigate:
- Illumination and viewing geometry.
- Image brightness and contrast changes.
- Resolution and resampling methods.
- Missing pixels and masks.
- CTX seams, striping and calibration residuals.
- Tile edges and preprocessing boundaries.
- Terrain and geological-context differences.

## Model comparison

Use predefined datasets, preprocessing protocols,
evaluation regions and metric definitions.

Record all tested configurations, including negative results.
Do not claim improvement without appropriate comparisons.

## Interpretation

Report unusual model responses as anomaly candidates.
Independently assess geological relevance.
Separate instrument artefacts from observational surface features.

## Release criteria

Scientific claims require:
- Traceable and suitable observations.
- Reproducible preprocessing and geographic partitions.
- Classical baseline results.
- Appropriate quantitative or qualitative reference evidence.
- Robustness and uncertainty analysis.
- Explicit limitations.

Passing engineering tests alone does not satisfy these criteria.
