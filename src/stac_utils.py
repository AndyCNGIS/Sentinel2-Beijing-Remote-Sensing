"""Utilities for querying Earth Search and extracting Sentinel-2 assets."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pystac_client


def open_catalog(stac_url: str):
    """Open a STAC API catalog."""
    return pystac_client.Client.open(stac_url)


def search_items(
    stac_url: str,
    collection: str,
    bbox: list[float],
    datetime_range: str,
    max_items: int = 100,
):
    """Search Sentinel-2 items intersecting a WGS84 bounding box."""
    if len(bbox) != 4:
        raise ValueError("bbox must contain [west, south, east, north]")

    west, south, east, north = bbox

    if west >= east or south >= north:
        raise ValueError(f"Invalid bbox: {bbox}")

    catalog = open_catalog(stac_url)

    search = catalog.search(
        collections=[collection],
        bbox=bbox,
        datetime=datetime_range,
        max_items=max_items,
    )

    return list(search.items())


def select_item(items, item_id: str | None = None):
    """Select a specific item, or the lowest-cloud item."""
    if not items:
        raise RuntimeError("STAC search returned no items")

    if item_id:
        for item in items:
            if item.id == item_id:
                return item
        raise RuntimeError(
            f"Requested item was not found: {item_id}"
        )

    def cloud_value(item):
        value = item.properties.get("eo:cloud_cover")
        return float("inf") if value is None else float(value)

    return min(items, key=cloud_value)


def get_asset_hrefs(item, band_mapping: dict[str, str]):
    """Return asset hrefs using logical band names."""
    result = {}

    for band, asset_key in band_mapping.items():
        if asset_key not in item.assets:
            raise KeyError(
                f"Missing asset {asset_key!r} for band {band}"
            )

        result[band] = item.assets[asset_key].href

    return result


def get_raster_band_metadata(item, band_mapping: dict[str, str]):
    """Extract STAC raster:bands metadata for each asset."""
    result = {}

    for band, asset_key in band_mapping.items():
        asset = item.assets[asset_key]
        raster_bands = asset.extra_fields.get("raster:bands")

        if not raster_bands:
            raise ValueError(
                f"Missing raster:bands metadata for {asset_key}"
            )

        result[band] = raster_bands[0]

    return result


def item_metadata_dict(item, band_mapping: dict[str, str]):
    """Build a compact, JSON-serializable provenance record."""
    assets = {}

    for band, asset_key in band_mapping.items():
        asset = item.assets[asset_key]

        assets[band] = {
            "asset_key": asset_key,
            "href": asset.href,
            "type": asset.media_type,
            "roles": asset.roles,
            "raster:bands": asset.extra_fields.get("raster:bands"),
        }

    return {
        "item_id": item.id,
        "collection": item.collection_id,
        "datetime": (
            item.datetime.isoformat()
            if isinstance(item.datetime, datetime)
            else str(item.datetime)
        ),
        "geometry": item.geometry,
        "bbox": item.bbox,
        "properties": item.properties,
        "assets": assets,
    }
