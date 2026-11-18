import requests
import rasterio

from pathlib import Path

from src.logger import logger
from src.exception import CustomException
from src.utils.common import resolve_path


class DataIngestion:
    """Memory-efficient geospatial raster ingestion."""

    def __init__(self, download_url: str, file_name: str):
        self.download_url = download_url

        if Path(file_name).name != file_name or not file_name:
            raise ValueError("Invalid dataset filename.")

        self.raw_data_path = resolve_path("data/raw") / file_name
        self.raw_data_path.parent.mkdir(
            parents=True, exist_ok=True
        )

    def download_bounded_raster(self) -> Path:
        """Stream a raster dataset to local storage."""

        temp_path = self.raw_data_path.with_suffix(
            self.raw_data_path.suffix + ".part"
        )

        try:
            if self.raw_data_path.exists():
                # Validate existing raster before reuse
                with rasterio.open(self.raw_data_path):
                    pass

                logger.info(
                    "Dataset already exists: %s",
                    self.raw_data_path
                )
                return self.raw_data_path

            logger.info(
                "Starting streamed download from: %s",
                self.download_url
            )

            downloaded_bytes = 0

            with requests.get(
                self.download_url,
                stream=True,
                timeout=(10, 60),
                headers={"Accept-Encoding": "identity"}
            ) as response:

                response.raise_for_status()

                expected_size = response.headers.get(
                    "Content-Length"
                )

                with temp_path.open("wb") as file:

                    for chunk in response.iter_content(
                        chunk_size=1024 * 1024
                    ):
                        if chunk:
                            file.write(chunk)
                            downloaded_bytes += len(chunk)

                if downloaded_bytes == 0:
                    raise ValueError("Downloaded file is empty.")

                if (
                    expected_size is not None
                    and response.headers.get(
                        "Content-Encoding", "identity"
                    ) == "identity"
                    and downloaded_bytes != int(expected_size)
                ):
                    raise IOError("Download size mismatch.")

            # Validate raster metadata before finalizing
            with rasterio.open(temp_path):
                pass

            temp_path.replace(self.raw_data_path)

            logger.info(
                "Download completed: %s | %.2f MB",
                self.raw_data_path,
                downloaded_bytes / (1024 ** 2)
            )

            return self.raw_data_path

        except Exception as error:
            temp_path.unlink(missing_ok=True)
            raise CustomException(error) from error

    def inspect_raster_metadata(self) -> dict:
        """Inspect metadata without reading pixel arrays."""

        try:
            if not self.raw_data_path.is_file():
                raise FileNotFoundError(
                    f"Raster not found: {self.raw_data_path}"
                )

            logger.info(
                "Inspecting raster: %s",
                self.raw_data_path.name
            )

            with rasterio.open(self.raw_data_path) as dataset:

                metadata = {
                    "driver": dataset.driver,
                    "width": dataset.width,
                    "height": dataset.height,
                    "bands": dataset.count,
                    "dtypes": list(dataset.dtypes),
                    "crs": str(dataset.crs),
                    "transform": list(dataset.transform)[:6],
                    "bounds": list(dataset.bounds),
                    "resolution": list(dataset.res),
                    "nodata": dataset.nodata,
                    "file_size_bytes":
                        self.raw_data_path.stat().st_size
                }

                for key, value in metadata.items():
                    logger.info("%s: %s", key, value)

                return metadata

        except Exception as error:
            raise CustomException(error) from error


if __name__ == "__main__":

    TEST_URL = (
        "https://raw.githubusercontent.com/rasterio/"
        "rasterio/master/tests/data/RGB.byte.tif"
    )

    try:
        logger.info("--- Starting Data Ingestion Test ---")

        ingestion = DataIngestion(
            download_url=TEST_URL,
            file_name="test_tile_01.tif"
        )

        ingestion.download_bounded_raster()
        ingestion.inspect_raster_metadata()

        logger.info("--- Data Ingestion Successful ---")

    except Exception:
        logger.exception("Data ingestion pipeline failed")
        raise SystemExit(1)