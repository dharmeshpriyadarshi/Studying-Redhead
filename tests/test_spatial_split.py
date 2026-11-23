
"""Tests for spatial independence and deterministic manifests."""

import copy
import json
import math

import pytest

from src.pipeline.spatial_split import (
    SpatialSplitError,
    audit_spatial_partition,
    create_spatial_partition,
    save_spatial_manifest,
)


@pytest.fixture
def samples():
    """Nine synthetic footprints, grouped into three scenes."""

    output = []

    for index in range(9):
        x = float(index * 2000)

        output.append({
            "sample_id": f"sample_{index}",
            "source_scene_id": f"scene_{index // 3}",
            "body": "Mars",
            "crs": "SYNTHETIC_PLANAR_TEST_GRID",
            "units": "m",
            "bounds": [x, 0.0, x + 10.0, 10.0],
        })

    return output


def create(samples, **overrides):
    settings = {
        "block_size_m": 1000.0,
        "buffer_m": 20.0,
        "seed": 2026,
    }
    settings.update(overrides)

    return create_spatial_partition(samples, **settings)


def test_creates_three_nonempty_splits(samples):
    result = create(samples)

    assert result["actual_counts"]["train"] > 0
    assert result["actual_counts"]["validation"] > 0
    assert result["actual_counts"]["test"] > 0
    assert sum(result["actual_counts"].values()) == 9


def test_deterministic_across_reordered_inputs(samples):
    first = create(samples)
    second = create(list(reversed(samples)))

    assert first == second
    assert first["manifest_sha256"] == second["manifest_sha256"]


def test_repeated_seed_is_deterministic(samples):
    assert create(samples, seed=19) == create(samples, seed=19)


def test_same_source_scene_never_crosses_splits(samples):
    result = create(samples)
    scenes = {}

    for item in result["assignments"]:
        scene = item["source_scene_id"]

        if scene in scenes:
            assert scenes[scene] == item["split"]

        scenes[scene] = item["split"]


def test_manifest_declares_no_scientific_approval(samples):
    result = create(samples)

    assert result["body"] == "Mars"
    assert result["purpose"] == (
        "synthetic_engineering_validation_only"
    )
    assert result["scientific_processing_approved"] is False
    assert result["leakage_audit"]["passed"] is True


def test_independent_auditor_approves_valid_split(samples):
    result = create(samples)

    audit = audit_spatial_partition(
        samples,
        result["assignments"],
        block_size_m=1000.0,
        buffer_m=20.0,
    )

    assert audit["passed"] is True
    assert audit["conflicts"] == []
    assert audit["checked_pairs"] == 36


def test_auditor_detects_scene_leakage(samples):
    result = create(samples)
    assignments = copy.deepcopy(result["assignments"])

    original = assignments[0]["split"]
    assignments[0]["split"] = next(
        split
        for split in ("train", "validation", "test")
        if split != original
    )

    audit = audit_spatial_partition(
        samples,
        assignments,
        block_size_m=1000.0,
        buffer_m=20.0,
    )

    assert audit["passed"] is False
    assert any(
        "shared_source_scene" in conflict["reasons"]
        for conflict in audit["conflicts"]
    )


def test_auditor_detects_overlapping_footprints(samples):
    subset = copy.deepcopy(samples[:3])

    for index, sample in enumerate(subset):
        sample["source_scene_id"] = f"unique_{index}"

    subset[0]["bounds"] = [0, 0, 10, 10]
    subset[1]["bounds"] = [5, 5, 15, 15]
    subset[2]["bounds"] = [3000, 0, 3010, 10]

    assignments = [
        {"sample_id": subset[0]["sample_id"], "split": "train"},
        {"sample_id": subset[1]["sample_id"], "split": "test"},
        {
            "sample_id": subset[2]["sample_id"],
            "split": "validation",
        },
    ]

    audit = audit_spatial_partition(
        subset, assignments, block_size_m=1000
    )

    assert audit["passed"] is False
    assert any(
        "footprint_buffer_conflict" in conflict["reasons"]
        for conflict in audit["conflicts"]
    )


def test_auditor_detects_same_block_leakage(samples):
    subset = copy.deepcopy(samples[:2])

    subset[0]["source_scene_id"] = "scene_a"
    subset[1]["source_scene_id"] = "scene_b"
    subset[0]["bounds"] = [1, 1, 3, 3]
    subset[1]["bounds"] = [70, 70, 72, 72]

    assignments = [
        {"sample_id": subset[0]["sample_id"], "split": "train"},
        {"sample_id": subset[1]["sample_id"], "split": "test"},
    ]

    audit = audit_spatial_partition(
        subset, assignments, block_size_m=100
    )

    assert audit["passed"] is False
    assert "shared_spatial_block" in audit["conflicts"][0]["reasons"]


def test_auditor_detects_buffer_leakage(samples):
    subset = copy.deepcopy(samples[:2])

    subset[0]["source_scene_id"] = "scene_a"
    subset[1]["source_scene_id"] = "scene_b"
    subset[0]["bounds"] = [0, 0, 10, 10]
    subset[1]["bounds"] = [20, 0, 30, 10]

    assignments = [
        {"sample_id": subset[0]["sample_id"], "split": "train"},
        {"sample_id": subset[1]["sample_id"], "split": "test"},
    ]

    audit = audit_spatial_partition(
        subset,
        assignments,
        block_size_m=5,
        buffer_m=10,
    )

    assert audit["passed"] is False
    assert "footprint_buffer_conflict" in (
        audit["conflicts"][0]["reasons"]
    )


def test_fully_connected_observations_fail_closed(samples):
    subset = copy.deepcopy(samples[:3])

    for sample in subset:
        sample["bounds"] = [0, 0, 10, 10]

    with pytest.raises(
        SpatialSplitError, match="Fewer than three"
    ):
        create(subset)


@pytest.mark.parametrize("number", [1, 2])
def test_insufficient_independent_components_rejected(
    samples, number
):
    with pytest.raises(
        SpatialSplitError, match="Fewer than three"
    ):
        create(samples[:number])


def test_duplicate_sample_id_rejected(samples):
    samples[1]["sample_id"] = samples[0]["sample_id"]

    with pytest.raises(SpatialSplitError, match="Duplicate"):
        create(samples)


def test_mixed_reference_bodies_rejected(samples):
    samples[0]["body"] = "Earth"

    with pytest.raises(SpatialSplitError, match="one body"):
        create(samples)


def test_mixed_crs_rejected(samples):
    samples[0]["crs"] = "ANOTHER_GRID"

    with pytest.raises(SpatialSplitError, match="one body and one CRS"):
        create(samples)


def test_nonmetric_coordinates_rejected(samples):
    samples[0]["units"] = "degrees"

    with pytest.raises(SpatialSplitError, match="metre"):
        create(samples)


@pytest.mark.parametrize("invalid", [
    float("nan"),
    float("inf"),
    True,
])
def test_invalid_coordinate_rejected(samples, invalid):
    samples[0]["bounds"][0] = invalid

    with pytest.raises(SpatialSplitError, match="finite"):
        create(samples)


def test_zero_area_footprint_rejected(samples):
    samples[0]["bounds"] = [0, 0, 0, 10]

    with pytest.raises(SpatialSplitError, match="positive area"):
        create(samples)


@pytest.mark.parametrize("value", [0, -1, float("nan")])
def test_invalid_block_size_rejected(samples, value):
    with pytest.raises(SpatialSplitError):
        create(samples, block_size_m=value)


@pytest.mark.parametrize("value", [-1, float("inf")])
def test_invalid_buffer_rejected(samples, value):
    with pytest.raises(SpatialSplitError):
        create(samples, buffer_m=value)


@pytest.mark.parametrize("value", [-1, True, "invalid"])
def test_invalid_seed_rejected(samples, value):
    with pytest.raises(SpatialSplitError, match="Seed"):
        create(samples, seed=value)


@pytest.mark.parametrize("training,validation", [
    (0, 0.15),
    (0.7, 0),
    (0.9, 0.2),
])
def test_invalid_split_fractions_rejected(
    samples, training, validation
):
    with pytest.raises(SpatialSplitError, match="fractions"):
        create(
            samples,
            train_fraction=training,
            validation_fraction=validation,
        )


def test_missing_assignment_rejected(samples):
    result = create(samples)

    with pytest.raises(
        SpatialSplitError, match="Every sample"
    ):
        audit_spatial_partition(
            samples,
            result["assignments"][:-1],
            block_size_m=1000,
        )


def test_duplicate_assignment_rejected(samples):
    result = create(samples)
    assignments = copy.deepcopy(result["assignments"])
    assignments.append(copy.deepcopy(assignments[0]))

    with pytest.raises(
        SpatialSplitError, match="Duplicate assignment"
    ):
        audit_spatial_partition(
            samples, assignments, block_size_m=1000
        )


def test_assignment_block_tampering_rejected(samples):
    result = create(samples)
    assignments = copy.deepcopy(result["assignments"])
    assignments[0]["block_ids"] = ["999:999"]

    with pytest.raises(
        SpatialSplitError, match="spatial-block mismatch"
    ):
        audit_spatial_partition(
            samples, assignments, block_size_m=1000
        )


def test_assignment_scene_tampering_rejected(samples):
    result = create(samples)
    assignments = copy.deepcopy(result["assignments"])
    assignments[0]["source_scene_id"] = "forged_scene"

    with pytest.raises(
        SpatialSplitError, match="source-scene mismatch"
    ):
        audit_spatial_partition(
            samples, assignments, block_size_m=1000
        )


def test_manifest_saved_without_timestamp(samples, tmp_path):
    manifest = create(samples)
    destination = tmp_path / "manifest.json"

    saved = save_spatial_manifest(manifest, destination)

    assert saved == destination

    first_bytes = destination.read_bytes()

    save_spatial_manifest(
        create(list(reversed(samples))), destination
    )

    assert destination.read_bytes() == first_bytes
    assert json.loads(first_bytes) == manifest


def test_oversized_footprint_rejected(samples):
    samples[0]["bounds"] = [0, 0, 10000, 10000]

    with pytest.raises(
        SpatialSplitError, match="too many spatial blocks"
    ):
        create(samples, block_size_m=10)
