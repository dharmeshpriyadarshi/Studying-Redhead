
"""Deterministic spatial partitions for synthetic engineering tests.

Coordinates must share one declared planar, metric reference.
No coordinate transformations are performed here.
"""

from collections import defaultdict
from collections.abc import Mapping
from hashlib import sha256
from pathlib import Path
import json
import math
import os
import tempfile


class SpatialSplitError(ValueError):
    """Invalid spatial inputs, assignments or split constraints."""


SPLITS = ("train", "validation", "test")
REQUIRED_KEYS = {
    "sample_id",
    "source_scene_id",
    "body",
    "crs",
    "units",
    "bounds",
}
MAX_SAMPLES = 500
MAX_BLOCKS_PER_SAMPLE = 256


def _finite(value, name, *, positive=False, allow_zero=False):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
    ):
        raise SpatialSplitError(f"{name} must be finite and numeric.")

    result = float(value)

    if positive and result <= 0:
        raise SpatialSplitError(f"{name} must be positive.")

    if allow_zero and result < 0:
        raise SpatialSplitError(f"{name} cannot be negative.")

    return result


def _read_samples(samples):
    if (
        not isinstance(samples, (list, tuple))
        or not 1 <= len(samples) <= MAX_SAMPLES
    ):
        raise SpatialSplitError(
            "Samples must be a nonempty list of at most 500 records."
        )

    parsed = []
    identifiers = set()

    for sample in samples:
        if not isinstance(sample, Mapping):
            raise SpatialSplitError("Each sample must be a mapping.")

        if set(sample) != REQUIRED_KEYS:
            raise SpatialSplitError(
                "Unexpected or missing spatial sample fields."
            )

        for key in ("sample_id", "source_scene_id", "crs"):
            value = sample[key]
            if (
                not isinstance(value, str)
                or not value.strip()
                or value != value.strip()
            ):
                raise SpatialSplitError(
                    f"{key} must be a nonempty, trimmed string."
                )

        sample_id = sample["sample_id"]

        if sample_id in identifiers:
            raise SpatialSplitError("Duplicate sample_id.")

        identifiers.add(sample_id)

        if sample["body"] not in ("Earth", "Mars"):
            raise SpatialSplitError("Unsupported reference body.")

        if sample["units"] != "m":
            raise SpatialSplitError(
                "Only declared metre-based coordinates are supported."
            )

        bounds = sample["bounds"]

        if (
            not isinstance(bounds, (list, tuple))
            or len(bounds) != 4
        ):
            raise SpatialSplitError(
                "Bounds must contain xmin, ymin, xmax, ymax."
            )

        x0, y0, x1, y1 = (
            _finite(value, "Coordinate")
            for value in bounds
        )

        if x0 >= x1 or y0 >= y1:
            raise SpatialSplitError(
                "Spatial bounds must have positive area."
            )

        parsed.append({
            "sample_id": sample_id,
            "source_scene_id": sample["source_scene_id"],
            "body": sample["body"],
            "crs": sample["crs"],
            "units": "m",
            "bounds": (x0, y0, x1, y1),
        })

    bodies = {sample["body"] for sample in parsed}
    references = {sample["crs"] for sample in parsed}

    if len(bodies) != 1 or len(references) != 1:
        raise SpatialSplitError(
            "All samples must declare one body and one CRS."
        )

    return sorted(parsed, key=lambda item: item["sample_id"])


def _blocks(bounds, block_size_m):
    x0, y0, x1, y1 = bounds

    left = math.floor(x0 / block_size_m)
    right = math.floor(x1 / block_size_m)
    bottom = math.floor(y0 / block_size_m)
    top = math.floor(y1 / block_size_m)

    count = (right - left + 1) * (top - bottom + 1)

    if count > MAX_BLOCKS_PER_SAMPLE:
        raise SpatialSplitError(
            "Footprint spans too many spatial blocks; "
            "review the block size or input extent."
        )

    return tuple(
        f"{x}:{y}"
        for x in range(left, right + 1)
        for y in range(bottom, top + 1)
    )


def _footprint_distance(a, b):
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b

    dx = max(ax0 - bx1, bx0 - ax1, 0.0)
    dy = max(ay0 - by1, by0 - ay1, 0.0)

    return math.hypot(dx, dy)


def _components(samples, block_size_m, buffer_m):
    parent = list(range(len(samples)))

    def find(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(first, second):
        parent[find(first)] = find(second)

    block_members = {}
    scene_members = {}
    sample_blocks = {}

    for index, sample in enumerate(samples):
        sample_id = sample["sample_id"]
        blocks = _blocks(sample["bounds"], block_size_m)
        sample_blocks[sample_id] = blocks

        scene = sample["source_scene_id"]

        if scene in scene_members:
            union(index, scene_members[scene])
        else:
            scene_members[scene] = index

        for block in blocks:
            if block in block_members:
                union(index, block_members[block])
            else:
                block_members[block] = index

    for i, first in enumerate(samples):
        for j in range(i + 1, len(samples)):
            second = samples[j]

            if _footprint_distance(
                first["bounds"], second["bounds"]
            ) <= buffer_m:
                union(i, j)

    grouped = defaultdict(list)

    for index, sample in enumerate(samples):
        grouped[find(index)].append(sample["sample_id"])

    components = [
        tuple(sorted(members))
        for members in grouped.values()
    ]

    return components, sample_blocks


def audit_spatial_partition(
    samples,
    assignments,
    *,
    block_size_m,
    buffer_m=0.0,
):
    """Independently identify cross-partition spatial conflicts."""

    records = _read_samples(samples)
    block_size_m = _finite(
        block_size_m, "block_size_m", positive=True
    )
    buffer_m = _finite(
        buffer_m, "buffer_m", allow_zero=True
    )

    if not isinstance(assignments, (list, tuple)):
        raise SpatialSplitError("Assignments must be a list.")

    by_id = {}
    record_map = {
        record["sample_id"]: record for record in records
    }

    for assignment in assignments:
        if not isinstance(assignment, Mapping):
            raise SpatialSplitError("Invalid assignment.")

        sample_id = assignment.get("sample_id")
        split = assignment.get("split")

        if sample_id not in record_map:
            raise SpatialSplitError("Unknown assigned sample_id.")

        if sample_id in by_id:
            raise SpatialSplitError("Duplicate assignment.")

        if split not in SPLITS:
            raise SpatialSplitError("Invalid partition label.")

        if "source_scene_id" in assignment:
            if (
                assignment["source_scene_id"]
                != record_map[sample_id]["source_scene_id"]
            ):
                raise SpatialSplitError(
                    "Assignment source-scene mismatch."
                )

        if "block_ids" in assignment:
            expected = _blocks(
                record_map[sample_id]["bounds"], block_size_m
            )

            if tuple(assignment["block_ids"]) != expected:
                raise SpatialSplitError(
                    "Assignment spatial-block mismatch."
                )

        by_id[sample_id] = split

    if set(by_id) != set(record_map):
        raise SpatialSplitError(
            "Every sample must have exactly one assignment."
        )

    conflicts = []
    checked_pairs = 0

    for i, first in enumerate(records):
        for second in records[i + 1:]:
            checked_pairs += 1

            if by_id[first["sample_id"]] == by_id[second["sample_id"]]:
                continue

            reasons = []

            if (
                first["source_scene_id"]
                == second["source_scene_id"]
            ):
                reasons.append("shared_source_scene")

            first_blocks = set(
                _blocks(first["bounds"], block_size_m)
            )
            second_blocks = set(
                _blocks(second["bounds"], block_size_m)
            )

            if first_blocks.intersection(second_blocks):
                reasons.append("shared_spatial_block")

            if _footprint_distance(
                first["bounds"], second["bounds"]
            ) <= buffer_m:
                reasons.append("footprint_buffer_conflict")

            if reasons and len(conflicts) < 50:
                conflicts.append({
                    "first": first["sample_id"],
                    "second": second["sample_id"],
                    "reasons": reasons,
                })

    return {
        "passed": not conflicts,
        "checked_pairs": checked_pairs,
        "conflicts": conflicts,
    }


def create_spatial_partition(
    samples,
    *,
    block_size_m,
    buffer_m=0.0,
    seed=2026,
    train_fraction=0.7,
    validation_fraction=0.15,
):
    """Create deterministic, geographically separated partitions."""

    records = _read_samples(samples)

    block_size_m = _finite(
        block_size_m, "block_size_m", positive=True
    )
    buffer_m = _finite(
        buffer_m, "buffer_m", allow_zero=True
    )

    if (
        isinstance(seed, bool)
        or not isinstance(seed, int)
        or seed < 0
    ):
        raise SpatialSplitError(
            "Seed must be a nonnegative integer."
        )

    train_fraction = _finite(train_fraction, "train_fraction")
    validation_fraction = _finite(
        validation_fraction, "validation_fraction"
    )

    test_fraction = 1.0 - train_fraction - validation_fraction

    if min(
        train_fraction, validation_fraction, test_fraction
    ) <= 0:
        raise SpatialSplitError(
            "All three split fractions must be positive."
        )

    groups, sample_blocks = _components(
        records, block_size_m, buffer_m
    )

    if len(groups) < 3:
        raise SpatialSplitError(
            "Fewer than three independent spatial components. "
            "A leakage-safe train/validation/test split "
            "cannot be constructed."
        )

    def ordering(group):
        signature = "|".join(group)
        digest = sha256(
            f"{seed}:{signature}".encode("utf-8")
        ).hexdigest()

        return (-len(group), digest, signature)

    groups.sort(key=ordering)

    fractions = {
        "train": train_fraction,
        "validation": validation_fraction,
        "test": test_fraction,
    }

    counts = dict.fromkeys(SPLITS, 0)
    assigned = {}
    component_ids = {}

    for index, group in enumerate(groups):
        if index < 3:
            chosen = SPLITS[index]
        else:
            chosen = min(
                SPLITS,
                key=lambda role: (
                    counts[role] / fractions[role],
                    SPLITS.index(role),
                ),
            )

        component_id = (
            "component_"
            + sha256("|".join(group).encode("utf-8"))
            .hexdigest()[:16]
        )

        counts[chosen] += len(group)

        for sample_id in group:
            assigned[sample_id] = chosen
            component_ids[sample_id] = component_id

    assignments = [
        {
            "sample_id": record["sample_id"],
            "source_scene_id": record["source_scene_id"],
            "block_ids": list(
                sample_blocks[record["sample_id"]]
            ),
            "component_id": component_ids[record["sample_id"]],
            "split": assigned[record["sample_id"]],
        }
        for record in records
    ]

    leakage_audit = audit_spatial_partition(
        samples,
        assignments,
        block_size_m=block_size_m,
        buffer_m=buffer_m,
    )

    if not leakage_audit["passed"]:
        raise SpatialSplitError(
            "Generated partition failed its leakage audit."
        )

    manifest = {
        "schema_version": 1,
        "purpose": "synthetic_engineering_validation_only",
        "body": records[0]["body"],
        "crs": records[0]["crs"],
        "units": "m",
        "block_size_m": block_size_m,
        "buffer_m": buffer_m,
        "seed": seed,
        "requested_fractions": fractions,
        "actual_counts": counts,
        "independent_components": len(groups),
        "assignments": assignments,
        "leakage_audit": leakage_audit,
        "scientific_processing_approved": False,
    }

    canonical = json.dumps(
        manifest, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    )

    manifest["manifest_sha256"] = sha256(
        canonical.encode("utf-8")
    ).hexdigest()

    return manifest


def save_spatial_manifest(manifest, destination):
    """Atomically save a deterministic JSON manifest."""

    if not isinstance(manifest, Mapping):
        raise SpatialSplitError("Manifest must be a mapping.")

    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    temporary_path = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=destination.parent,
            prefix=".spatial_manifest_",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            json.dump(
                manifest,
                handle,
                indent=2,
                sort_keys=True,
                allow_nan=False,
            )
            handle.write("\n")

        os.replace(temporary_path, destination)

    finally:
        if (
            temporary_path is not None
            and temporary_path.exists()
        ):
            temporary_path.unlink()

    return destination
