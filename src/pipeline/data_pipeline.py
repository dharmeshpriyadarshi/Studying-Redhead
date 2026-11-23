
import argparse
import hashlib
import json
import re

from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from rasterio.crs import CRS
from rasterio.warp import Resampling

from src.logger import logger
from src.utils.common import resolve_path, read_yaml

from src.pipeline.data_ingestion import DataIngestion
from src.pipeline.geospatial_projection import GeospatialProjector
from src.pipeline.data_transformation import DataTransformation
from src.pipeline.data_validation import DataValidation


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def calculate_sha256(file_path):
    """Calculate file checksum without loading it into memory."""

    digest = hashlib.sha256()

    with Path(file_path).open("rb") as file:

        for chunk in iter(
            lambda: file.read(1024 * 1024),
            b""
        ):
            digest.update(chunk)

    return digest.hexdigest()


class DataPipeline:
    """Configuration-driven data pipeline orchestration."""

    STAGES = (
        "configuration",
        "ingestion",
        "projection",
        "transformation",
        "validation",
        "quality_gate"
    )

    def __init__(self, config_path="configs/config.yaml"):

        self.config_path = resolve_path(config_path)

        timestamp = datetime.now(timezone.utc).strftime(
            "%Y%m%dT%H%M%S%fZ"
        )

        self.run_id = f"{timestamp}_{uuid4().hex[:8]}"

        self.run_dir = (
            resolve_path("artifacts/pipeline_runs")
            / self.run_id
        )

        self.summary_path = self.run_dir / "run_summary.json"

        self.summary = {
            "run_id": self.run_id,
            "config_path": str(self.config_path),
            "status": "running",
            "started_at": utc_now(),
            "stages": {
                name: {"status": "pending"}
                for name in self.STAGES
            }
        }

    def write_summary(self):
        """Atomically persist the current execution state."""

        temporary = self.summary_path.with_suffix(".json.tmp")

        with temporary.open("w", encoding="utf-8") as file:

            json.dump(
                self.summary,
                file,
                indent=2,
                allow_nan=False
            )

        temporary.replace(self.summary_path)

    def run_stage(self, name, action):
        """Execute and track an individual pipeline stage."""

        stage = self.summary["stages"][name]

        stage["status"] = "running"
        stage["started_at"] = utc_now()

        logger.info("Starting stage: %s", name)

        started = perf_counter()

        self.write_summary()

        try:

            output = action()

            stage["output"] = output
            stage["status"] = "passed"

            logger.info("Stage completed: %s", name)

            return output

        except Exception as error:

            stage["status"] = "failed"

            stage["error"] = {
                "type": type(error).__name__,
                "message": str(error)
            }

            logger.error("Stage failed: %s", name)

            raise

        finally:

            stage["finished_at"] = utc_now()

            stage["elapsed_seconds"] = round(
                perf_counter() - started,
                6
            )

            self.write_summary()

    def load_configuration(self):
        """Load and validate the current pipeline configuration."""

        config = read_yaml(self.config_path)

        pipeline = config["pipeline"]
        geospatial = config["geospatial"]
        validation = config["validation"]

        settings = {
            "profile": pipeline["profile"],
            "source_url": pipeline["source_url"],
            "raw_filename": pipeline["raw_filename"],
            "expected_sha256": pipeline["expected_sha256"].lower(),
            "source_crs": pipeline["source_crs"],
            "target_crs": pipeline["target_crs"],
            "resampling": pipeline["resampling"],
            "warp_memory_limit_mb": pipeline["warp_memory_limit_mb"],
            "min_eligible_tiles": pipeline["min_eligible_tiles"],
            "tile_size": geospatial["tile_size"],
            "min_valid_fraction": validation["min_valid_fraction"],
            "histogram_bins": validation["histogram_bins"]
        }

        if settings["profile"] != "earth_smoke_test":
            raise ValueError("Unsupported pipeline profile.")

        if not settings["source_url"].startswith("https://"):
            raise ValueError("Source URL must use HTTPS.")

        filename = settings["raw_filename"]

        if (
            not filename
            or "/" in filename
            or "\\" in filename
            or not filename.lower().endswith(".tif")
        ):
            raise ValueError("Invalid raw raster filename.")

        if not re.fullmatch(
            r"[0-9a-f]{64}",
            settings["expected_sha256"]
        ):
            raise ValueError(
                "Expected SHA-256 must contain 64 hexadecimal characters."
            )

        source_crs = CRS.from_user_input(
            settings["source_crs"]
        )

        target_crs = CRS.from_user_input(
            settings["target_crs"]
        )

        if (
            source_crs != CRS.from_epsg(32618)
            or target_crs != CRS.from_epsg(3857)
        ):
            raise ValueError(
                "Invalid CRS for the Earth smoke-test profile."
            )

        if settings["resampling"] not in {
            "nearest", "bilinear", "cubic"
        }:
            raise ValueError("Unsupported resampling method.")

        for key in (
            "tile_size",
            "warp_memory_limit_mb",
            "min_eligible_tiles",
            "histogram_bins"
        ):

            if (
                type(settings[key]) is not int
                or settings[key] <= 0
            ):
                raise ValueError(
                    f"{key} must be a positive integer."
                )

        if settings["histogram_bins"] > 4096:
            raise ValueError("Too many histogram bins.")

        if not 0 < settings["min_valid_fraction"] <= 1:
            raise ValueError("Invalid minimum valid fraction.")

        return settings

    def execute_ingestion(self, settings):

        ingestion = DataIngestion(
            download_url=settings["source_url"],
            file_name=settings["raw_filename"]
        )

        cache_hit = ingestion.raw_data_path.is_file()

        raw_path = ingestion.download_bounded_raster()

        checksum = calculate_sha256(raw_path)

        if checksum != settings["expected_sha256"]:

            raise ValueError(
                "Raw raster SHA-256 mismatch. "
                f"Expected: {settings['expected_sha256']} | "
                f"Observed: {checksum}"
            )

        metadata = ingestion.inspect_raster_metadata()

        if CRS.from_user_input(metadata["crs"]) != (
            CRS.from_user_input(settings["source_crs"])
        ):
            raise ValueError("Unexpected source raster CRS.")

        logger.info("Raw raster checksum verified: %s", checksum)

        return {
            "raw_path": str(raw_path),
            "sha256": checksum,
            "cache_hit": cache_hit,
            "crs": metadata["crs"],
            "width": metadata["width"],
            "height": metadata["height"],
            "bands": metadata["bands"]
        }

    def execute_projection(self, settings, ingestion):

        projector = GeospatialProjector(
            target_crs=settings["target_crs"],
            resampling=Resampling[settings["resampling"]],
            warp_memory_limit=settings["warp_memory_limit_mb"],
            target_body="Earth",
        )

        raw_path = Path(ingestion["raw_path"])

        output_filename = (
            f"reprojected_{raw_path.stem}_{self.run_id}.tif"
        )

        projected_path = projector.reproject_raster(
            source_path=raw_path,
            output_filename=output_filename
        )

        return {
            "projected_path": str(projected_path),
            "target_crs": settings["target_crs"],
            "resampling": settings["resampling"]
        }

    def execute_transformation(self, settings, projection):

        transformation = DataTransformation(
            tile_size=settings["tile_size"]
        )

        tiles_dir = transformation.generate_tiles(
            source_path=projection["projected_path"]
        )

        return {
            "tiles_dir": str(tiles_dir),
            "manifest_path": str(tiles_dir / "manifest.csv")
        }

    def execute_validation(
        self,
        settings,
        projection,
        transformation
    ):

        validator = DataValidation(
            tile_size=settings["tile_size"],
            min_valid_fraction=settings["min_valid_fraction"],
            histogram_bins=settings["histogram_bins"]
        )

        report_dir = validator.validate_dataset(
            source_path=projection["projected_path"],
            tiles_dir=transformation["tiles_dir"]
        )

        report_path = report_dir / "quality_report.json"

        with report_path.open(encoding="utf-8") as file:
            report = json.load(file)

        return {
            "report_dir": str(report_dir),
            "quality_report": str(report_path),
            "tile_quality": str(report_dir / "tile_quality.csv"),
            "status": report["status"],
            "total_tiles": report["total_tiles"],
            "eligible_tiles": report["eligible_tiles"],
            "empty_tiles": report["empty_tiles"],
            "fully_valid_pixels": report["fully_valid_pixels"]
        }

    def execute_quality_gate(self, settings, validation):

        if validation["status"] != "passed":
            raise ValueError("Dataset integrity validation failed.")

        minimum = settings["min_eligible_tiles"]

        if validation["eligible_tiles"] < minimum:

            raise ValueError(
                "Insufficient eligible tiles. "
                f"Required: {minimum} | "
                f"Observed: {validation['eligible_tiles']}"
            )

        return {
            "passed": True,
            "minimum_eligible_tiles": minimum,
            "eligible_tiles": validation["eligible_tiles"]
        }

    def run(self):
        """Execute the complete data engineering pipeline."""

        started = perf_counter()

        self.run_dir.mkdir(
            parents=True,
            exist_ok=False
        )

        self.write_summary()

        logger.info("Pipeline run ID: %s", self.run_id)
        logger.info("Run summary: %s", self.summary_path)

        try:

            settings = self.run_stage(
                "configuration",
                self.load_configuration
            )

            ingestion = self.run_stage(
                "ingestion",
                lambda: self.execute_ingestion(settings)
            )

            projection = self.run_stage(
                "projection",
                lambda: self.execute_projection(
                    settings, ingestion
                )
            )

            transformation = self.run_stage(
                "transformation",
                lambda: self.execute_transformation(
                    settings, projection
                )
            )

            validation = self.run_stage(
                "validation",
                lambda: self.execute_validation(
                    settings,
                    projection,
                    transformation
                )
            )

            self.run_stage(
                "quality_gate",
                lambda: self.execute_quality_gate(
                    settings, validation
                )
            )

            self.summary["status"] = "passed"

            logger.info(
                "Pipeline completed successfully: %s",
                self.run_id
            )

            return self.summary_path

        except Exception as error:

            self.summary["status"] = "failed"

            self.summary["error"] = {
                "type": type(error).__name__,
                "message": str(error)
            }

            for stage in self.summary["stages"].values():

                if stage["status"] == "pending":
                    stage["status"] = "skipped"

            raise

        finally:

            self.summary["finished_at"] = utc_now()

            self.summary["elapsed_seconds"] = round(
                perf_counter() - started,
                6
            )

            self.write_summary()

            logger.info(
                "Pipeline execution time: %.3f seconds",
                self.summary["elapsed_seconds"]
            )


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="Studying Redhead data pipeline"
    )

    parser.add_argument(
        "--config",
        default="configs/config.yaml"
    )

    args = parser.parse_args()

    try:

        logger.info("--- Starting Unified Data Pipeline ---")

        pipeline = DataPipeline(config_path=args.config)

        summary_path = pipeline.run()

        logger.info("Execution summary: %s", summary_path)

        logger.info("--- Unified Data Pipeline Successful ---")

    except Exception:

        logger.exception("Unified data pipeline failed")

        raise SystemExit(1)
