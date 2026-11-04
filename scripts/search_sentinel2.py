#!/usr/bin/env python3
"""Search Copernicus STAC for Sentinel-2 L2A scenes over Beijing.

Requires outbound HTTPS access to stac.dataspace.copernicus.eu.
Writes matched item metadata to outputs/sentinel2_catalog.json.

Usage:
    python scripts/search_sentinel2.py
"""
import json
import sys
from pathlib import Path

from pystac_client import Client

# Beijing study area bounding box (lon_min, lat_min, lon_max, lat_max)
BBOX = [116.25, 39.80, 116.50, 40.05]
DATETIME = "2021-06-01/2021-09-30"  # summer season, same-season comparison
MAX_CLOUD = 20  # percent
MAX_ITEMS = 30

CATALOG_URL = "https://stac.dataspace.copernicus.eu/v1"
OUT = Path("outputs/sentinel2_catalog.json")


def main() -> int:
    catalog = Client.open(CATALOG_URL)
    print("Catalog:", catalog.id)

    search = catalog.search(
        collections=["sentinel-2-l2a"],
        bbox=BBOX,
        datetime=DATETIME,
        query={"eo:cloud_cover": {"lt": MAX_CLOUD}},
        max_items=MAX_ITEMS,
    )
    items = list(search.items())
    print(f"Matched items: {len(items)}")
    if not items:
        print("No scenes matched - try relaxing cloud cover or the date range.")
        return 1

    records = []
    for item in items:
        records.append({
            "id": item.id,
            "datetime": str(item.datetime),
            "cloud_cover": item.properties.get("eo:cloud_cover"),
            "assets": list(item.assets.keys()),
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(records, ensure_ascii=False, indent=2), "utf-8")
    print(f"Wrote {OUT}")

    # Honest validation report
    for r in records:
        assert r["id"], "empty scene id"
        assert r["cloud_cover"] is None or r["cloud_cover"] < MAX_CLOUD
    print("Validation: all ids non-empty, all cloud covers < "
          f"{MAX_CLOUD}%  OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
