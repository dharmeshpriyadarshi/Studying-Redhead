from unittest.mock import MagicMock, Mock

import pytest
import requests

from src.exception import CustomException
from src.pipeline.data_ingestion import DataIngestion

URL = "https://example.invalid/synthetic.tif"


def fake_response(payload, length=None):
    response = MagicMock()
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    response.headers = {"Content-Length": str(len(payload) if length is None else length)}
    response.iter_content.return_value = iter((payload[:1024], payload[1024:]))
    return response


def test_streamed_download(raster_path, monkeypatch):
    payload = raster_path.read_bytes()
    response = fake_response(payload)
    get = Mock(return_value=response)
    monkeypatch.setattr(requests, "get", get)
    ingestion = DataIngestion(URL, "downloaded.tif")
    output = ingestion.download_bounded_raster()
    assert output.read_bytes() == payload
    assert get.call_args.kwargs["stream"] is True
    assert response.iter_content.called
    assert not output.with_suffix(".tif.part").exists()
    metadata = ingestion.inspect_raster_metadata()
    assert (metadata["width"], metadata["height"], metadata["bands"]) == (35, 19, 3)
    assert metadata["crs"] == "EPSG:32618"


def test_existing_raster_reused(raster_path, monkeypatch):
    get = Mock(side_effect=AssertionError("Unexpected download"))
    monkeypatch.setattr(requests, "get", get)
    ingestion = DataIngestion(URL, raster_path.name)
    assert ingestion.download_bounded_raster() == raster_path
    get.assert_not_called()


@pytest.mark.parametrize("kind", ["empty", "size_mismatch", "invalid_raster", "http_error", "stream_error"])
def test_failed_download_cleanup(isolated_root, raster_path, monkeypatch, kind):
    payload = raster_path.read_bytes()
    response = fake_response(payload)
    if kind == "empty":
        response = fake_response(b"")
    elif kind == "size_mismatch":
        response = fake_response(payload, length=len(payload) + 1)
    elif kind == "invalid_raster":
        response = fake_response(b"not a raster")
    elif kind == "http_error":
        response.raise_for_status.side_effect = requests.HTTPError("503")
    elif kind == "stream_error":
        def broken_stream():
            yield payload[:1024]
            raise requests.ConnectionError("Interrupted stream")
        response.iter_content.return_value = broken_stream()
    monkeypatch.setattr(requests, "get", Mock(return_value=response))
    ingestion = DataIngestion(URL, "failed.tif")
    with pytest.raises(CustomException):
        ingestion.download_bounded_raster()
    assert not ingestion.raw_data_path.exists()
    assert not ingestion.raw_data_path.with_suffix(".tif.part").exists()


def test_missing_metadata():
    with pytest.raises(CustomException):
        DataIngestion(URL, "missing.tif").inspect_raster_metadata()
