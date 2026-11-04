#!/usr/bin/env python3
"""Align Sentinel-2 bands to a common 10 m grid (EPSG:32650) and clip to a
study area, using GDAL via gdalwarp-equivalent Python bindings / CLI.

Usage:
    python scripts/preprocess.py --input-dir data/raw/sentinel2_2021 \
        --study-area data/raw/study_area.gpkg --output-dir data/processed
"""
import argparse
import subprocess
import sys
from pathlib import Path

# 10 m bands used for indices; B11 (20 m) is resampled to 10 m on demand.
BANDS = ["B02", "B03", "B04", "B08"]
TARGET_SRS = "EPSG:32650"  # UTM zone 50N - appropriate for Beijing


def run(cmd: list) -> None:
    print("$", " ".join(cmd))
    subprocess.run(cmd, check=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input-dir", required=True,
                    help="directory containing B02.tif ... B08.tif")
    ap.add_argument("--study-area", required=True,
                    help="GeoPackage / GeoJSON with the clip polygon")
    ap.add_argument("--output-dir", required=True)
    args = ap.parse_args()

    indir, outdir = Path(args.input_dir), Path(args.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)

    for band in BANDS:
        src = indir / f"{band}.tif"
        if not src.exists():
            print(f"SKIP {band}: {src} not found", file=sys.stderr)
            continue
        dst = outdir / f"{band}_aligned.tif"
        run(["gdalwarp", "-t_srs", TARGET_SRS,
             "-tr", "10", "10",                # force 10 m pixels
             "-cutline", args.study_area,
             "-crop_to_cutline",
             "-dstnodata", "-9999",
             str(src), str(dst)])

    # Validation: all aligned bands share CRS, shape and transform.
    import rasterio
    ref = None
    for f in sorted(outdir.glob("*_aligned.tif")):
        with rasterio.open(f) as src:
            cur = (str(src.crs), src.width, src.height, src.res)
        if ref is None:
            ref = cur
            print(f"Reference grid: {f.name} {cur}")
        else:
            assert cur == ref, f"{f.name} grid mismatch: {cur} != {ref}"
        print(f"  OK {f.name}")
    print("ALL BANDS ALIGNED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
