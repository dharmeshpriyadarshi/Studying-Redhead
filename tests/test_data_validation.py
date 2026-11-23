import csv
import json

import numpy as np
import pytest
import rasterio

from src.exception import CustomException
from src.pipeline.data_validation import DataValidation


def test_report_statistics(raster_path, source_array, tiles_dir):
    folder = DataValidation(16, 0.5, 16).validate_dataset(raster_path, tiles_dir)
    report = json.loads((folder / "quality_report.json").read_text(encoding="utf-8"))
    assert report["status"] == "passed"
    assert report["total_tiles"] == 6
    assert report["source_pixels"] == 35 * 19
    assert report["padded_pixels"] == 6 * 16**2
    assert report["fully_valid_pixels"] == int(np.all(source_array != 0, axis=0).sum())
    assert report["eligible_tiles"] == 2
    assert report["empty_tiles"] == 0
    for index, band in enumerate(report["bands"]):
        values = (source_array[index][source_array[index] != 0].astype(np.float32) / 255).astype(np.float64)
        assert band["valid_samples"] == values.size
        assert band["mean"] == pytest.approx(values.mean(), abs=1e-10)
        assert band["std"] == pytest.approx(values.std(), abs=1e-10)
        assert band["min"] == pytest.approx(values.min())
        assert band["max"] == pytest.approx(values.max())
        np.testing.assert_array_equal(band["histogram_counts"], np.histogram(values, bins=16, range=(0, 1))[0])
    assert (folder / "tile_quality.csv").is_file()
    for filename in ("intensity_histogram.png", "tile_coverage.png"):
        assert (folder / filename).read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


@pytest.mark.parametrize("damage", ["pixel", "manifest", "missing_file", "duplicate_record"])
def test_rejects_corruption(isolated_root, raster_path, tiles_dir, damage):
    manifest = tiles_dir / "manifest.csv"
    target = tiles_dir / "tile_r000000_c000000.tif"
    if damage == "pixel":
        with rasterio.open(target, "r+") as ds:
            data = ds.read(1)
            assert data[3, 3] > 0
            data[3, 3] = 0
            ds.write(data, 1)
    elif damage == "missing_file":
        target.unlink()
    else:
        with manifest.open(encoding="utf-8", newline="") as file:
            reader = csv.DictReader(file)
            fields = reader.fieldnames
            rows = list(reader)
        if damage == "manifest":
            rows[0]["valid_pixels"] = "-1"
        else:
            rows[1] = rows[0].copy()
        with manifest.open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
    with pytest.raises(CustomException):
        DataValidation(16, 0.5, 16).validate_dataset(raster_path, tiles_dir)
    assert not (isolated_root / "artifacts/validation" / tiles_dir.name).exists()
