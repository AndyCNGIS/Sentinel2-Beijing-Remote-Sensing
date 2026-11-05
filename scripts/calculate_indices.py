#!/usr/bin/env python3
"""Calculate NDVI and McFeeters NDWI from aligned reflectance rasters."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import numpy as np
import rasterio

LOG = logging.getLogger("calculate_indices")


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _grid_value(obj, key):
    """Read a grid property from a Rasterio dataset or profile dict."""
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key)


def assert_same_grid(reference, current, band_name: str):
    """Require two rasters/profiles to have exactly the same spatial grid."""
    reference_crs = _grid_value(reference, "crs")
    current_crs = _grid_value(current, "crs")
    if current_crs != reference_crs:
        raise ValueError(f"{band_name}: CRS mismatch")

    reference_transform = _grid_value(reference, "transform")
    current_transform = _grid_value(current, "transform")
    if current_transform != reference_transform:
        raise ValueError(f"{band_name}: affine transform mismatch")

    for dimension in ("width", "height"):
        if _grid_value(current, dimension) != _grid_value(reference, dimension):
            raise ValueError(f"{band_name}: {dimension} mismatch")

    reference_res = _grid_value(reference, "res")
    current_res = _grid_value(current, "res")
    if current_res != reference_res:
        raise ValueError(f"{band_name}: resolution mismatch")


def check_alignment(datasets: dict):
    """Require identical CRS, transform, dimensions and resolution."""
    if "B04" not in datasets:
        raise ValueError("B04 reference raster is missing")

    reference = datasets["B04"]

    for name, src in datasets.items():
        assert_same_grid(reference, src, name)


def calculate_index(
    numerator_a: np.ndarray,
    numerator_b: np.ndarray,
    denominator_a: np.ndarray,
    denominator_b: np.ndarray,
    valid_mask: np.ndarray,
    epsilon: float,
):
    """Calculate normalized difference with safe denominator handling."""
    numerator = numerator_a - numerator_b
    denominator = denominator_a + denominator_b

    valid = (
        valid_mask
        & np.isfinite(numerator)
        & np.isfinite(denominator)
        & (np.abs(denominator) >= epsilon)
    )

    result = np.full(
        numerator.shape,
        np.nan,
        dtype=np.float32,
    )

    np.divide(
        numerator,
        denominator,
        out=result,
        where=valid,
    )

    valid &= np.isfinite(result)

    return result, valid


def write_index(
    path: Path,
    data: np.ndarray,
    valid: np.ndarray,
    profile: dict,
    nodata: float,
    index_name: str,
    tags: dict,
):
    output = np.full(
        data.shape,
        nodata,
        dtype=np.float32,
    )

    output[valid] = data[valid]

    out_profile = profile.copy()
    out_profile.update(
        driver="GTiff",
        dtype="float32",
        count=1,
        nodata=nodata,
        compress="deflate",
        predictor=3,
        tiled=True,
        blockxsize=256,
        blockysize=256,
    )

    with rasterio.open(path, "w", **out_profile) as dst:
        dst.write(output, 1)
        dst.write_mask(
            valid.astype(np.uint8) * 255
        )
        dst.update_tags(
            index=index_name,
            **tags,
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input-dir",
        required=True,
        help="Preprocessed reflectance directory",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
    )
    parser.add_argument(
        "--config",
        default="configs/beijing_2021_summer.json",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    input_dir = Path(args.input_dir)
    output_dir = (
        Path(args.output_dir)
        if args.output_dir
        else input_dir
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    config = load_config(args.config)
    nodata = float(config.get("nodata", -9999.0))
    epsilon = float(
        config.get("denominator_epsilon", 1e-6)
    )
    valid_classes = config.get(
        "scl_valid_classes",
        [4, 5, 6],
    )

    names = ["B02", "B03", "B04", "B08", "SCL_10m"]
    datasets = {}

    try:
        for name in names:
            path = input_dir / f"{name}.tif"
            if not path.exists():
                raise FileNotFoundError(path)
            datasets[name] = rasterio.open(path)

        check_alignment(datasets)

        arrays = {
            name: datasets[name].read(1)
            for name in names
        }

        masks = {
            name: datasets[name].read_masks(1) > 0
            for name in names
        }

        reference = datasets["B04"]
        profile = reference.profile.copy()

        scl = arrays["SCL_10m"]

        scl_mask = (
            masks["SCL_10m"]
            & np.isin(scl, valid_classes)
        )

        common_valid = scl_mask.copy()

        for band in ("B03", "B04", "B08"):
            common_valid &= masks[band]
            common_valid &= np.isfinite(arrays[band])
            common_valid &= arrays[band] != nodata

        # NDVI = (NIR - RED) / (NIR + RED)
        ndvi, ndvi_valid = calculate_index(
            arrays["B08"],
            arrays["B04"],
            arrays["B08"],
            arrays["B04"],
            common_valid,
            epsilon,
        )

        # McFeeters NDWI = (GREEN - NIR) / (GREEN + NIR)
        ndwi, ndwi_valid = calculate_index(
            arrays["B03"],
            arrays["B08"],
            arrays["B03"],
            arrays["B08"],
            common_valid,
            epsilon,
        )

        item_id = reference.tags().get(
            "source_item",
            "unknown",
        )

        tags = {
            "source_item": item_id,
            "scl_valid_classes": ",".join(
                str(x) for x in valid_classes
            ),
            "denominator_epsilon": str(epsilon),
            "nodata": str(nodata),
        }

        write_index(
            output_dir / "NDVI.tif",
            ndvi,
            ndvi_valid,
            profile,
            nodata,
            "NDVI",
            tags,
        )

        write_index(
            output_dir / "NDWI.tif",
            ndwi,
            ndwi_valid,
            profile,
            nodata,
            "McFeeters NDWI",
            tags,
        )

        report = {
            "NDVI": {
                "valid_pixels": int(ndvi_valid.sum()),
                "valid_ratio": float(ndvi_valid.mean()),
                "min": float(ndvi[ndvi_valid].min()),
                "max": float(ndvi[ndvi_valid].max()),
                "mean": float(ndvi[ndvi_valid].mean()),
            },
            "NDWI": {
                "valid_pixels": int(ndwi_valid.sum()),
                "valid_ratio": float(ndwi_valid.mean()),
                "min": float(ndwi[ndwi_valid].min()),
                "max": float(ndwi[ndwi_valid].max()),
                "mean": float(ndwi[ndwi_valid].mean()),
            },
            "scl_valid_classes": valid_classes,
            "denominator_epsilon": epsilon,
        }

        (output_dir / "indices_report.json").write_text(
            json.dumps(
                report,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        LOG.info("NDVI statistics: %s", report["NDVI"])
        LOG.info("NDWI statistics: %s", report["NDWI"])
        LOG.info("Index calculation completed.")

    finally:
        for src in datasets.values():
            src.close()


if __name__ == "__main__":
    main()
