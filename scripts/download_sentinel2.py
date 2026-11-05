#!/usr/bin/env python3
"""Search Earth Search and crop Sentinel-2 COG assets to the AOI.

The four reflectance bands (B02/B03/B04/B08) must share the same
native source grid. B04 is used as the authoritative 10 m reference
grid. SCL is retained at its native 20 m resolution.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
from pathlib import Path

import rasterio
from rasterio.crs import CRS
from rasterio.windows import Window, from_bounds

from src.stac_utils import (
    get_asset_hrefs,
    item_metadata_dict,
    search_items,
    select_item,
)

LOG = logging.getLogger("download_sentinel2")


def load_config(path: str) -> dict:
    """Load project configuration from a JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def crop_window(src, bbox: list[float]) -> Window:
    """Calculate a clamped pixel window for a WGS84 bbox."""
    from rasterio.warp import transform_bounds

    projected = transform_bounds(
        "EPSG:4326",
        src.crs,
        *bbox,
        densify_pts=21,
    )

    left = max(projected[0], src.bounds.left)
    bottom = max(projected[1], src.bounds.bottom)
    right = min(projected[2], src.bounds.right)
    top = min(projected[3], src.bounds.top)

    if left >= right or bottom >= top:
        raise ValueError(
            f"AOI does not intersect asset: {src.name}"
        )

    raw = from_bounds(
        left,
        bottom,
        right,
        top,
        transform=src.transform,
    )

    col0 = max(0, math.floor(raw.col_off))
    row0 = max(0, math.floor(raw.row_off))
    col1 = min(
        src.width,
        math.ceil(raw.col_off + raw.width),
    )
    row1 = min(
        src.height,
        math.ceil(raw.row_off + raw.height),
    )

    if col1 <= col0 or row1 <= row0:
        raise ValueError("Computed crop window is empty")

    return Window(
        col_off=col0,
        row_off=row0,
        width=col1 - col0,
        height=row1 - row0,
    )


def write_cropped_asset(
    band: str,
    href: str,
    output_path: Path,
    bbox: list[float],
    reference_grid: dict | None = None,
) -> dict:
    """Read one COG window and write raw source pixels locally.

    When reference_grid is supplied, the source CRS, resolution and
    affine transform must match B04 before its crop window is reused.
    """
    LOG.info("Reading %s from COG", band)

    with rasterio.open(href) as src:
        window = crop_window(src, bbox)

        if reference_grid is not None:
            expected = reference_grid

            if src.crs != expected["crs"]:
                raise ValueError(
                    f"{band}: CRS differs from B04 "
                    f"({src.crs} != {expected['crs']})"
                )

            if src.res != expected["res"]:
                raise ValueError(
                    f"{band}: resolution differs from B04 "
                    f"({src.res} != {expected['res']})"
                )

            if src.transform != expected["source_transform"]:
                raise ValueError(
                    f"{band}: source transform differs from B04. "
                    "Cannot safely reuse the B04 crop window."
                )

            # The same pixel window is safe only for identical grids.
            window = expected["window"]

            col_end = window.col_off + window.width
            row_end = window.row_off + window.height

            if col_end > src.width or row_end > src.height:
                raise ValueError(
                    f"{band}: B04 crop window exceeds source dimensions "
                    f"({src.width} x {src.height})"
                )

        data = src.read(1, window=window)

        if data.size == 0:
            raise ValueError(
                f"{band}: crop produced an empty raster"
            )

        transform = src.window_transform(window)

        profile = src.profile.copy()
        profile.update(
            driver="GTiff",
            height=data.shape[0],
            width=data.shape[1],
            transform=transform,
            count=1,
            compress="deflate",
            predictor=2 if data.dtype.kind in "ui" else 3,
            tiled=True,
            blockxsize=256,
            blockysize=256,
        )

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with rasterio.open(output_path, "w", **profile) as dst:
            dst.write(data, 1)
            dst.update_tags(
                source="AWS Earth Search Sentinel-2 COG",
                logical_band=band,
                source_href=href,
            )

        grid = {
            "crs": src.crs,
            "res": src.res,
            "source_transform": src.transform,
            "window": window,
            "transform": transform,
            "width": data.shape[1],
            "height": data.shape[0],
        }

        LOG.info(
            "%s: wrote %s (%s x %s)",
            band,
            output_path,
            data.shape[1],
            data.shape[0],
        )

        return grid


def validate_b04_grid(b04_grid: dict, config: dict) -> None:
    """Validate the B04 source grid against configured output CRS/resolution."""
    if "output_crs" not in config:
        raise KeyError("Missing required config key: output_crs")

    if "resolution" not in config:
        raise KeyError("Missing required config key: resolution")

    expected_crs = CRS.from_user_input(config["output_crs"])

    if b04_grid["crs"] != expected_crs:
        raise ValueError(
            f"B04 CRS {b04_grid['crs']} does not match "
            f"configured output_crs {expected_crs}"
        )

    expected_resolution = float(config["resolution"])

    if expected_resolution <= 0:
        raise ValueError(
            f"Configured resolution must be positive: "
            f"{expected_resolution}"
        )

    if any(
        not math.isclose(
            abs(value),
            expected_resolution,
            rel_tol=0.0,
            abs_tol=1e-6,
        )
        for value in b04_grid["res"]
    ):
        raise ValueError(
            f"B04 resolution {b04_grid['res']} does not match "
            f"configured resolution {expected_resolution}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Download and crop Sentinel-2 L2A COG assets "
            "from Earth Search."
        )
    )
    parser.add_argument(
        "--config",
        default="configs/beijing_2021_summer.json",
    )
    parser.add_argument(
        "--output-root",
        default="data/raw/sentinel2",
    )
    parser.add_argument("--item-id", default=None)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    config = load_config(args.config)

    items = search_items(
        config["stac_url"],
        config["collection"],
        config["bbox"],
        config["datetime"],
        config.get("max_items", 100),
    )

    max_cloud = config.get("cloud_cover_max")

    if max_cloud is not None:
        items = [
            item
            for item in items
            if item.properties.get("eo:cloud_cover") is not None
            and float(item.properties["eo:cloud_cover"]) <= max_cloud
        ]

    item = select_item(
        items,
        args.item_id or config.get("item_id"),
    )

    LOG.info("Selected product: %s", item.id)
    LOG.info("Datetime: %s", item.datetime)
    LOG.info(
        "Cloud cover: %s",
        item.properties.get("eo:cloud_cover"),
    )

    band_mapping = config["bands"]
    hrefs = get_asset_hrefs(item, band_mapping)

    required_bands = {"B02", "B03", "B04", "B08", "SCL"}
    missing_bands = required_bands - set(hrefs)

    if missing_bands:
        raise ValueError(
            f"Missing required assets: {sorted(missing_bands)}"
        )

    output_dir = Path(args.output_root) / item.id
    output_dir.mkdir(parents=True, exist_ok=True)

    metadata_path = output_dir / "item_metadata.json"

    expected_files = [
        output_dir / f"{band}.tif"
        for band in band_mapping
    ]

    if (
        not args.overwrite
        and all(path.exists() for path in expected_files)
        and metadata_path.exists()
    ):
        LOG.info("All output files already exist; skipping.")
        return

    # B04 is the authoritative 10 m reference grid.
    b04_path = output_dir / "B04.tif"

    if args.overwrite and b04_path.exists():
        b04_path.unlink()

    b04_grid = write_cropped_asset(
        "B04",
        hrefs["B04"],
        b04_path,
        config["bbox"],
    )

    # Check that the actual B04 grid matches the project configuration.
    validate_b04_grid(b04_grid, config)

    # The other 10 m reflectance bands must have the same source grid.
    for band in ("B02", "B03", "B08"):
        output_path = output_dir / f"{band}.tif"

        if args.overwrite and output_path.exists():
            output_path.unlink()

        write_cropped_asset(
            band,
            hrefs[band],
            output_path,
            config["bbox"],
            reference_grid=b04_grid,
        )

    # SCL remains at its native 20 m resolution in raw/.
    scl_path = output_dir / "SCL.tif"

    if args.overwrite and scl_path.exists():
        scl_path.unlink()

    write_cropped_asset(
        "SCL",
        hrefs["SCL"],
        scl_path,
        config["bbox"],
    )

    metadata = item_metadata_dict(item, band_mapping)
    metadata["project"] = {
        "bbox_wgs84": config["bbox"],
        "output_crs": config["output_crs"],
        "resolution": config["resolution"],
        "requested_item_id": item.id,
    }

    metadata_path.write_text(
        json.dumps(
            metadata,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    LOG.info("Metadata written: %s", metadata_path)
    LOG.info("Download and crop completed.")


if __name__ == "__main__":
    main()
