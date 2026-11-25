
"""Bounded NASA ODE CTX metadata discovery.

Offline by default. No imagery or footprint files are downloaded.
Returned search results are candidates, not validated observations.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import urlsplit

import requests


class CTXDiscoveryError(ValueError):
    """Invalid ODE response, metadata or acquisition request."""


ODE_URL = "https://oderest.rsl.wustl.edu/live2/"

QUERY = {
    "query": "product",
    "results": "fp",
    "output": "JSON",
    "limit": 3,
    "target": "mars",
    "ihid": "MRO",
    "iid": "CTX",
    "pt": "EDR",
    "minlat": 20,
    "maxlat": 23,
    "westlon": 75,
    "eastlon": 79,
}

EXPECTED_DATASET = "MRO-M-CTX-2-EDR-L0-V1.0"

TRUSTED_HOSTS = {
    "planetarydata.jpl.nasa.gov",
    "ode.rsl.wustl.edu",
}

MAX_RESPONSE_BYTES = 1_000_000
MAX_PRODUCTS = 3

DEFAULT_DIRECTORY = Path("artifacts/ctx_ode")
RAW_FILE = "ctx_ode_response.json"
AUDIT_FILE = "ctx_discovery_audit.json"


def _text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise CTXDiscoveryError(
            f"Missing or invalid ODE field: {field}"
        )
    return value.strip()


def _trusted_link(value):
    value = _text(value, "URL")

    try:
        parsed = urlsplit(value)
        valid = (
            parsed.scheme == "https"
            and parsed.hostname in TRUSTED_HOSTS
            and parsed.port is None
            and parsed.username is None
            and parsed.password is None
            and bool(parsed.path)
            and not parsed.fragment
        )
    except ValueError:
        valid = False

    if not valid:
        raise CTXDiscoveryError(
            "Unexpected or unsafe ODE resource URL."
        )

    return value


def _product_files(product):
    container = product.get("Product_files")

    if not isinstance(container, dict):
        raise CTXDiscoveryError(
            "ODE product has no structured file inventory."
        )

    entries = container.get("Product_file", [])

    if isinstance(entries, dict):
        entries = [entries]

    if not isinstance(entries, list):
        raise CTXDiscoveryError(
            "Invalid ODE product-file inventory."
        )

    files = []

    for entry in entries:
        if not isinstance(entry, dict):
            raise CTXDiscoveryError(
                "Invalid ODE product-file record."
            )

        kind = _text(entry.get("Type"), "file type")

        if kind not in {"Product", "Browse", "Derived"}:
            raise CTXDiscoveryError(
                "Unsupported ODE resource type."
            )

        size = entry.get("KBytes")

        if size is not None:
            if not isinstance(size, str) or not re.fullmatch(
                r"[0-9]+(?:\.[0-9]+)?", size
            ):
                raise CTXDiscoveryError(
                    "Invalid ODE file-size metadata."
                )

        files.append({
            "type": kind,
            "file_name": _text(
                entry.get("FileName"), "file name"
            ),
            "url": _trusted_link(entry.get("URL")),
            "reported_kbytes": size,
        })

    if not any(item["type"] == "Product" for item in files):
        raise CTXDiscoveryError(
            "ODE product has no primary archive resource."
        )

    return sorted(
        files,
        key=lambda item: (
            item["type"],
            item["file_name"],
            item["url"],
        ),
    )


def parse_ode_response(payload):
    """Validate and normalize the observed ODE response structure."""

    if not isinstance(payload, dict):
        raise CTXDiscoveryError(
            "ODE response root must be a mapping."
        )

    results = payload.get("ODEResults")

    if not isinstance(results, dict):
        raise CTXDiscoveryError(
            "Missing ODEResults response object."
        )

    products_container = results.get("Products")

    if not isinstance(products_container, dict):
        raise CTXDiscoveryError(
            "Missing ODE Products structure."
        )

    entries = products_container.get("Product", [])

    if isinstance(entries, dict):
        entries = [entries]

    if (
        not isinstance(entries, list)
        or len(entries) > MAX_PRODUCTS
    ):
        raise CTXDiscoveryError(
            "Unexpected ODE product-result count."
        )

    normalized = []
    identifiers = set()

    for entry in entries:
        if not isinstance(entry, dict):
            raise CTXDiscoveryError(
                "Invalid ODE product entry."
            )

        if (
            entry.get("ihid") != "MRO"
            or entry.get("iid") != "CTX"
            or entry.get("pt") != "EDR"
            or entry.get("Target_name") != "MARS"
            or entry.get("Data_Set_Id") != EXPECTED_DATASET
        ):
            raise CTXDiscoveryError(
                "ODE product does not match requested instrument."
            )

        identifier = _text(
            entry.get("pdsid"), "PDS product identifier"
        )

        if not re.fullmatch(r"[A-Z0-9_]+", identifier):
            raise CTXDiscoveryError(
                "Invalid CTX product identifier."
            )

        if identifier in identifiers:
            raise CTXDiscoveryError(
                "Duplicate CTX product identifier."
            )

        identifiers.add(identifier)

        normalized.append({
            "product_id": identifier,
            "dataset_id": EXPECTED_DATASET,
            "volume_id": _text(
                entry.get("PDSVolume_Id"), "volume"
            ),
            "label_file_name_as_reported": _text(
                entry.get("LabelFileName"), "label filename"
            ),
            "product_creation_time_as_reported": entry.get(
                "Product_creation_time"
            ),
            "files": _product_files(entry),
            "footprint_geometry_verified": False,
            "map_projection_verified": False,
            "observation_time_verified": False,
            "scientific_processing_approved": False,
        })

    return sorted(
        normalized,
        key=lambda item: item["product_id"],
    )


def analyze_response_bytes(raw):
    """Parse bounded JSON without any external network request."""

    if (
        not isinstance(raw, bytes)
        or not raw
        or len(raw) > MAX_RESPONSE_BYTES
    ):
        raise CTXDiscoveryError(
            "ODE JSON is empty or exceeds the metadata limit."
        )

    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise CTXDiscoveryError(
            "ODE response contains invalid JSON."
        ) from exc

    products = parse_ode_response(payload)

    return {
        "schema_version": 1,
        "source": "NASA PDS Orbital Data Explorer",
        "query_endpoint": ODE_URL,
        "query_parameters": dict(QUERY),
        "raw_response_sha256": hashlib.sha256(raw).hexdigest(),
        "returned_products": len(products),
        "products": products,
        "candidate_region_only": True,
        "geographic_footprints_verified": False,
        "scientific_processing_approved": False,
        "outstanding_review": [
            "Verify CTX product labels and acquisition geometry",
            "Inspect footprint provenance and coordinates",
            "Establish a scientifically defensible study region",
            "Assess CTX image processing and calibration",
            "Review compatibility with MOLA topography",
        ],
    }


def fetch_ode_metadata(*, session=None):
    """Retrieve one small, bounded ODE search response."""

    client = requests if session is None else session
    response = None

    try:
        response = client.get(
            ODE_URL,
            params=dict(QUERY),
            timeout=(8, 30),
            stream=True,
            allow_redirects=False,
            headers={"Accept": "application/json"},
        )

        if response.status_code != 200:
            raise CTXDiscoveryError(
                f"NASA ODE returned HTTP {response.status_code}."
            )

        if "application/json" not in response.headers.get(
            "Content-Type", ""
        ).lower():
            raise CTXDiscoveryError(
                "NASA ODE did not return JSON metadata."
            )

        declared = response.headers.get("Content-Length")

        if declared is not None:
            try:
                length = int(declared)
            except ValueError as exc:
                raise CTXDiscoveryError(
                    "Invalid ODE Content-Length."
                ) from exc

            if length < 0 or length > MAX_RESPONSE_BYTES:
                raise CTXDiscoveryError(
                    "Declared ODE response exceeds size limit."
                )

        data = bytearray()

        for chunk in response.iter_content(chunk_size=8192):
            if not isinstance(chunk, (bytes, bytearray)):
                raise CTXDiscoveryError(
                    "Invalid ODE response chunk."
                )

            data.extend(chunk)

            if len(data) > MAX_RESPONSE_BYTES:
                raise CTXDiscoveryError(
                    "ODE response exceeds metadata size limit."
                )

        if declared is not None and len(data) != length:
            raise CTXDiscoveryError(
                "ODE Content-Length mismatch."
            )

        return bytes(data)

    except requests.RequestException as exc:
        raise CTXDiscoveryError(
            f"ODE request failed: {type(exc).__name__}"
        ) from exc

    finally:
        if response is not None:
            response.close()


def _atomic_write(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=".ctx_ode_",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(raw)

        os.replace(temporary, path)

    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def discover_ctx(
    destination=DEFAULT_DIRECTORY,
    *,
    live=False,
    session=None,
):
    """Create a metadata-only audit; local mode is the default."""

    destination = Path(destination)
    raw_path = destination / RAW_FILE

    if live:
        raw = fetch_ode_metadata(session=session)
    else:
        try:
            raw = raw_path.read_bytes()
        except OSError as exc:
            raise CTXDiscoveryError(
                "Saved ODE response missing; use --live "
                "for an explicitly authorized metadata query."
            ) from exc

    audit = analyze_response_bytes(raw)
    audit["acquisition_mode"] = "live" if live else "offline"

    if live:
        _atomic_write(raw_path, raw)

    serialized = (
        json.dumps(audit, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")

    _atomic_write(destination / AUDIT_FILE, serialized)

    return audit


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Discover CTX metadata from NASA ODE."
    )
    parser.add_argument("--live", action="store_true")
    parser.add_argument(
        "--destination",
        default=str(DEFAULT_DIRECTORY),
    )

    args = parser.parse_args(argv)
    audit = discover_ctx(
        args.destination,
        live=args.live,
    )
    print(json.dumps(audit, indent=2, sort_keys=True))
    return audit


if __name__ == "__main__":
    try:
        main()
    except CTXDiscoveryError as exc:
        raise SystemExit(
            f"CTX discovery failed: {exc}"
        ) from exc
