import csv

import numpy as np
import pytest
import rasterio
from rasterio.windows import Window

from src.exception import CustomException
from src.pipeline.data_transformation import DataTransformation


def test_normalization_and_mask():
    tile = np.ma.array([[[0, 128, 255]]], dtype=np.uint8, mask=[[[True, False, False]]])
    result = DataTransformation(16).normalize_tile(tile)
    assert result.dtype == np.float32
    np.testing.assert_array_equal(result, np.array([[[-9999, 128 / 255, 1]]], dtype=np.float32))


def test_all_tiles_and_edge_padding(raster_path, source_array, tiles_dir):
    with (tiles_dir / "manifest.csv").open(encoding="utf-8", newline="") as f:
        records = list(csv.DictReader(f))
    assert len(records) == 6
    assert len(list(tiles_dir.glob("*.tif"))) == 6
    assert {(int(r["row_offset"]), int(r["col_offset"])) for r in records} == {
        (r, c) for r in (0, 16) for c in (0, 16, 32)
    }
    with rasterio.open(raster_path) as source:
        for record in records:
            r, c = int(record["row_offset"]), int(record["col_offset"])
            h, w = min(16, 19 - r), min(16, 35 - c)
            chunk = source_array[:, r:r+h, c:c+w]
            expected = np.full((3, 16, 16), -9999, dtype=np.float32)
            expected[:, :h, :w] = np.where(chunk == 0, -9999, chunk.astype(np.float32) / 255)
            with rasterio.open(tiles_dir / record["filename"]) as tile:
                assert tile.shape == (16, 16)
                assert tile.crs == source.crs
                assert tile.nodata == -9999
                assert tile.transform.almost_equals(source.window_transform(Window(c, r, w, h)))
                np.testing.assert_array_equal(tile.read(), expected)
            count = int(np.count_nonzero(np.all(expected != -9999, axis=0)))
            assert int(record["valid_pixels"]) == count
            assert float(record["valid_fraction"]) == pytest.approx(count / 256)


def test_refuses_overwrite(raster_path, tiles_dir):
    before = (tiles_dir / "manifest.csv").read_bytes()
    with pytest.raises(CustomException, match="already exists"):
        DataTransformation(16).generate_tiles(raster_path)
    assert (tiles_dir / "manifest.csv").read_bytes() == before


@pytest.mark.parametrize("size", [0, -1, 1.5, True])
def test_invalid_tile_size(size):
    with pytest.raises(ValueError):
        DataTransformation(size)


def test_reject_non_uint8():
    with pytest.raises(ValueError, match="uint8"):
        DataTransformation(16).normalize_tile(np.ma.array([1], dtype=np.float32))
