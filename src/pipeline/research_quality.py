
"""Offline checks for reproducible research configuration.

Does not download data, run planetary reprojection,
or certify the scientific validity of source products.
"""

import argparse
import json
import re
from pathlib import Path

import yaml

from src.pipeline.dataset_catalog import validate_catalog


class ResearchQualityError(ValueError):
    """A research configuration or dependency rule was violated."""


PIN_PATTERN = re.compile(
    r"([A-Za-z0-9][A-Za-z0-9_.-]*)=="
    r"([A-Za-z0-9][A-Za-z0-9._+-]*)"
)


def _load_yaml(path):
    try:
        content = path.read_text(encoding="utf-8-sig")
        value = yaml.safe_load(content)
    except (OSError, yaml.YAMLError) as exc:
        raise ResearchQualityError(
            f"Could not load YAML: {path.name}"
        ) from exc

    if not isinstance(value, dict):
        raise ResearchQualityError(
            f"{path.name} must contain a mapping."
        )

    return value


def _read_pins(path, *, include_base=False):
    try:
        lines = path.read_text(
            encoding="utf-8-sig"
        ).splitlines()
    except OSError as exc:
        raise ResearchQualityError(
            f"Cannot read requirements: {path.name}"
        ) from exc

    pins = {}
    base_included = False

    for raw in lines:
        line = raw.strip()

        if not line or line.startswith("#"):
            continue

        if line.startswith("-r"):
            if (
                not include_base
                or line != "-r requirements.txt"
                or base_included
            ):
                raise ResearchQualityError(
                    f"Unexpected requirement include: {line}"
                )

            base_included = True
            continue

        matched = PIN_PATTERN.fullmatch(line)

        if matched is None:
            raise ResearchQualityError(
                f"Unpinned or unsupported dependency: {line}"
            )

        original_name, version = matched.groups()
        name = re.sub(
            r"[-_.]+", "-", original_name
        ).lower()

        if name in pins:
            raise ResearchQualityError(
                f"Duplicate dependency: {name}"
            )

        pins[name] = version

    if not pins:
        raise ResearchQualityError(
            f"Empty dependency inventory: {path.name}"
        )

    if include_base and not base_included:
        raise ResearchQualityError(
            "Development requirements must include "
            "requirements.txt."
        )

    return pins


def verify_research_contract(project_root="."):
    """Validate committed research policy and dependency consistency."""

    root = Path(project_root).resolve()

    config = _load_yaml(root / "configs/config.yaml")
    catalog = _load_yaml(
        root / "configs/planetary_sources.yaml"
    )

    geospatial = config.get("geospatial")
    processing = config.get("processing")
    pipeline = config.get("pipeline")

    if not all(
        isinstance(section, dict)
        for section in (geospatial, processing, pipeline)
    ):
        raise ResearchQualityError(
            "Required configuration sections are missing."
        )

    if geospatial.get("planet") != "Mars":
        raise ResearchQualityError(
            "The research target must remain Mars."
        )

    if geospatial.get("target_crs") is not None:
        raise ResearchQualityError(
            "An unaudited global Mars target CRS "
            "must not be configured."
        )

    if pipeline.get("profile") != "earth_smoke_test":
        raise ResearchQualityError(
            "Unsupported active processing profile."
        )

    if (
        pipeline.get("source_crs") != "EPSG:32618"
        or pipeline.get("target_crs") != "EPSG:3857"
    ):
        raise ResearchQualityError(
            "Earth smoke-test CRS contract changed."
        )

    if processing.get("preserve_raw_data") is not True:
        raise ResearchQualityError(
            "Raw source preservation must remain enabled."
        )

    if not str(pipeline.get("source_url", "")).startswith(
        "https://"
    ):
        raise ResearchQualityError(
            "The engineering source URL must use HTTPS."
        )

    checksum = pipeline.get("expected_sha256")

    if (
        not isinstance(checksum, str)
        or re.fullmatch(r"[0-9a-fA-F]{64}", checksum) is None
    ):
        raise ResearchQualityError(
            "A pinned source SHA-256 is required."
        )

    try:
        records = validate_catalog(catalog)
    except ValueError as exc:
        raise ResearchQualityError(
            f"Invalid planetary catalog: {exc}"
        ) from exc

    base = _read_pins(root / "requirements.txt")
    development = _read_pins(
        root / "requirements-dev.txt",
        include_base=True,
    )
    locked = _read_pins(
        root / "requirements-dev.lock.txt"
    )

    for required in ("pytest", "pytest-cov"):
        if required not in development:
            raise ResearchQualityError(
                f"Missing test dependency: {required}"
            )

    direct = dict(base)

    for package, version in development.items():
        if package in direct and direct[package] != version:
            raise ResearchQualityError(
                f"Conflicting direct pin: {package}"
            )

        direct[package] = version

    for package, version in direct.items():
        if locked.get(package) != version:
            raise ResearchQualityError(
                f"Development lock mismatch: {package}"
            )

    return {
        "status": "passed",
        "research_target": "Mars",
        "active_pipeline_profile": "earth_smoke_test",
        "catalog_records": len(records),
        "source_candidates": sum(
            record["status"] == "source_candidate"
            for record in records
        ),
        "documented_metadata_records": sum(
            record["status"] == "metadata_documented"
            for record in records
        ),
        "direct_dependencies_checked": len(direct),
        "locked_packages": len(locked),
        "planetary_data_scientifically_certified": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Check offline research-quality contracts."
    )

    parser.add_argument(
        "--root",
        default=".",
        help="Project root directory.",
    )

    args = parser.parse_args(argv)
    result = verify_research_contract(args.root)

    print(json.dumps(result, indent=2, sort_keys=True))
    return result


if __name__ == "__main__":
    try:
        main()
    except ResearchQualityError as exc:
        raise SystemExit(
            f"Research quality check failed: {exc}"
        ) from exc
