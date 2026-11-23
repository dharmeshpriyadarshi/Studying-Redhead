
"""Offline tests for research quality contracts."""

import shutil
from pathlib import Path

import pytest
import yaml

from src.pipeline.research_quality import (
    ResearchQualityError,
    main,
    verify_research_contract,
)


FILES = (
    "configs/config.yaml",
    "configs/planetary_sources.yaml",
    "requirements.txt",
    "requirements-dev.txt",
    "requirements-dev.lock.txt",
)


@pytest.fixture
def contract_root(tmp_path):
    repository = Path(__file__).resolve().parents[1]

    for filename in FILES:
        destination = tmp_path / filename
        destination.parent.mkdir(
            parents=True, exist_ok=True
        )

        shutil.copyfile(
            repository / filename, destination
        )

    return tmp_path


def modify_yaml(root, filename, change):
    path = root / filename
    payload = yaml.safe_load(
        path.read_text(encoding="utf-8-sig")
    )

    change(payload)

    path.write_text(
        yaml.safe_dump(payload),
        encoding="utf-8",
    )


def test_valid_research_contract(contract_root):
    result = verify_research_contract(contract_root)

    assert result["status"] == "passed"
    assert result["research_target"] == "Mars"
    assert result["active_pipeline_profile"] == (
        "earth_smoke_test"
    )
    assert result["catalog_records"] >= 1
    assert result["planetary_data_scientifically_certified"] is False


def test_contract_report_is_deterministic(contract_root):
    first = verify_research_contract(contract_root)
    second = verify_research_contract(contract_root)

    assert first == second


@pytest.mark.parametrize("section,field,value", [
    ("geospatial", "planet", "Earth"),
    ("geospatial", "target_crs", "EPSG:3857"),
    ("pipeline", "profile", "mars_processing"),
    ("pipeline", "source_crs", "EPSG:4326"),
    ("pipeline", "target_crs", "EPSG:32618"),
    ("processing", "preserve_raw_data", False),
])
def test_invalid_scientific_configuration_rejected(
    contract_root, section, field, value
):
    def change(config):
        config[section][field] = value

    modify_yaml(
        contract_root, "configs/config.yaml", change
    )

    with pytest.raises(ResearchQualityError):
        verify_research_contract(contract_root)


def test_invalid_catalog_rejected(contract_root):
    def change(catalog):
        catalog["records"][0]["status"] = (
            "scientifically_approved"
        )

    modify_yaml(
        contract_root,
        "configs/planetary_sources.yaml",
        change,
    )

    with pytest.raises(
        ResearchQualityError, match="Invalid planetary catalog"
    ):
        verify_research_contract(contract_root)


def test_unpinned_dependency_rejected(contract_root):
    path = contract_root / "requirements.txt"

    with path.open("a", encoding="utf-8") as handle:
        handle.write("\nexample-package>=1.0\n")

    with pytest.raises(
        ResearchQualityError, match="Unpinned"
    ):
        verify_research_contract(contract_root)


def test_missing_base_requirements_include_rejected(
    contract_root
):
    path = contract_root / "requirements-dev.txt"
    content = path.read_text(encoding="utf-8")

    path.write_text(
        content.replace("-r requirements.txt", ""),
        encoding="utf-8",
    )

    with pytest.raises(
        ResearchQualityError,
        match="must include",
    ):
        verify_research_contract(contract_root)


def test_mismatched_dependency_lock_rejected(contract_root):
    path = contract_root / "requirements-dev.lock.txt"
    content = path.read_text(encoding="utf-8")

    path.write_text(
        content.replace(
            "pytest==8.3.5",
            "pytest==8.3.4",
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        ResearchQualityError,
        match="lock mismatch",
    ):
        verify_research_contract(contract_root)


def test_missing_dependency_lock_entry_rejected(
    contract_root
):
    path = contract_root / "requirements-dev.lock.txt"
    content = path.read_text(encoding="utf-8")

    lines = [
        line for line in content.splitlines()
        if not line.startswith("pytest-cov==")
    ]

    path.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ResearchQualityError, match="lock mismatch"
    ):
        verify_research_contract(contract_root)


def test_duplicate_dependency_lock_rejected(contract_root):
    path = contract_root / "requirements-dev.lock.txt"

    with path.open("a", encoding="utf-8") as handle:
        handle.write("\npytest==8.3.5\n")

    with pytest.raises(
        ResearchQualityError, match="Duplicate"
    ):
        verify_research_contract(contract_root)


def test_invalid_config_document_rejected(contract_root):
    path = contract_root / "configs/config.yaml"
    path.write_text("[]\n", encoding="utf-8")

    with pytest.raises(
        ResearchQualityError, match="mapping"
    ):
        verify_research_contract(contract_root)


def test_cli_reports_contract(contract_root, capsys):
    result = main(["--root", str(contract_root)])
    output = capsys.readouterr().out

    assert result["status"] == "passed"
    assert '"status": "passed"' in output
    assert '"research_target": "Mars"' in output
