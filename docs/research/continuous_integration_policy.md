

\# Studying Redhead — Continuous Integration Policy



Status: Proposed automated engineering checks.

Date: 2026-11-23.



\## Purpose



Ensure that code changes do not silently violate the

project's scientific engineering safeguards.



CI does not establish scientific validity of Mars observations.



\## Environment



\- GitHub Actions

\- Ubuntu 24.04 runner

\- Python 3.11.9

\- Pinned development dependency inventory

\- No required repository secrets



\## Mandatory checks



1\. Install pinned development dependencies.

2\. Verify dependency integrity using pip check.

3\. Compile the Python source and tests.

4\. Check the research configuration contract.

5\. Validate the planetary source catalog.

6\. Verify dependency pin consistency.

7\. Check deterministic spatial partition behavior.

8\. Execute the full regression test suite.

9\. Enforce at least 85% combined branch-aware coverage.



\## Research safeguards



The currently runnable pipeline is an Earth-only

engineering smoke test.



The broader research target remains Mars.



CI rejects an unaudited global target CRS and

unauthorized changes to the Earth smoke-test profile.



Original raw data preservation must remain enabled.



Source-candidate entries are not scientifically approved.

Metadata documentation does not imply scientific approval.



Mars reprojection remains disabled until the planetary

coordinate definitions are independently validated.



\## Reproducibility



Dependency files and Python versions are fixed for the

current CI environment.



The quality contract verifies that direct requirement

pins agree with the development lock.



This is not a hash-verified dependency supply-chain lock

and does not guarantee bit-for-bit environment identity.



Spatial partition tests confirm deterministic assignments

for fixed synthetic observations, settings and seeds.



\## Offline testing



Automated regression tests use synthetic fixtures.

The test suite prevents live Requests HTTP traffic.



CI must not download full NASA products, execute

unvalidated planetary processing or run model training.



\## Coverage policy



Minimum combined branch-aware coverage: 85%.



Passing coverage does not establish data quality,

model validity, calibration or scientific discovery.



Coverage requirements must not be reduced merely

to accommodate newly added modules.



\## Operational limitation



Local verification does not prove that GitHub Actions

will pass on the Ubuntu runner.



The first successful remote workflow execution is

required before claiming that CI is operational.



Future changes to the approved research profile,

planetary dataset scope or CRS policy require a

separate scientifically justified review.



