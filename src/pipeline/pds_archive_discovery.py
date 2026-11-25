
"""Auditable acquisition of a pinned NASA MOLA PDS4 label.

Offline by default. No raster products are downloaded.
Scientific processing approval is never granted here.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import xml.etree.ElementTree as ET

import requests


class ArchiveDiscoveryError(ValueError):
    """Archive retrieval or product-identity verification failed."""


LABEL_NAME = "megt44n000hb.xml"

LABEL_URL = (
    "https://pds-geosciences.wustl.edu/mgs/"
    "urn-nasa-pds-mgs_mola_topography_derived/"
    "meg128/megt44n000hb.xml"
)

EXPECTED_LID = (
    "urn:nasa:pds:mgs_mola_topography_derived:"
    "data_meg128:megt44n000hb"
)

PINNED_SHA256 = (
    "f6de640ed5603eb03395616214c9a570"
    "7c9d49273f699d2cbeec53e93df6bd08"
)

PDS_NAMESPACE = "http://pds.nasa.gov/pds4/pds/v1"
MAX_LABEL_BYTES = 65536

DEFAULT_DIRECTORY = Path("artifacts/pds_archive")


def inspect_label(raw, *, expected_sha256=None):
    """Verify bounded XML, product identity and optional checksum."""

    if not isinstance(raw, bytes) or not raw:
        raise ArchiveDiscoveryError(
            "PDS4 label must contain nonempty bytes."
        )

    if len(raw) > MAX_LABEL_BYTES:
        raise ArchiveDiscoveryError(
            "PDS4 label exceeds the metadata size limit."
        )

    if re.search(
        rb"<!\s*(?:DOCTYPE|ENTITY)\b", raw, flags=re.IGNORECASE
    ):
        raise ArchiveDiscoveryError(
            "XML DTD or entity declarations are prohibited."
        )

    digest = hashlib.sha256(raw).hexdigest()

    if (
        expected_sha256 is not None
        and digest != expected_sha256
    ):
        raise ArchiveDiscoveryError(
            "PDS4 label SHA-256 does not match the pinned value."
        )

    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ArchiveDiscoveryError(
            "Invalid PDS4 XML document."
        ) from exc

    expected_root = (
        f"{{{PDS_NAMESPACE}}}Product_Observational"
    )

    if root.tag != expected_root:
        raise ArchiveDiscoveryError(
            "Expected a PDS4 Product_Observational label."
        )

    identification = root.find(
        f"{{{PDS_NAMESPACE}}}Identification_Area"
    )

    if identification is None:
        raise ArchiveDiscoveryError(
            "PDS4 Identification_Area is missing."
        )

    identifier = identification.findtext(
        f"{{{PDS_NAMESPACE}}}logical_identifier"
    )

    if identifier is None or identifier.strip() != EXPECTED_LID:
        raise ArchiveDiscoveryError(
            "Unexpected or missing PDS4 logical identifier."
        )

    return {
        "file_name": LABEL_NAME,
        "size_bytes": len(raw),
        "sha256": digest,
        "xml_root": "Product_Observational",
        "logical_identifier": identifier.strip(),
        "identity_verified": True,
    }


def fetch_label(*, session=None):
    """Retrieve only the pinned XML URL with bounded transfer."""

    client = session if session is not None else requests
    response = None

    try:
        response = client.get(
            LABEL_URL,
            timeout=(5, 25),
            stream=True,
            allow_redirects=False,
            headers={"Accept": "application/xml"},
        )

        if response.status_code != 200:
            raise ArchiveDiscoveryError(
                f"NASA archive returned HTTP {response.status_code}."
            )

        content_type = response.headers.get(
            "Content-Type", ""
        ).lower()

        if "xml" not in content_type:
            raise ArchiveDiscoveryError(
                "NASA archive did not return XML metadata."
            )

        declared = response.headers.get("Content-Length")

        if declared is not None:
            try:
                declared_size = int(declared)
            except ValueError as exc:
                raise ArchiveDiscoveryError(
                    "Invalid Content-Length response header."
                ) from exc

            if not 0 <= declared_size <= MAX_LABEL_BYTES:
                raise ArchiveDiscoveryError(
                    "Declared metadata size exceeds the limit."
                )

        data = bytearray()

        for chunk in response.iter_content(chunk_size=8192):
            if not isinstance(chunk, (bytes, bytearray)):
                raise ArchiveDiscoveryError(
                    "Invalid metadata response chunk."
                )

            data.extend(chunk)

            if len(data) > MAX_LABEL_BYTES:
                raise ArchiveDiscoveryError(
                    "Downloaded metadata exceeds the size limit."
                )

        if declared is not None and len(data) != declared_size:
            raise ArchiveDiscoveryError(
                "Downloaded size differs from Content-Length."
            )

        return bytes(data)

    except requests.RequestException as exc:
        raise ArchiveDiscoveryError(
            f"NASA metadata request failed: {type(exc).__name__}"
        ) from exc

    finally:
        if response is not None:
            response.close()


def _atomic_write(path, payload):
    """Write bytes atomically within the output directory."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=".pds_label_",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(payload)

        os.replace(temporary, path)

    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def acquire_reference_label(
    destination=DEFAULT_DIRECTORY,
    *,
    live=False,
    session=None,
    expected_sha256=None,
):
    """Verify the pinned NASA label and save its audit.

    The offline mode reads a previously acquired local label.
    Live mode retrieves exactly one XML file.
    """

    if not isinstance(live, bool):
        raise ArchiveDiscoveryError(
            "Live mode must be explicitly boolean."
        )

    destination = Path(destination)
    label_path = destination / LABEL_NAME

    if live:
        raw = fetch_label(session=session)
    else:
        try:
            raw = label_path.read_bytes()
        except OSError as exc:
            raise ArchiveDiscoveryError(
                "Local MOLA label missing; obtain it using "
                "the explicitly enabled --live mode."
            ) from exc

    pinned = (
        PINNED_SHA256
        if expected_sha256 is None
        else expected_sha256
    )

    details = inspect_label(raw, expected_sha256=pinned)

    audit = {
        "schema_version": 1,
        "source": "NASA PDS Geosciences",
        "source_url": LABEL_URL,
        "acquisition_mode": "live" if live else "offline",
        "product": details,
        "review_status": "identity_and_integrity_verified",
        "scientific_processing_approved": False,
        "outstanding_review": [
            "instrument and processing metadata",
            "data structure and special pixels",
            "measurement units",
            "Mars coordinate conventions",
            "source raster geometry",
            "scientific suitability",
        ],
    }

    if live:
        _atomic_write(label_path, raw)

    audit_path = (
        destination / "verified_mola_label_audit.json"
    )

    serialized = (
        json.dumps(audit, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")

    _atomic_write(audit_path, serialized)

    return audit


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Verify pinned NASA MOLA PDS4 metadata."
    )

    parser.add_argument(
        "--live",
        action="store_true",
        help="Explicitly acquire the small NASA XML label.",
    )

    parser.add_argument(
        "--destination",
        default=str(DEFAULT_DIRECTORY),
    )

    args = parser.parse_args(argv)

    audit = acquire_reference_label(
        args.destination,
        live=args.live,
    )

    print(json.dumps(audit, indent=2, sort_keys=True))
    return audit


if __name__ == "__main__":
    try:
        main()
    except ArchiveDiscoveryError as exc:
        raise SystemExit(
            f"MOLA label acquisition failed: {exc}"
        ) from exc
