#!/usr/bin/env python3
"""Convert Sentinel-2 raw DN crops to aligned reflectance GeoTIFFs."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import numpy as np
import rasterio
from src.indices import NODATA
from rasterio.features import geometry_mask
from rasterio.warp import (
    Resampling,
    reproject,
    transform_geom,
)

LOG = logging.getLogger("preprocess")

REFLECTANCE_BANDS = ("B02", "B03", "B04", "B08")


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def get_scale_offset(metadata: dict, band: str):
    """Read calibration coefficients from STAC raster:bands."""
    raster_band = metadata["assets"][band]["raster:bands"][0]

    scale = raster_band.get("scale")
    offset = raster_band.get("offset")
    nodata = raster_band.get("nodata")

    if scale is None or offset is None:
        raise ValueError(
            f"{band}: STAC scale/offset is missing"
        )

    return float(scale), float(offset), nodata


def make_aoi_mask(
    bbox: list[float],
    dst_crs,
    transform,
    width: int,
    height: int,
):
    """Return True for pixels whose centers are inside the AOI."""
    west, south, east, north = bbox

    geometry = {
        "type": "Polygon",
        "coordinates": [[
            [west, south],
            [east, south],
            [east, north],
            [west, north],
            [west, south],
        ]],
    }

    projected_geometry = transform_geom(
        "EPSG:4326",
        dst_crs,
        geometry,
        precision=-1,
    )

    return geometry_mask(
        [projected_geometry],
        out_shape=(height, width),
        transform=transform,
        invert=True,
        all_touched=False,
    )


def write_float_raster(
    output_path: Path,
    array: np.ndarray,
    valid_mask: np.ndarray,
    profile: dict,
    nodata: float,
    tags: dict,
):
    output = np.full(
        array.shape,
        nodata,
        dtype=np.float32,
    )

    output[valid_mask] = array[valid_mask].astype(
        np.float32,
        copy=False,
    )

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

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with rasterio.open(
        output_path,
        "w",
        **out_profile,
    ) as dst:
        dst.write(output, 1)
        dst.write_mask(
            (valid_mask.astype(np.uint8) * 255)
        )
        dst.update_tags(**tags)



def write_reflectance(
    source_path: Path,
    output_path: Path,
    offset: float,
    quantification_value: float,
):
    """Convert raw Sentinel-2 DN to BOA surface reflectance.

    Reflectance = (DN + offset) / quantification_value.
    DN=0 is always treated as NoData.
    """
    if not np.isfinite(quantification_value) or quantification_value <= 0:
        raise ValueError("quantification_value must be positive and finite")

    with rasterio.open(source_path) as src:
        dn = src.read(1)

        valid_mask = (
            (src.read_masks(1) > 0)
            & (dn != 0)
            & np.isfinite(dn)
        )

        reflectance = (
            dn.astype(np.float32) + np.float32(offset)
        ) / np.float32(quantification_value)

        profile = src.profile.copy()

    write_float_raster(
        output_path=Path(output_path),
        array=reflectance,
        valid_mask=valid_mask,
        profile=profile,
        nodata=float(NODATA),
        tags={
            "radiometric_calibration": "BOA",
            "formula": "(DN + offset) / quantification_value",
            "boa_add_offset": str(offset),
            "quantification_value": str(quantification_value),
            "source_file": Path(source_path).name,
        },
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--raw-dir",
        required=True,
        help="Raw Sentinel-2 item directory",
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

    raw_dir = Path(args.raw_dir)
    metadata_path = raw_dir / "item_metadata.json"

    if not metadata_path.exists():
        raise FileNotFoundError(metadata_path)

    metadata = load_json(metadata_path)
    config = load_json(Path(args.config))

    output_dir = (
        Path(args.output_dir)
        if args.output_dir
        else Path("data/processed") / metadata["item_id"]
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    nodata = float(config.get("nodata", -9999.0))
    bbox = metadata["project"]["bbox_wgs84"]

    reference_path = raw_dir / "B04.tif"

    with rasterio.open(reference_path) as ref:
        dst_crs = ref.crs
        dst_transform = ref.transform
        dst_width = ref.width
        dst_height = ref.height

        reference_profile = ref.profile.copy()

    aoi_mask = make_aoi_mask(
        bbox,
        dst_crs,
        dst_transform,
        dst_width,
        dst_height,
    )

    if not aoi_mask.any():
        raise RuntimeError("AOI mask contains no pixels")

    common_profile = reference_profile.copy()
    common_profile.update(
        crs=dst_crs,
        transform=dst_transform,
        width=dst_width,
        height=dst_height,
        count=1,
        dtype="float32",
        nodata=nodata,
    )

    band_valid_masks = {}

    # --------------------------------------------------------
    # 1. Reflectance bands
    # --------------------------------------------------------

    for band in REFLECTANCE_BANDS:
        source_path = raw_dir / f"{band}.tif"

        if not source_path.exists():
            raise FileNotFoundError(source_path)

        scale, offset, source_nodata = get_scale_offset(
            metadata,
            band,
        )

        LOG.info(
            "%s calibration: scale=%s offset=%s nodata=%s",
            band,
            scale,
            offset,
            source_nodata,
        )

        with rasterio.open(source_path) as src:
            if src.crs == dst_crs and (
                src.width == dst_width
                and src.height == dst_height
                and src.transform == dst_transform
            ):
                dn = src.read(1)
            else:
                # Reproject raw DN to the B04 reference grid.
                dn = np.zeros(
                    (dst_height, dst_width),
                    dtype=np.float32,
                )

                reproject(
                    source=rasterio.band(src, 1),
                    destination=dn,
                    src_transform=src.transform,
                    src_crs=src.crs,
                    src_nodata=(
                        source_nodata
                        if source_nodata is not None
                        else 0
                    ),
                    dst_transform=dst_transform,
                    dst_crs=dst_crs,
                    dst_nodata=0,
                    resampling=Resampling.bilinear,
                )

        valid = (
            np.isfinite(dn)
            & (dn != 0)
            & aoi_mask
        )

        reflectance = (
            dn.astype(np.float32) * scale + offset
        )

        valid &= np.isfinite(reflectance)

        band_valid_masks[band] = valid

        write_float_raster(
            output_dir / f"{band}.tif",
            reflectance,
            valid,
            common_profile,
            nodata,
            {
                "source_band": band,
                "scale": str(scale),
                "offset": str(offset),
                "calibration": "DN * scale + offset",
                "source_item": metadata["item_id"],
                "processing": "Sentinel-2 L2A reflectance",
            },
        )

        LOG.info(
            "%s valid pixels: %d / %d (%.4f%%)",
            band,
            int(valid.sum()),
            int(aoi_mask.sum()),
            100.0 * valid.sum() / aoi_mask.sum(),
        )

    # --------------------------------------------------------
    # 2. SCL: nearest-neighbor reprojection to B04 grid
    # --------------------------------------------------------

    scl_source_path = raw_dir / "SCL.tif"

    with rasterio.open(scl_source_path) as src:
        scl = np.zeros(
            (dst_height, dst_width),
            dtype=np.uint8,
        )

        reproject(
            source=rasterio.band(src, 1),
            destination=scl,
            src_transform=src.transform,
            src_crs=src.crs,
            src_nodata=(
                src.nodata if src.nodata is not None else 0
            ),
            dst_transform=dst_transform,
            dst_crs=dst_crs,
            dst_nodata=0,
            resampling=Resampling.nearest,
        )

    scl_valid = (
        (scl != 0)
        & aoi_mask
    )

    scl_profile = common_profile.copy()
    scl_profile.update(dtype="uint8", nodata=0)

    with rasterio.open(
        output_dir / "SCL_10m.tif",
        "w",
        **scl_profile,
    ) as dst:
        dst.write(scl, 1)
        dst.write_mask(
            scl_valid.astype(np.uint8) * 255
        )
        dst.update_tags(
            source_band="SCL",
            resampling="nearest",
            reference_grid="B04",
            source_item=metadata["item_id"],
        )

    # --------------------------------------------------------
    # 3. Processing report
    # --------------------------------------------------------

    report = {
        "item_id": metadata["item_id"],
        "datetime": metadata["datetime"],
        "bbox_wgs84": bbox,
        "crs": str(dst_crs),
        "transform": list(dst_transform),
        "width": dst_width,
        "height": dst_height,
        "resolution": list(reference_profile["transform"][:2]),
        "aoi_pixels": int(aoi_mask.sum()),
        "bands": {},
        "scl_classes": {},
    }

    for band, valid in band_valid_masks.items():
        report["bands"][band] = {
            "valid_pixels": int(valid.sum()),
            "valid_ratio_within_aoi": (
                float(valid.sum() / aoi_mask.sum())
            ),
        }

    for value, count in zip(
        *np.unique(scl[aoi_mask], return_counts=True)
    ):
        report["scl_classes"][str(int(value))] = int(count)

    report_path = output_dir / "preprocess_report.json"

    report_path.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    LOG.info("Preprocessing completed: %s", output_dir)
    LOG.info("Report: %s", report_path)


if __name__ == "__main__":
    main()
