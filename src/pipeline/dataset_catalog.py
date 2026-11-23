
"""Scientific provenance registry for planetary data candidates."""

import argparse
import json
import re
from urllib.parse import urlsplit

from src.logger import logger
from src.utils.common import read_yaml


ALLOWED_HOSTS = {
    "pds.nasa.gov",
    "pds.jpl.nasa.gov",
    "pds-geosciences.wustl.edu",
    "pds-imaging.jpl.nasa.gov",
    "ode.rsl.wustl.edu",
}

INSTRUMENT_MODALITY = {
    "CTX": "orbital_imagery",
    "MOLA": "topography_grid",
}

RECORD_FIELDS = {
    "record_id",
    "status",
    "target_body",
    "mission",
    "instrument",
    "modality",
    "archive",
    "landing_page",
    "collection_identifier",
    "identifier_scheme",
    "product_identifier",
    "product_label_url",
    "processing_level",
    "spatial_reference",
    "resolution",
    "measurement_units",
    "observation_time",
    "footprint",
    "calibration_status",
    "usage_review",
    "sha256",
    "notes",
}

PRODUCT_FIELDS = {
    "identifier_scheme",
    "product_identifier",
    "product_label_url",
    "processing_level",
    "spatial_reference",
    "resolution",
    "measurement_units",
    "footprint",
}

SOURCE_CANDIDATE_NULL_FIELDS = PRODUCT_FIELDS | {
    "observation_time",
    "sha256",
}


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def trusted_https(url):
    if not nonempty(url):
        return False

    try:
        parsed = urlsplit(url)

        return (
            parsed.scheme == "https"
            and parsed.hostname in ALLOWED_HOSTS
            and parsed.username is None
            and parsed.password is None
            and parsed.port is None
        )

    except ValueError:
        return False


def validate_record(record):
    if not isinstance(record, dict):
        raise ValueError("Dataset record must be a mapping.")

    missing = RECORD_FIELDS - set(record)
    unknown = set(record) - RECORD_FIELDS

    if missing or unknown:
        raise ValueError(
            f"Invalid record fields: missing={sorted(missing)}, "
            f"unknown={sorted(unknown)}"
        )

    record_id = record["record_id"]

    if not (
        isinstance(record_id, str)
        and re.fullmatch(r"[a-z][a-z0-9_]*", record_id)
    ):
        raise ValueError("Invalid record_id.")

    if record["target_body"] != "Mars":
        raise ValueError("Expected Mars as the target body.")

    for field in ("mission", "instrument", "archive", "notes"):
        if not nonempty(record[field]):
            raise ValueError(f"Missing or invalid {field}.")

    instrument = record["instrument"]

    if instrument not in INSTRUMENT_MODALITY:
        raise ValueError(f"Unsupported instrument: {instrument}")

    if record["modality"] != INSTRUMENT_MODALITY[instrument]:
        raise ValueError("Instrument and modality mismatch.")

    if not trusted_https(record["landing_page"]):
        raise ValueError("Invalid or untrusted source URL.")

    collection_id = record["collection_identifier"]

    if collection_id is not None:
        if not (
            nonempty(collection_id)
            and collection_id.startswith("urn:nasa:pds:")
        ):
            raise ValueError("Invalid PDS collection identifier.")

    sha256 = record["sha256"]

    if sha256 is not None:
        if not (
            isinstance(sha256, str)
            and re.fullmatch(r"[0-9a-fA-F]{64}", sha256)
        ):
            raise ValueError("Invalid SHA-256.")

    status = record["status"]

    if status == "source_candidate":

        for field in SOURCE_CANDIDATE_NULL_FIELDS:
            if record[field] is not None:
                raise ValueError(
                    f"Candidate must not claim {field}."
                )

        if record["calibration_status"] != "not_assessed":
            raise ValueError(
                "Candidate calibration must be unassessed."
            )

        if record["usage_review"] != "pending":
            raise ValueError(
                "Candidate usage review must be pending."
            )

    elif status == "metadata_documented":

        for field in PRODUCT_FIELDS:
            if not nonempty(record[field]):
                raise ValueError(
                    f"Documented product requires {field}."
                )

        if not trusted_https(record["product_label_url"]):
            raise ValueError("Invalid product label URL.")

        scheme = record["identifier_scheme"]

        if scheme not in {"PDS3", "PDS4"}:
            raise ValueError("Unsupported identifier scheme.")

        if scheme == "PDS4":
            if not record["product_identifier"].startswith(
                "urn:nasa:pds:"
            ):
                raise ValueError("Invalid PDS4 product identifier.")

        if record["calibration_status"] not in {
            "reviewed",
            "not_applicable",
        }:
            raise ValueError(
                "Calibration status not reviewed."
            )

        if record["usage_review"] != "reviewed":
            raise ValueError(
                "Data-use review must be completed."
            )

    else:
        raise ValueError(f"Unsupported status: {status}")

    return record


def validate_catalog(payload):
    if not isinstance(payload, dict):
        raise ValueError("Catalog must be a mapping.")

    if set(payload) != {"schema_version", "records"}:
        raise ValueError("Invalid catalog structure.")

    if type(payload["schema_version"]) is not int:
        raise ValueError("Invalid schema version.")

    if payload["schema_version"] != 1:
        raise ValueError("Unsupported catalog schema version.")

    records = payload["records"]

    if not isinstance(records, list) or not records:
        raise ValueError("Catalog requires at least one record.")

    seen = set()

    for record in records:
        validate_record(record)

        record_id = record["record_id"]

        if record_id in seen:
            raise ValueError(
                f"Duplicate record_id: {record_id}"
            )

        seen.add(record_id)

    return records


def load_catalog(path):
    payload = read_yaml(path)
    return validate_catalog(payload)


def summarize_catalog(records):
    return {
        "total_records": len(records),
        "source_candidates": sum(
            record["status"] == "source_candidate"
            for record in records
        ),
        "metadata_documented": sum(
            record["status"] == "metadata_documented"
            for record in records
        ),
        "records": [
            {
                "record_id": record["record_id"],
                "instrument": record["instrument"],
                "status": record["status"],
                "product_identifier": record["product_identifier"],
            }
            for record in records
        ],
    }


def main():
    parser = argparse.ArgumentParser(
        description="Validate the planetary source registry."
    )

    parser.add_argument(
        "--config",
        default="configs/planetary_sources.yaml"
    )

    args = parser.parse_args()

    records = load_catalog(args.config)
    summary = summarize_catalog(records)

    print(json.dumps(summary, indent=2))

    logger.info(
        "Planetary catalog validated: %s records",
        len(records)
    )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logger.exception("Planetary catalog validation failed")
        raise SystemExit(1)
