#!/usr/bin/env python3
"""Compute NDVI and NDWI from aligned Sentinel-2 bands.

Bands must already share CRS / grid / resolution (see scripts/preprocess.py).
An optional SCL band applies the Sentinel-2 L2A cloud mask before computing.

Usage:
    python scripts/calculate_indices.py --red B04.tif --nir B08.tif \
        --green B03.tif [--scl SCL.tif] --outdir outputs/indices
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import rasterio

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.indices import ndvi, ndwi, scl_cloud_mask, NODATA  # noqa: E402


def read_band(path: str):
    """Read band 1 as float32 plus its validity mask and profile."""
    with rasterio.open(path) as src:
        data = src.read(1).astype(np.float32)
        profile = src.profile.copy()
        nodata = src.nodata
    valid = np.isfinite(data)
    if nodata is not None:
        valid &= data != nodata
    return data, valid, profile


def write_index(arr: np.ndarray, profile: dict, path: Path) -> None:
    profile.update(count=1, dtype="float32", nodata=NODATA)
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(arr, 1)
    print(f"Wrote {path}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--red", required=True, help="B04 (red) GeoTIFF, 10 m")
    ap.add_argument("--nir", required=True, help="B08 (NIR) GeoTIFF, 10 m")
    ap.add_argument("--green", required=True, help="B03 (green) GeoTIFF, 10 m")
    ap.add_argument("--scl", default=None, help="SCL band for cloud masking")
    ap.add_argument("--outdir", default="outputs/indices")
    args = ap.parse_args()

    red, vred, profile = read_band(args.red)
    nir, vnir, _ = read_band(args.nir)
    green, vgreen, _ = read_band(args.green)

    # Grid alignment precondition: shapes must match or the result is
    # geographically meaningless.
    assert red.shape == nir.shape == green.shape, (
        "band shapes differ - run preprocess.py first to align grids")

    valid = vred & vnir & vgreen
    if args.scl:
        with rasterio.open(args.scl) as src:
            scl = src.read(1)
        valid &= scl_cloud_mask(scl)
        print(f"Applied SCL cloud mask (kept {valid.mean():.1%} pixels)")

    outdir = Path(args.outdir)
    write_index(ndvi(nir, red, valid), profile, outdir / "ndvi.tif")
    write_index(ndwi(green, nir, valid), profile, outdir / "ndwi.tif")

    # Validation: valid index values must lie in [-1, 1]
    for name in ("ndvi", "ndwi"):
        with rasterio.open(outdir / f"{name}.tif") as src:
            arr = src.read(1)
        ok = arr != NODATA
        lo, hi = arr[ok].min(), arr[ok].max()
        assert -1.0 <= lo and hi <= 1.0, f"{name} out of range: [{lo}, {hi}]"
        print(f"{name}: valid pixels {ok.sum()}, range [{lo:.3f}, {hi:.3f}] OK")
    print("ALL INDEX CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
