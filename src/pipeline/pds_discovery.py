
"""Read-only discovery of NASA PDS4 collection metadata.

Discovery results are not scientific data approval.
No imagery or topography arrays are downloaded.
"""

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlencode, urljoin, urlsplit
from uuid import uuid4

import requests

from src.pipeline.dataset_catalog import load_catalog
from src.utils.common import resolve_path


API_ROOT = "https://pds.nasa.gov/api/search/1/products"
MAX_RESPONSE_BYTES = 2_000_000

COLLECTION_PATTERN = re.compile(
    r"urn:nasa:pds:[A-Za-z0-9_.-]+:"
    r"[A-Za-z0-9_.-]+::[0-9]+(?:\.[0-9]+)*"
)


class DiscoveryError(ValueError):
    """Raised when registry discovery is unsafe or inconclusive."""


def select_collection(records, record_id):
    matches = [
        record for record in records
        if record["record_id"] == record_id
    ]

    if len(matches) != 1:
        raise DiscoveryError("Unknown or ambiguous record_id.")

    record = matches[0]

    if record["status"] != "source_candidate":
        raise DiscoveryError("Expected a source candidate.")

    identifier = record["collection_identifier"]

    if not (
        isinstance(identifier, str)
        and COLLECTION_PATTERN.fullmatch(identifier)
    ):
        raise DiscoveryError(
            "No valid versioned PDS4 collection identifier. "
            "CTX may require a separate ODE discovery workflow."
        )

    return record



def bounded_json_get(session, url, params=None):
    """Fetch bounded JSON, allowing one verified NASA PDS redirect."""

    response = None

    try:
        for hop in range(2):
            response = session.get(
                url,
                params=params,
                headers={"Accept": "application/json"},
                timeout=(5, 25),
                allow_redirects=False,
                stream=True,
            )

            if response.status_code == 307:
                if hop != 0:
                    raise DiscoveryError(
                        "PDS API redirect limit exceeded."
                    )

                location = response.headers.get("Location")

                if not isinstance(location, str) or not location:
                    raise DiscoveryError(
                        "PDS API redirect has no Location."
                    )

                target = urljoin(url, location)

                try:
                    source = urlsplit(url)
                    destination = urlsplit(target)

                    expected_query = (
                        urlencode(params)
                        if isinstance(params, dict)
                        else ""
                    )

                    safe = (
                        source.scheme == "https"
                        and source.hostname == "pds.nasa.gov"
                        and destination.scheme == "https"
                        and destination.hostname == "pds.mcp.nasa.gov"
                        and destination.port is None
                        and destination.username is None
                        and destination.password is None
                        and destination.path == source.path
                        and destination.query in ("", expected_query)
                        and not destination.fragment
                    )
                except ValueError:
                    safe = False

                if not safe:
                    raise DiscoveryError(
                        "Unsafe or unexpected PDS API redirect."
                    )

                response.close()
                response = None

                url = target

                # Avoid sending the same query parameter twice.
                if destination.query:
                    params = None

                continue

            if response.status_code != 200:
                raise DiscoveryError(
                    f"PDS API returned HTTP {response.status_code}."
                )

            content_type = response.headers.get(
                "Content-Type", ""
            ).lower()

            if "json" not in content_type:
                raise DiscoveryError(
                    "PDS API did not return JSON metadata."
                )

            raw = bytearray()

            for chunk in response.iter_content(
                chunk_size=65536
            ):
                if not chunk:
                    continue

                raw.extend(chunk)

                if len(raw) > MAX_RESPONSE_BYTES:
                    raise DiscoveryError(
                        "PDS API metadata response exceeds size limit."
                    )

            try:
                payload = json.loads(raw)
            except (ValueError, UnicodeDecodeError) as exc:
                raise DiscoveryError(
                    "Invalid PDS API JSON response."
                ) from exc

            if not isinstance(payload, dict):
                raise DiscoveryError(
                    "Unexpected PDS API response structure."
                )

            return payload

        raise DiscoveryError(
            "PDS API redirect limit exceeded."
        )

    except requests.RequestException as exc:
        raise DiscoveryError(
            f"PDS API request failed: {type(exc).__name__}"
        ) from exc

    finally:
        if response is not None:
            response.close()



def product_identifier(product):
    """Extract an identifier from a registry record."""

    if not isinstance(product, dict):
        return None

    value = product.get("id") or product.get("lidvid")

    if value is None:
        properties = product.get("properties", {})

        if isinstance(properties, dict):
            value = properties.get("lidvid")

    if isinstance(value, list):
        value = value[0] if len(value) == 1 else None

    if isinstance(value, str) and value.startswith("urn:"):
        return value

    return None


def extract_collection(payload, expected_identifier):
    """Reject registry responses for an unexpected collection."""

    if "data" in payload:
        items = payload["data"]

        if not isinstance(items, list):
            raise DiscoveryError("Invalid collection response data.")
    else:
        items = [payload]

    matching = [
        item for item in items
        if product_identifier(item) == expected_identifier
    ]

    if len(matching) != 1:
        raise DiscoveryError(
            "Collection response identifier mismatch or ambiguity."
        )

    return matching[0]


def extract_members(payload, limit):
    items = payload.get("data")

    if not isinstance(items, list):
        raise DiscoveryError("Invalid members response data.")

    if len(items) > limit:
        raise DiscoveryError(
            "Registry returned more members than requested."
        )

    identifiers = []

    for item in items:
        identifier = product_identifier(item)

        if identifier is None:
            raise DiscoveryError(
                "Member record is missing a usable identifier."
            )

        identifiers.append(identifier)

    if len(set(identifiers)) != len(identifiers):
        raise DiscoveryError("Duplicate member identifier.")

    summary = payload.get("summary", {})

    if not isinstance(summary, dict):
        raise DiscoveryError("Invalid registry summary.")

    total_hits = summary.get("hits")

    if total_hits is not None and (
        type(total_hits) is not int or total_hits < len(items)
    ):
        raise DiscoveryError("Invalid registry hit count.")

    return {
        "returned_count": len(identifiers),
        "reported_total_hits": total_hits,
        "identifiers": identifiers,
        "sample_is_exhaustive": (
            total_hits is not None
            and total_hits > 0
            and total_hits == len(identifiers)
        ),
    }


def discover_collection(record, limit=3, session=None):
    """Inspect one PDS4 collection and its first members page."""

    if type(limit) is not int or not 1 <= limit <= 10:
        raise DiscoveryError(
            "Discovery limit must be an integer from 1 to 10."
        )

    identifier = record["collection_identifier"]

    if not (
        isinstance(identifier, str)
        and COLLECTION_PATTERN.fullmatch(identifier)
    ):
        raise DiscoveryError("Invalid PDS4 collection identifier.")

    encoded = quote(identifier, safe=":")
    url = f"{API_ROOT}/{encoded}"

    owns_session = session is None

    if owns_session:
        session = requests.Session()

    try:
        collection_payload = bounded_json_get(
            session, url
        )

        collection = extract_collection(
            collection_payload, identifier
        )

        members_payload = bounded_json_get(
            session,
            f"{url}/members",
            params={"limit": limit},
        )

        members = extract_members(
            members_payload, limit
        )

    finally:
        if owns_session:
            session.close()

    return {
        "schema_version": 1,
        "audit_status": "discovery_only",
        "queried_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "source_record_id": record["record_id"],
        "instrument": record["instrument"],
        "archive": "NASA PDS",
        "registry_api": API_ROOT,
        "collection_identifier": identifier,
        "collection_response_identifier": product_identifier(
            collection
        ),
        "members": members,
        "scientific_processing_approved": False,
        "outstanding_reviews": [
            "individual product identifiers and label files",
            "instrument and observation metadata",
            "calibration and processing level",
            "measurement units and special pixels",
            "Mars spatial reference and coordinate conventions",
            "spatial extent and target-region suitability",
            "product file integrity and data-use terms",
        ],
        "interpretation": (
            "Registry discovery only. No individual product "
            "has been scientifically validated."
        ),
    }


def save_audit(report):
    directory = resolve_path("artifacts/discovery")
    directory.mkdir(parents=True, exist_ok=True)

    filename = (
        f"{report['source_record_id']}_"
        f"{uuid4().hex[:12]}.json"
    )

    destination = directory / filename
    temporary = directory / (filename + ".part")

    try:
        temporary.write_text(
            json.dumps(report, indent=2),
            encoding="utf-8",
        )

        temporary.replace(destination)

    finally:
        temporary.unlink(missing_ok=True)

    return destination


def main():
    parser = argparse.ArgumentParser(
        description="Read-only NASA PDS4 metadata discovery."
    )

    parser.add_argument(
        "--config",
        default="configs/planetary_sources.yaml"
    )

    parser.add_argument(
        "--record",
        default="mola_meg128_candidate"
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=3
    )

    parser.add_argument(
        "--live",
        action="store_true",
        help="Opt in to NASA PDS metadata requests."
    )

    args = parser.parse_args()

    records = load_catalog(args.config)

    if not args.live:
        print(json.dumps({
            "mode": "offline",
            "network_requests": 0,
            "record_ids": [
                record["record_id"]
                for record in records
            ],
            "message": (
                "Supply --live to query NASA PDS metadata."
            ),
        }, indent=2))
        return

    record = select_collection(records, args.record)

    report = discover_collection(
        record,
        limit=args.limit,
    )

    destination = save_audit(report)

    print(json.dumps({
        "audit_path": str(destination),
        "audit_status": report["audit_status"],
        "collection": report["collection_identifier"],
        "members": report["members"],
        "scientific_processing_approved": False,
    }, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (DiscoveryError, OSError, ValueError) as exc:
        print(f"Discovery failed: {exc}")
        raise SystemExit(1)
