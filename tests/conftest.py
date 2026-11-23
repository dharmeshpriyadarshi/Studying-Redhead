"""Isolated, offline fixtures for the data pipeline."""
import numpy as np
import pytest
import rasterio
import requests
import yaml
from rasterio.transform import from_origin

from src.utils import common
from src.pipeline.data_pipeline import calculate_sha256


@pytest.fixture(autouse=True)
def isolated_root(tmp_path, monkeypatch):
    """Redirect project-relative paths; deny real Requests HTTP traffic."""
    tmp_path = tmp_path.resolve()
    monkeypatch.setattr(common, "ROOT_DIR", tmp_path)
    for name in ("data/raw", "data/interim", "data/processed", "artifacts", "configs"):
        (tmp_path / name).mkdir(parents=True, exist_ok=True)

    def deny_http(*args, **kwargs):
        raise AssertionError("Live HTTP is not allowed in this test suite.")

    monkeypatch.setattr(requests.sessions.Session, "request", deny_http)
    return tmp_path


@pytest.fixture
def source_array():
    """Known values with shared and band-specific NoData pixels."""
    values = (np.arange(3 * 19 * 35).reshape(3, 19, 35) % 255 + 1)
    values = values.astype(np.uint8)
    values[:, :2, :3] = 0
    values[0, 4, 4] = 0
    return values


@pytest.fixture
def raster_path(isolated_root, source_array):
    path = isolated_root / "data/raw/synthetic.tif"
    with rasterio.open(
        path, "w", driver="GTiff", width=35, height=19,
        count=3, dtype="uint8", crs="EPSG:32618",
        transform=from_origin(500000, 2800000, 30, 30), nodata=0,
    ) as dst:
        dst.write(source_array)
    return path


@pytest.fixture
def tiles_dir(raster_path):
    from src.pipeline.data_transformation import DataTransformation
    return DataTransformation(tile_size=16).generate_tiles(raster_path)


@pytest.fixture
def pipeline_config(isolated_root, raster_path):
    config = {
        "geospatial": {"tile_size": 16, "target_crs": None},
        "validation": {"min_valid_fraction": 0.1, "histogram_bins": 16},
        "pipeline": {
            "profile": "earth_smoke_test",
            "source_url": "https://example.invalid/synthetic.tif",
            "raw_filename": raster_path.name,
            "expected_sha256": calculate_sha256(raster_path),
            "source_crs": "EPSG:32618", "target_crs": "EPSG:3857",
            "resampling": "nearest", "warp_memory_limit_mb": 64,
            "min_eligible_tiles": 1,
        },
    }
    path = isolated_root / "configs/config.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return path
