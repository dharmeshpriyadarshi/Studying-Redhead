import hashlib
import json
from pathlib import Path
from unittest.mock import MagicMock, Mock

import pytest
import requests
import yaml

from src.pipeline.data_pipeline import DataPipeline, calculate_sha256


def read_summary(pipeline):
    return json.loads(pipeline.summary_path.read_text(encoding="utf-8"))


def test_sha256(isolated_root):
    payload = b"Studying Redhead" * 100000
    path = isolated_root / "data/raw/checksum.bin"
    path.write_bytes(payload)
    assert calculate_sha256(path) == hashlib.sha256(payload).hexdigest()


@pytest.mark.integration
def test_two_complete_runs(pipeline_config, raster_path, monkeypatch):
    get = Mock(side_effect=AssertionError("Unexpected network call"))
    monkeypatch.setattr(requests, "get", get)
    first, second = DataPipeline(pipeline_config), DataPipeline(pipeline_config)
    first.run()
    second.run()
    a, b = read_summary(first), read_summary(second)
    assert a["run_id"] != b["run_id"]
    for report in (a, b):
        assert report["status"] == "passed"
        stages = report["stages"]
        assert all(s["status"] == "passed" for s in stages.values())
        assert stages["ingestion"]["output"]["cache_hit"] is True
        assert stages["ingestion"]["output"]["sha256"] == calculate_sha256(raster_path)
        assert stages["quality_gate"]["output"]["passed"] is True
        for stage, key in (("projection", "projected_path"), ("transformation", "manifest_path"), ("validation", "quality_report")):
            assert Path(stages[stage]["output"][key]).is_file()
    for stage, key in (("projection", "projected_path"), ("transformation", "tiles_dir"), ("validation", "report_dir")):
        assert a["stages"][stage]["output"][key] != b["stages"][stage]["output"][key]
    for key in ("total_tiles", "eligible_tiles", "fully_valid_pixels", "empty_tiles"):
        assert a["stages"]["validation"]["output"][key] == b["stages"]["validation"]["output"][key]
    get.assert_not_called()


@pytest.mark.integration
@pytest.mark.parametrize("kind, failed_stage, message", [
    ("checksum", "ingestion", "SHA-256 mismatch"),
    ("config", "configuration", "Invalid CRS"),
    ("quality", "quality_gate", "Insufficient eligible tiles"),
])
def test_failure_propagation(pipeline_config, kind, failed_stage, message, isolated_root):
    config = yaml.safe_load(pipeline_config.read_text(encoding="utf-8"))
    if kind == "checksum":
        config["pipeline"]["expected_sha256"] = "0" * 64
    elif kind == "config":
        config["pipeline"]["target_crs"] = "EPSG:32618"
    else:
        config["pipeline"]["min_eligible_tiles"] = 10000
    pipeline_config.write_text(yaml.safe_dump(config), encoding="utf-8")
    pipeline = DataPipeline(pipeline_config)
    with pytest.raises(ValueError, match=message):
        pipeline.run()
    report = read_summary(pipeline)
    assert report["status"] == "failed"
    assert report["stages"][failed_stage]["status"] == "failed"
    stage_order = list(pipeline.STAGES)
    index = stage_order.index(failed_stage)
    for name in stage_order[:index]:
        assert report["stages"][name]["status"] == "passed"
    for name in stage_order[index+1:]:
        assert report["stages"][name]["status"] == "skipped"
    if kind != "quality":
        assert not list((isolated_root / "data/interim").glob("*.tif"))
        assert not list((isolated_root / "data/processed").iterdir())


@pytest.mark.integration
@pytest.mark.parametrize("bad_hash", [False, True], ids=["verified", "checksum_mismatch"])
def test_fresh_download_pipeline(pipeline_config, raster_path, monkeypatch, bad_hash, isolated_root):
    payload = raster_path.read_bytes()
    raster_path.unlink()  # Only the temporary synthetic fixture.
    if bad_hash:
        config = yaml.safe_load(pipeline_config.read_text(encoding="utf-8"))
        config["pipeline"]["expected_sha256"] = "0" * 64
        pipeline_config.write_text(yaml.safe_dump(config), encoding="utf-8")
    response = MagicMock()
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    response.headers = {"Content-Length": str(len(payload))}
    response.iter_content.return_value = iter((payload[:1024], payload[1024:]))
    get = Mock(return_value=response)
    monkeypatch.setattr(requests, "get", get)
    pipeline = DataPipeline(pipeline_config)
    if bad_hash:
        with pytest.raises(ValueError, match="SHA-256 mismatch"):
            pipeline.run()
        report = read_summary(pipeline)
        assert report["status"] == "failed"
        assert report["stages"]["ingestion"]["status"] == "failed"
        assert report["stages"]["projection"]["status"] == "skipped"
        assert not list((isolated_root / "data/interim").glob("*.tif"))
        # Current ingestion publishes before orchestration checks the hash.
        # Cache invalidation/quarantine is a separate hardening task.
    else:
        pipeline.run()
        report = read_summary(pipeline)
        assert report["status"] == "passed"
        assert report["stages"]["ingestion"]["output"]["cache_hit"] is False
        assert raster_path.read_bytes() == payload
        assert report["stages"]["quality_gate"]["output"]["passed"] is True
    get.assert_called_once()
