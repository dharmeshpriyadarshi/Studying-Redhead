
from pathlib import Path

import rasterio
from rasterio.crs import CRS
from rasterio.warp import (
    calculate_default_transform,
    reproject,
    Resampling
)

from src.logger import logger
from src.exception import CustomException
from src.utils.common import resolve_path


class GeospatialProjector:
    """Memory-efficient geospatial raster reprojection."""

    def __init__(
        self,
        target_crs: str,
        resampling: Resampling = Resampling.nearest,
        warp_memory_limit: int = 64
    ):
        self.target_crs = CRS.from_user_input(target_crs)
        self.resampling = resampling
        self.warp_memory_limit = warp_memory_limit

        self.interim_dir = resolve_path("data/interim")
        self.interim_dir.mkdir(parents=True, exist_ok=True)

    def reproject_raster(
        self,
        source_path: str | Path,
        output_filename: str
    ) -> Path:
        """Reproject a raster without loading its full array."""

        temp_path = None

        try:
            source_path = resolve_path(source_path)

            if not source_path.is_file():
                raise FileNotFoundError(
                    f"Source raster not found: {source_path}"
                )

            if (
                not output_filename
                or Path(output_filename).name != output_filename
                or not output_filename.lower().endswith(".tif")
            ):
                raise ValueError("Invalid output filename.")

            dest_path = self.interim_dir / output_filename

            if dest_path.resolve() == source_path:
                raise ValueError(
                    "Source and destination must be different."
                )

            temp_path = dest_path.with_suffix(".tif.part")

            with rasterio.open(source_path) as src:

                if src.crs is None:
                    raise ValueError("Source raster has no CRS.")

                logger.info("Source raster: %s", source_path)
                logger.info("Source CRS: %s", src.crs)
                logger.info("Target CRS: %s", self.target_crs)
                logger.info("Resampling: %s", self.resampling.name)

                transform, width, height = (
                    calculate_default_transform(
                        src.crs,
                        self.target_crs,
                        src.width,
                        src.height,
                        *src.bounds
                    )
                )

                if width <= 0 or height <= 0:
                    raise ValueError(
                        "Invalid destination raster dimensions."
                    )

                logger.info(
                    "Original dimensions: %s x %s",
                    src.width,
                    src.height
                )

                logger.info(
                    "Target dimensions: %s x %s",
                    width,
                    height
                )

                logger.info(
                    "Calculated affine transform: %s",
                    transform
                )

                if dest_path.exists():

                    with rasterio.open(dest_path) as existing:

                        if (
                            existing.crs != self.target_crs
                            or existing.width != width
                            or existing.height != height
                            or existing.count != src.count
                            or existing.dtypes != src.dtypes
                            or not existing.transform.almost_equals(
                                transform
                            )
                        ):
                            raise ValueError(
                                "Existing output metadata mismatch."
                            )

                    logger.info(
                        "Reprojected raster already exists: %s",
                        dest_path
                    )

                    return dest_path

                profile = src.meta.copy()

                profile.update({
                    "driver": "GTiff",
                    "crs": self.target_crs,
                    "transform": transform,
                    "width": width,
                    "height": height,
                    "compress": "deflate",
                    "tiled": True,
                    "blockxsize": 256,
                    "blockysize": 256,
                    "BIGTIFF": "IF_SAFER"
                })

                with rasterio.open(
                    temp_path, "w", **profile
                ) as dst:

                    for band in range(1, src.count + 1):

                        logger.info(
                            "Reprojecting band %s of %s",
                            band,
                            src.count
                        )

                        reproject(
                            source=rasterio.band(src, band),
                            destination=rasterio.band(dst, band),
                            src_transform=src.transform,
                            src_crs=src.crs,
                            src_nodata=src.nodata,
                            dst_transform=transform,
                            dst_crs=self.target_crs,
                            dst_nodata=src.nodata,
                            resampling=self.resampling,
                            warp_mem_limit=self.warp_memory_limit,
                            num_threads=2
                        )

            with rasterio.open(temp_path) as result:

                if result.crs != self.target_crs:
                    raise ValueError("Output CRS validation failed.")

                logger.info("Output CRS: %s", result.crs)
                logger.info("Output bounds: %s", result.bounds)
                logger.info("Output resolution: %s", result.res)

            temp_path.replace(dest_path)

            logger.info(
                "Geospatial projection completed: %s",
                dest_path
            )

            return dest_path

        except Exception as error:

            if temp_path is not None:
                temp_path.unlink(missing_ok=True)

            raise CustomException(error) from error


if __name__ == "__main__":

    try:
        logger.info("--- Starting Coordinate Projection Test ---")

        projector = GeospatialProjector(
            target_crs="EPSG:3857",
            resampling=Resampling.nearest
        )

        projector.reproject_raster(
            source_path="data/raw/test_tile_01.tif",
            output_filename="reprojected_test_tile_01.tif"
        )

        logger.info("--- Coordinate Projection Successful ---")

    except Exception:
        logger.exception("Coordinate projection failed")
        raise SystemExit(1)
