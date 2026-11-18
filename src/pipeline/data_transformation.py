
import csv
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import rasterio
from rasterio.windows import Window

from src.logger import logger
from src.exception import CustomException
from src.utils.common import resolve_path, read_yaml


class DataTransformation:
    """Window-based raster tiling and image normalization."""

    def __init__(self, tile_size: int = 256):

        if type(tile_size) is not int or tile_size <= 0:
            raise ValueError("Tile size must be a positive integer.")

        self.tile_size = tile_size
        self.nodata = -9999.0
        self.processed_dir = resolve_path("data/processed")
        self.processed_dir.mkdir(parents=True, exist_ok=True)

    def normalize_tile(self, tile: np.ma.MaskedArray) -> np.ndarray:
        """Normalize uint8 values while preserving invalid pixels."""

        if tile.dtype != np.uint8:
            raise ValueError(
                "This normalization method requires uint8 imagery."
            )

        mask = np.ma.getmaskarray(tile)

        normalized = tile.data.astype(np.float32) / np.float32(255.0)

        normalized[mask] = self.nodata

        return normalized

    def generate_tiles(self, source_path: str | Path) -> Path:
        """Generate fixed-size, georeferenced raster tiles."""

        try:

            source_path = resolve_path(source_path)

            if not source_path.is_file():
                raise FileNotFoundError(
                    f"Source raster not found: {source_path}"
                )

            output_dir = self.processed_dir / (
                f"{source_path.stem}_tiles_{self.tile_size}"
            )

            if output_dir.exists():
                raise FileExistsError(
                    f"Output directory already exists: {output_dir}. "
                    "Move it before regenerating tiles."
                )

            logger.info("Starting raster transformation")
            logger.info("Source raster: %s", source_path)
            logger.info("Tile size: %s", self.tile_size)

            tile_count = 0
            fully_valid_pixels = 0

            fields = [
                "filename",
                "source",
                "row_offset",
                "col_offset",
                "source_width",
                "source_height",
                "tile_size",
                "valid_pixels",
                "valid_fraction"
            ]

            with TemporaryDirectory(
                dir=self.processed_dir,
                prefix=".tiles_"
            ) as temp_dir:

                staging_dir = Path(temp_dir) / "tiles"
                staging_dir.mkdir()

                manifest_path = staging_dir / "manifest.csv"

                with rasterio.open(source_path) as src:

                    if src.crs is None:
                        raise ValueError("Source raster has no CRS.")

                    if any(dtype != "uint8" for dtype in src.dtypes):
                        raise ValueError(
                            "Current normalization supports "
                            "uint8 imagery only."
                        )

                    if (
                        any(scale != 1.0 for scale in src.scales)
                        or any(offset != 0.0 for offset in src.offsets)
                    ):
                        raise ValueError(
                            "Source has non-default scale or offset."
                        )

                    logger.info("Source CRS: %s", src.crs)
                    logger.info(
                        "Source dimensions: %s x %s",
                        src.width,
                        src.height
                    )
                    logger.info("Source bands: %s", src.count)

                    with manifest_path.open(
                        "w",
                        newline="",
                        encoding="utf-8"
                    ) as manifest_file:

                        writer = csv.DictWriter(
                            manifest_file,
                            fieldnames=fields
                        )

                        writer.writeheader()

                        for row in range(
                            0, src.height, self.tile_size
                        ):

                            for col in range(
                                0, src.width, self.tile_size
                            ):

                                width = min(
                                    self.tile_size,
                                    src.width - col
                                )

                                height = min(
                                    self.tile_size,
                                    src.height - row
                                )

                                window = Window(
                                    col, row, width, height
                                )

                                data = src.read(
                                    window=window,
                                    masked=True
                                )

                                normalized = self.normalize_tile(data)

                                tile = np.full(
                                    (
                                        src.count,
                                        self.tile_size,
                                        self.tile_size
                                    ),
                                    self.nodata,
                                    dtype=np.float32
                                )

                                tile[:, :height, :width] = normalized

                                valid_pixels = int(
                                    np.count_nonzero(
                                        np.all(
                                            tile != self.nodata,
                                            axis=0
                                        )
                                    )
                                )

                                valid_fraction = (
                                    valid_pixels / self.tile_size**2
                                )

                                transform = src.window_transform(
                                    window
                                )

                                filename = (
                                    f"tile_r{row:06d}_c{col:06d}.tif"
                                )

                                tile_path = staging_dir / filename

                                profile = {
                                    "driver": "GTiff",
                                    "height": self.tile_size,
                                    "width": self.tile_size,
                                    "count": src.count,
                                    "dtype": "float32",
                                    "crs": src.crs,
                                    "transform": transform,
                                    "nodata": self.nodata,
                                    "compress": "deflate"
                                }

                                with rasterio.open(
                                    tile_path, "w", **profile
                                ) as dst:

                                    dst.write(tile)

                                    dst.update_tags(
                                        normalization="uint8_divide_255",
                                        source=source_path.name,
                                        row_offset=row,
                                        col_offset=col
                                    )

                                writer.writerow({
                                    "filename": filename,
                                    "source": source_path.name,
                                    "row_offset": row,
                                    "col_offset": col,
                                    "source_width": width,
                                    "source_height": height,
                                    "tile_size": self.tile_size,
                                    "valid_pixels": valid_pixels,
                                    "valid_fraction": valid_fraction
                                })

                                tile_count += 1
                                fully_valid_pixels += valid_pixels

                                logger.info(
                                    "Generated %s | Valid: %.2f%%",
                                    filename,
                                    valid_fraction * 100
                                )

                staging_dir.rename(output_dir)

            logger.info("Total tiles generated: %s", tile_count)

            logger.info(
                "Fully valid spatial pixels: %s",
                fully_valid_pixels
            )

            logger.info("Processed artifacts: %s", output_dir)

            return output_dir

        except Exception as error:
            raise CustomException(error) from error


if __name__ == "__main__":

    try:

        logger.info("--- Starting Data Transformation Test ---")

        config = read_yaml("configs/config.yaml")

        transformation = DataTransformation(
            tile_size=config["geospatial"]["tile_size"]
        )

        transformation.generate_tiles(
            source_path=(
                "data/interim/reprojected_test_tile_01.tif"
            )
        )

        logger.info("--- Data Transformation Successful ---")

    except Exception:
        logger.exception("Data transformation pipeline failed")
        raise SystemExit(1)
