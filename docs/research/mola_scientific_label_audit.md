

\# MOLA MEG128 — Scientific Label Audit



Date: 2026-11-25



\## Purpose



Inspect the scientific metadata of the authentic

NASA MOLA product megt44n000hb.



The product identity and original XML label SHA-256

were verified during the preceding acquisition milestone.



\## Metadata observed



\- PDS4 product class: Product\_Observational

\- Product version: 1.1

\- Primary raster: megt44n000hb.img

\- Supplemental files: .lbl and .hdr

\- Raster: 5632 lines by 11520 samples

\- Data storage: SignedMSB2

\- Measurement unit stated in label: meter

\- Projection name: Equirectangular

\- Latitude convention: Planetocentric

\- Longitude direction: Positive East

\- Longitude extent: 0 to 90 degrees

\- Latitude extent: 0 to 44 degrees



A signed 16-bit raster of this shape contains

129761280 bytes of pixel data.



Actual scaling, value offset and special pixel

constants must be taken from the authentic XML

and must never be invented from synthetic tests.



\## Scope of the audit



The audit program reads XML only.



It identifies the primary observational array

independently of supplemental file areas.



It checks array dimensions, storage type, byte

order, file offsets, and selected cartographic

declarations.



The program reports missing values as unknown.



\## Limitations



\- No raster binary was downloaded or inspected.

\- No pixel values were decoded.

\- No planetary reprojection was performed.

\- No vertical datum was independently validated.

\- No spatial alignment with CTX was established.

\- No anomaly detection or ML was performed.

\- Scientific processing remains unapproved.



\## Next decisions



1\. Verify actual scaling and special constants.

2\. Audit planetary map radii and reference frame.

3\. Review source image georegistration.

4\. Establish a bounded candidate study region.

5\. Consider a carefully scoped raster acquisition

&#x20;  only after suitability and data volume are justified.



\## Official references



NASA PDS MOLA MEGDR:

https://pds-geosciences.wustl.edu/missions/mgs/megdr.html



PDS4 Data Dictionary:

https://pds.nasa.gov/datastandards/documents/dd/current/PDS4\_PDS\_DD\_1D00.html
