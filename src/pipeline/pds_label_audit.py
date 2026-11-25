
"""Offline scientific metadata audit for the pinned MOLA PDS4 label.

Reads metadata only. Does not load raster pixels, transform
coordinates, or approve a product for scientific processing.
"""

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
import xml.etree.ElementTree as ET

from src.pipeline import pds_archive_discovery as archive


class PDSLabelAuditError(ValueError):
    """The PDS4 label cannot be interpreted reliably."""


NS = f"{{{archive.PDS_NAMESPACE}}}"
DEFAULT_LABEL = archive.DEFAULT_DIRECTORY / archive.LABEL_NAME
DEFAULT_REPORT = (
    archive.DEFAULT_DIRECTORY / "mola_scientific_label_audit.json"
)

SUPPORTED_TYPES = {
    "SignedMSB2": {
        "bytes_per_sample": 2,
        "signed": True,
        "byte_order": "big",
    }
}


def _name(element):
    return element.tag.rsplit("}", 1)[-1]


def _child(parent, name, *, required=True):
    element = parent.find(f"{NS}{name}") if parent is not None else None

    if element is None and required:
        raise PDSLabelAuditError(
            f"Required PDS4 element missing: {name}"
        )

    return element


def _text(parent, name, *, required=True):
    element = _child(parent, name, required=required)

    if element is None:
        return None

    value = (element.text or "").strip()

    if not value and required:
        raise PDSLabelAuditError(
            f"Required PDS4 value missing: {name}"
        )

    return value or None


def _integer(value, name, *, minimum=0):
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise PDSLabelAuditError(
            f"Invalid integer: {name}"
        ) from exc

    if parsed < minimum:
        raise PDSLabelAuditError(
            f"Invalid range for {name}"
        )

    return parsed


def _number(value, name):
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise PDSLabelAuditError(
            f"Invalid numeric value: {name}"
        ) from exc

    if not math.isfinite(parsed):
        raise PDSLabelAuditError(
            f"Nonfinite numeric value: {name}"
        )

    return parsed


def _unique_field(root, name):
    values = {
        (element.text or "").strip()
        for element in root.iter()
        if _name(element) == name
        and (element.text or "").strip()
    }

    if len(values) > 1:
        raise PDSLabelAuditError(
            f"Conflicting PDS4 values: {name}"
        )

    return next(iter(values), None)


def _cartography(root):
    names = (
        "map_projection_name",
        "latitude_type",
        "longitude_direction",
        "west_bounding_coordinate",
        "east_bounding_coordinate",
        "south_bounding_coordinate",
        "north_bounding_coordinate",
    )

    values = {
        name: _unique_field(root, name)
        for name in names
    }

    for name in names[3:]:
        if values[name] is not None:
            values[name] = _number(values[name], name)

    west = values["west_bounding_coordinate"]
    east = values["east_bounding_coordinate"]
    south = values["south_bounding_coordinate"]
    north = values["north_bounding_coordinate"]

    bounds = (west, east, south, north)

    if all(value is not None for value in bounds):
        if not (
            0 <= west < east <= 360
            and -90 <= south < north <= 90
        ):
            raise PDSLabelAuditError(
                "Invalid geographical bounds."
            )

    values["metadata_complete"] = all(
        value is not None
        for value in values.values()
    )

    values["coordinates_transformed"] = False
    return values


def analyze_pds_label(raw, *, expected_sha256=None):
    """Interpret structural metadata from a verified MOLA label."""

    digest = (
        archive.PINNED_SHA256
        if expected_sha256 is None
        else expected_sha256
    )

    try:
        identity = archive.inspect_label(
            raw,
            expected_sha256=digest,
        )
    except archive.ArchiveDiscoveryError as exc:
        raise PDSLabelAuditError(
            f"Product identity/integrity failed: {exc}"
        ) from exc

    root = ET.fromstring(raw)
    identification = _child(root, "Identification_Area")

    area = _child(root, "File_Area_Observational")

    observational_areas = [
        element
        for element in root
        if element.tag == f"{NS}File_Area_Observational"
    ]

    if len(observational_areas) != 1:
        raise PDSLabelAuditError(
            "Expected exactly one primary observational file area."
        )

    file_element = _child(area, "File")
    file_name = _text(file_element, "file_name")

    expected_image_name = (
        archive.LABEL_NAME.removesuffix(".xml") + ".img"
    )

    if file_name != expected_image_name:
        raise PDSLabelAuditError(
            "Unexpected primary raster filename."
        )

    arrays = [
        element
        for element in area
        if _name(element).startswith("Array_2D")
    ]

    if len(arrays) != 1:
        raise PDSLabelAuditError(
            "Expected exactly one primary 2D raster array."
        )

    array = arrays[0]

    identifier = _text(array, "local_identifier")
    offset_bytes = _integer(
        _text(array, "offset"), "raster offset"
    )
    axes_count = _integer(
        _text(array, "axes"), "axes", minimum=1
    )
    index_order = _text(array, "axis_index_order")

    if axes_count != 2:
        raise PDSLabelAuditError(
            "Expected exactly two raster axes."
        )

    if index_order != "Last Index Fastest":
        raise PDSLabelAuditError(
            "Unsupported raster axis index order."
        )

    element_array = _child(array, "Element_Array")
    data_type = _text(element_array, "data_type")

    if data_type not in SUPPORTED_TYPES:
        raise PDSLabelAuditError(
            "Unsupported raster storage data type."
        )

    storage = SUPPORTED_TYPES[data_type]

    axes = {}

    axis_elements = [
        element
        for element in array
        if element.tag == f"{NS}Axis_Array"
    ]

    if len(axis_elements) != 2:
        raise PDSLabelAuditError(
            "Exactly two Axis_Array records are required."
        )

    sequence_numbers = set()

    for axis in axis_elements:
        name = _text(axis, "axis_name")
        elements = _integer(
            _text(axis, "elements"),
            "axis elements",
            minimum=1,
        )
        sequence = _integer(
            _text(axis, "sequence_number"),
            "axis sequence",
            minimum=1,
        )

        if name in axes or sequence in sequence_numbers:
            raise PDSLabelAuditError(
                "Duplicate raster axis or sequence."
            )

        axes[name] = elements
        sequence_numbers.add(sequence)

    if set(axes) != {"Line", "Sample"}:
        raise PDSLabelAuditError(
            "Expected Line and Sample raster axes."
        )

    if sequence_numbers != {1, 2}:
        raise PDSLabelAuditError(
            "Unexpected raster axis sequence numbers."
        )

    special = _child(
        array, "Special_Constants", required=False
    )

    special_constants = {}

    if special is not None:
        for element in special:
            value = (element.text or "").strip()
            if value:
                special_constants[_name(element)] = value

    scale = _text(
        element_array, "scaling_factor", required=False
    )
    value_offset = _text(
        element_array, "value_offset", required=False
    )

    if scale is not None:
        _number(scale, "scaling_factor")

    if value_offset is not None:
        _number(value_offset, "value_offset")

    lines = axes["Line"]
    samples = axes["Sample"]

    payload_bytes = (
        lines * samples * storage["bytes_per_sample"]
    )

    minimum_file_size = offset_bytes + payload_bytes

    declared_file_size = _text(
        file_element, "file_size", required=False
    )

    if declared_file_size is not None:
        declared_file_size = _integer(
            declared_file_size,
            "file_size",
        )

        if declared_file_size < minimum_file_size:
            raise PDSLabelAuditError(
                "Declared raster file is smaller "
                "than the labelled array."
            )

    supplemental_files = []

    for supplemental_area in root:
        if _name(supplemental_area) != (
            "File_Area_Observational_Supplemental"
        ):
            continue

        supplemental_file = _child(
            supplemental_area, "File", required=False
        )

        if supplemental_file is not None:
            name = _text(
                supplemental_file,
                "file_name",
                required=False,
            )

            if name is not None:
                supplemental_files.append(name)

    cartography = _cartography(root)

    return {
        "schema_version": 1,
        "source_label_sha256": hashlib.sha256(raw).hexdigest(),
        "identity": {
            "logical_identifier": identity["logical_identifier"],
            "version_id": _text(
                identification, "version_id"
            ),
            "identity_verified": True,
        },
        "raster": {
            "file_name": file_name,
            "local_identifier": identifier,
            "array_class": _name(array),
            "lines": lines,
            "samples": samples,
            "axis_index_order": index_order,
            "offset_bytes": offset_bytes,
            "data_type": data_type,
            "byte_order": storage["byte_order"],
            "signed": storage["signed"],
            "bytes_per_sample": storage["bytes_per_sample"],
            "unit": _text(
                element_array, "unit", required=False
            ),
            "scaling_factor_as_labelled": scale,
            "value_offset_as_labelled": value_offset,
            "special_constants_as_labelled": special_constants,
            "expected_array_bytes": payload_bytes,
            "minimum_file_bytes": minimum_file_size,
            "declared_file_size": declared_file_size,
            "raster_file_inspected": False,
        },
        "supplemental_files": sorted(supplemental_files),
        "cartography": cartography,
        "review": {
            "metadata_structure_checked": True,
            "raster_content_verified": False,
            "planetary_reprojection_approved": False,
            "scientific_processing_approved": False,
            "remaining": [
                "Review map-projection radii and reference frame",
                "Review raster scaling and special constants",
                "Validate companion raster integrity",
                "Validate actual spatial registration",
                "Assess suitability for CTX comparison",
            ],
        },
    }


def audit_local_label(
    label_path=DEFAULT_LABEL,
    report_path=DEFAULT_REPORT,
):
    """Audit a local pinned XML label and save an atomic report."""

    label_path = Path(label_path)
    report_path = Path(report_path)

    try:
        if label_path.stat().st_size > archive.MAX_LABEL_BYTES:
            raise PDSLabelAuditError(
                "Local PDS4 label exceeds the size limit."
            )

        raw = label_path.read_bytes()
    except OSError as exc:
        raise PDSLabelAuditError(
            "Could not read local PDS4 label."
        ) from exc

    result = analyze_pds_label(raw)

    report_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=report_path.parent,
            prefix=".pds_audit_",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(result, handle, indent=2, sort_keys=True)
            handle.write("\n")

        os.replace(temporary, report_path)

    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()

    return result


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Audit the locally verified MOLA PDS4 label."
    )
    parser.add_argument("--label", default=str(DEFAULT_LABEL))
    parser.add_argument("--report", default=str(DEFAULT_REPORT))

    args = parser.parse_args(argv)
    result = audit_local_label(args.label, args.report)

    print(json.dumps(result, indent=2, sort_keys=True))
    return result


if __name__ == "__main__":
    try:
        main()
    except PDSLabelAuditError as exc:
        raise SystemExit(
            f"PDS4 scientific label audit failed: {exc}"
        ) from exc
