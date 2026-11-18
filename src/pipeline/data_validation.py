
import csv
import json
import math
from pathlib import Path
from tempfile import TemporaryDirectory

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import rasterio
from rasterio.windows import Window

from src.logger import logger
from src.exception import CustomException
from src.utils.common import resolve_path, read_yaml


def require(condition, message):
    if not condition:
        raise ValueError(message)


class DataValidation:
    """Validate tiles and generate reproducible quality reports."""

    def __init__(
        self,
        tile_size=256,
        min_valid_fraction=0.5,
        histogram_bins=32
    ):
        require(
            type(tile_size) is int and tile_size > 0,
            "Invalid tile size."
        )

        require(
            0 < min_valid_fraction <= 1,
            "Coverage threshold must be in (0, 1]."
        )

        require(
            type(histogram_bins) is int
            and 1 <= histogram_bins <= 4096,
            "Invalid histogram bin count."
        )

        self.tile_size = tile_size
        self.threshold = min_valid_fraction
        self.bins = histogram_bins
        self.nodata = -9999.0

    def validate_dataset(self, source_path, tiles_dir):

        try:

            source_path = resolve_path(source_path)
            tiles_dir = resolve_path(tiles_dir)

            report_dir = (
                resolve_path("artifacts/validation")
                / tiles_dir.name
            )

            require(
                not report_dir.exists(),
                f"Report already exists: {report_dir}"
            )

            with (tiles_dir / "manifest.csv").open(
                encoding="utf-8",
                newline=""
            ) as file:
                records = list(csv.DictReader(file))

            quality = []
            size = self.tile_size
            total_valid = 0

            with rasterio.open(source_path) as src:

                require(
                    src.crs is not None,
                    "Source CRS missing."
                )

                require(
                    all(t == "uint8" for t in src.dtypes),
                    "Expected uint8 source imagery."
                )

                require(
                    all(s == 1 for s in src.scales)
                    and all(o == 0 for o in src.offsets),
                    "Unexpected source scale or offset."
                )

                expected_offsets = {
                    (r, c)
                    for r in range(0, src.height, size)
                    for c in range(0, src.width, size)
                }

                actual_offsets = [
                    (
                        int(r["row_offset"]),
                        int(r["col_offset"])
                    )
                    for r in records
                ]

                require(
                    len(records) == len(expected_offsets)
                    and set(actual_offsets) == expected_offsets,
                    "Missing, duplicated or unexpected tile offsets."
                )

                expected_names = {
                    f"tile_r{r:06d}_c{c:06d}.tif"
                    for r, c in expected_offsets
                }

                require(
                    {
                        p.name for p in tiles_dir.glob("*.tif")
                    } == expected_names,
                    "Tile file inventory does not match expected grid."
                )

                stats = [
                    dict(
                        count=0,
                        total=0.0,
                        squares=0.0,
                        minimum=None,
                        maximum=None
                    )
                    for _ in range(src.count)
                ]

                hist = np.zeros(
                    (src.count, self.bins),
                    dtype=np.int64
                )

                coverage = np.zeros((
                    math.ceil(src.height / size),
                    math.ceil(src.width / size)
                ))

                source_pixels = src.width * src.height

                for record in records:

                    row = int(record["row_offset"])
                    col = int(record["col_offset"])

                    width = min(size, src.width - col)
                    height = min(size, src.height - row)

                    name = f"tile_r{row:06d}_c{col:06d}.tif"

                    require(
                        record["filename"] == name
                        and record["source"] == source_path.name
                        and int(record["tile_size"]) == size
                        and int(record["source_width"]) == width
                        and int(record["source_height"]) == height,
                        f"Manifest metadata mismatch: {name}"
                    )

                    window = Window(col, row, width, height)

                    original = src.read(
                        window=window,
                        masked=True
                    )

                    expected = np.full(
                        (src.count, size, size),
                        self.nodata,
                        dtype=np.float32
                    )

                    values = (
                        original.data.astype(np.float32)
                        / np.float32(255)
                    )

                    values[
                        np.ma.getmaskarray(original)
                    ] = self.nodata

                    expected[:, :height, :width] = values

                    with rasterio.open(tiles_dir / name) as tile:

                        require(
                            tile.width == size
                            and tile.height == size
                            and tile.count == src.count
                            and tile.crs == src.crs
                            and tile.nodata == self.nodata
                            and all(
                                t == "float32"
                                for t in tile.dtypes
                            )
                            and tile.transform.almost_equals(
                                src.window_transform(window)
                            ),
                            f"Raster schema mismatch: {name}"
                        )

                        actual = tile.read()

                    require(
                        np.array_equal(actual, expected),
                        f"Pixel values or NoData differ from source: {name}"
                    )

                    valid = actual != self.nodata

                    valid_pixels = int(
                        np.count_nonzero(
                            np.all(valid, axis=0)
                        )
                    )

                    fraction = valid_pixels / size**2

                    require(
                        valid_pixels == int(record["valid_pixels"])
                        and math.isclose(
                            fraction,
                            float(record["valid_fraction"]),
                            rel_tol=0,
                            abs_tol=1e-9
                        ),
                        f"Manifest coverage mismatch: {name}"
                    )

                    eligible = fraction >= self.threshold

                    quality.append({
                        **record,
                        "valid_pixels": valid_pixels,
                        "valid_fraction": fraction,
                        "training_eligible": eligible
                    })

                    coverage[
                        row // size,
                        col // size
                    ] = fraction

                    total_valid += valid_pixels

                    for i, s in enumerate(stats):

                        v = actual[i][valid[i]].astype(
                            np.float64
                        )

                        if not v.size:
                            continue

                        s["count"] += int(v.size)
                        s["total"] += float(v.sum())

                        s["squares"] += float(
                            np.square(v).sum()
                        )

                        low = float(v.min())
                        high = float(v.max())

                        s["minimum"] = (
                            low if s["minimum"] is None
                            else min(s["minimum"], low)
                        )

                        s["maximum"] = (
                            high if s["maximum"] is None
                            else max(s["maximum"], high)
                        )

                        hist[i] += np.histogram(
                            v,
                            bins=self.bins,
                            range=(0, 1)
                        )[0]

                    logger.info(
                        "Validated %s | Valid: %.2f%% | Eligible: %s",
                        name,
                        fraction * 100,
                        eligible
                    )

            bands = []

            for i, s in enumerate(stats):

                n = s["count"]

                mean = s["total"] / n if n else None

                std = (
                    math.sqrt(
                        max(0.0, s["squares"] / n - mean**2)
                    )
                    if n else None
                )

                bands.append({
                    "band": i + 1,
                    "valid_samples": n,
                    "min": s["minimum"],
                    "max": s["maximum"],
                    "mean": mean,
                    "std": std,
                    "histogram_counts": hist[i].tolist()
                })

            report = {
                "status": "passed",
                "source": source_path.name,
                "tile_size": size,
                "total_tiles": len(quality),
                "min_valid_fraction": self.threshold,
                "eligible_tiles": sum(
                    r["training_eligible"]
                    for r in quality
                ),
                "empty_tiles": sum(
                    r["valid_pixels"] == 0
                    for r in quality
                ),
                "fully_valid_pixels": total_valid,
                "source_pixels": source_pixels,
                "padded_pixels": len(quality) * size**2,
                "source_valid_fraction": (
                    total_valid / source_pixels
                ),
                "padded_valid_fraction": (
                    total_valid / (len(quality) * size**2)
                ),
                "histogram_edges": np.linspace(
                    0, 1, self.bins + 1
                ).tolist(),
                "bands": bands
            }

            report_dir.parent.mkdir(
                parents=True,
                exist_ok=True
            )

            with TemporaryDirectory(
                dir=report_dir.parent,
                prefix=".validation_"
            ) as temp:

                stage = Path(temp) / "report"
                stage.mkdir()

                with (stage / "quality_report.json").open(
                    "w",
                    encoding="utf-8"
                ) as f:

                    json.dump(
                        report,
                        f,
                        indent=2,
                        allow_nan=False
                    )

                with (stage / "tile_quality.csv").open(
                    "w",
                    encoding="utf-8",
                    newline=""
                ) as f:

                    writer = csv.DictWriter(
                        f,
                        fieldnames=list(quality[0])
                    )

                    writer.writeheader()
                    writer.writerows(quality)

                self.plot_reports(stage, hist, coverage)

                stage.rename(report_dir)

            logger.info(
                "Total tiles: %s | Eligible: %s | Empty: %s",
                report["total_tiles"],
                report["eligible_tiles"],
                report["empty_tiles"]
            )

            logger.info(
                "Quality reports: %s",
                report_dir
            )

            return report_dir

        except Exception as error:
            raise CustomException(error) from error

    def plot_reports(self, output, hist, coverage):

        edges = np.linspace(0, 1, self.bins + 1)

        fig, ax = plt.subplots(figsize=(9, 5))

        try:

            for i, counts in enumerate(hist):

                ax.stairs(
                    counts,
                    edges,
                    label=f"Band {i + 1}"
                )

            ax.set(
                xlabel="Normalized intensity",
                ylabel="Valid sample count",
                title="Per-band intensity distributions"
            )

            ax.legend()
            fig.tight_layout()

            fig.savefig(
                output / "intensity_histogram.png",
                dpi=150
            )

        finally:
            plt.close(fig)

        fig, ax = plt.subplots(figsize=(8, 6))

        try:

            image = ax.imshow(
                coverage * 100,
                vmin=0,
                vmax=100,
                cmap="viridis"
            )

            fig.colorbar(
                image,
                ax=ax,
                label="Fully valid pixels (%)"
            )

            ax.set(
                xlabel="Tile column",
                ylabel="Tile row",
                title="Spatial tile coverage"
            )

            if coverage.size <= 100:

                for (r, c), value in np.ndenumerate(coverage):

                    ax.text(
                        c,
                        r,
                        f"{value * 100:.1f}%",
                        ha="center",
                        va="center",
                        color=(
                            "white" if value < 0.5 else "black"
                        )
                    )

            fig.tight_layout()

            fig.savefig(
                output / "tile_coverage.png",
                dpi=150
            )

        finally:
            plt.close(fig)


if __name__ == "__main__":

    try:

        logger.info("--- Starting Dataset Validation ---")

        config = read_yaml("configs/config.yaml")

        validator = DataValidation(
            tile_size=config["geospatial"]["tile_size"],
            min_valid_fraction=config["validation"][
                "min_valid_fraction"
            ],
            histogram_bins=config["validation"][
                "histogram_bins"
            ]
        )

        validator.validate_dataset(
            source_path=(
                "data/interim/reprojected_test_tile_01.tif"
            ),
            tiles_dir=(
                "data/processed/"
                "reprojected_test_tile_01_tiles_256"
            )
        )

        logger.info("--- Dataset Validation Successful ---")

    except Exception:
        logger.exception("Dataset validation failed")
        raise SystemExit(1)
