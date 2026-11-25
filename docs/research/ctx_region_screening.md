

\# CTX Observation Discovery — Candidate Region Screening



Date: 2026-11-25



\## Research purpose



Identify authentic Mars Reconnaissance Orbiter CTX

observations suitable for further scientific review.



This is a metadata-discovery phase, not an image

processing or anomaly-detection experiment.



\## Proposed candidate region



Region: Nili Fossae vicinity, Mars



Candidate query bounds:

\- Latitude: 20 to 23 degrees north

\- Longitude: 75 to 79 degrees positive east



These bounds are exploratory and not a finalized

scientific study-region boundary.



\## Source service



NASA PDS Orbital Data Explorer (ODE)



Endpoint:

https://oderest.rsl.wustl.edu/live2/



Mission: MRO

Instrument: CTX

Product type: EDR

Dataset identifier:

MRO-M-CTX-2-EDR-L0-V1.0



Initial request: metadata-only, limited to 3 products.



\## Initial verified API response



HTTP response: 200

Content type: application/json



The JSON result contains:

ODEResults / Products / Product



Observed product identifiers include:



\- T01\_000883\_2006\_XI\_20N281W

\- P02\_001754\_2021\_XI\_22N281W



The returned metadata includes references to:



\- Primary CTX archive files

\- Browse and thumbnail images

\- Derived KML files

\- Geographic footprint shapefiles



Product creation time is not automatically equivalent

to original spacecraft observation time.



A product returned by a geographic search is not

independently verified to have accurate georegistration.



\## Data-handling safeguards



The discovery module:



\- Uses a fixed, bounded candidate query.

\- Requires explicitly enabled live network access.

\- Rejects redirects and unexpected HTTP responses.

\- Enforces a metadata response-size limit.

\- Validates dataset and instrument identifiers.

\- Records only HTTPS resources on trusted hosts.

\- Stores the raw API response and its SHA-256.

\- Supports deterministic offline reinspection.



No orbital raster is downloaded by this module.



\## Scientific limitations



The CTX EDR products are not assumed to be

map-projected research-ready rasters.



ODE-derived footprints may originate from different

geometric estimation methods.



Footprint files have not yet been independently audited.



No CTX–MOLA geometric alignment has been established.



No training, anomaly detection or scientific image

classification has been performed.



\## Next review



1\. Inspect individual CTX product labels.

2\. Review ODE footprint provenance.

3\. Verify geographic coordinate conventions.

4\. Compare candidate observation coverage.

5\. Assess acquisition geometry and image quality.

6\. Select a bounded study area using evidence.

7\. Determine whether projected CTX products or

&#x20;  additional processing are scientifically needed.



\## References



NASA PDS Orbital Data Explorer:

https://ode.rsl.wustl.edu/mars/



ODE Product Footprints:

https://ode.rsl.wustl.edu/mars/pagehelp/Content/Frequently\_Asked\_Questions/Product\_Footprints.htm
