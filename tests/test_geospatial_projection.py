import pytest
import rasterio
from rasterio.warp import calculate_default_transform

from src.exception import CustomException
from src.pipeline.geospatial_projection import GeospatialProjector
from src.pipeline.data_pipeline import calculate_sha256


def test_reprojection_and_reuse(raster_path):
    before = calculate_sha256(raster_path)
    projector = GeospatialProjector("EPSG:3857")
    output = projector.reproject_raster(raster_path, "projected.tif")
    with rasterio.open(raster_path) as raw, rasterio.open(output) as dst:
        transform, width, height = calculate_default_transform(
            raw.crs, "EPSG:3857", raw.width, raw.height, *raw.bounds
        )
        assert raw.crs.to_epsg() == 32618
        assert dst.crs.to_epsg() == 3857
        assert (dst.width, dst.height) == (width, height)
        assert dst.transform.almost_equals(transform)
        assert dst.count == 3
        assert dst.nodata == 0
        assert dst.dtypes == raw.dtypes
        assert dst.read_masks().any()
    assert calculate_sha256(raster_path) == before
    assert not output.with_suffix(".tif.part").exists()
    output_hash = calculate_sha256(output)
    assert projector.reproject_raster(raster_path, "projected.tif") == output
    assert calculate_sha256(output) == output_hash


def test_missing_source():
    with pytest.raises(CustomException):
        GeospatialProjector("EPSG:3857").reproject_raster("missing.tif", "output.tif")


def test_existing_output_mismatch(raster_path, isolated_root):
    output = isolated_root / "data/interim/projected.tif"
    output.write_bytes(raster_path.read_bytes())
    before = calculate_sha256(output)
    with pytest.raises(CustomException, match="metadata mismatch"):
        GeospatialProjector("EPSG:3857").reproject_raster(raster_path, output.name)
    assert calculate_sha256(output) == before
