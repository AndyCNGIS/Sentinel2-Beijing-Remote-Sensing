# Sentinel-2 Beijing Remote Sensing

Beijing Sentinel-2 remote sensing data engineering pipeline: STAC catalog search,
multispectral preprocessing, spectral index computation (NDVI / NDWI) and
cloud masking, implemented with pure open-source Python on an ARM64 (aarch64)
CPU server.

## Why this project

This repository demonstrates the remote sensing data engineering skills required
for GIS / remote sensing graduate study applications:

- Search big Earth observation catalogs with **STAC** (SpatioTemporal Asset Catalog)
- Preprocess multispectral rasters with **GDAL / Rasterio**
- Compute and validate spectral indices (NDVI, NDWI)
- Handle NoData, cloud masks and per-band grid alignment correctly
- Write reproducible, tested processing scripts

## Environment

```bash
conda activate gis-core   # geopandas, rasterio, gdal, pystac-client, ...
```

Created with conda-forge on Linux aarch64 (Kylin V10, Phytium ARM64 v8.2).

## Project structure

```
Sentinel2-Beijing-Remote-Sensing/
├── README.md
├── scripts/
│   ├── search_sentinel2.py     # PySTAC-client search against Copernicus STAC
│   ├── preprocess.py           # band stacking, reprojection, clipping
│   └── calculate_indices.py    # NDVI / NDWI with NoData-safe computation
├── src/
│   └── indices.py              # reusable index computation functions
├── tests/
│   └── test_indices.py         # offline unit tests (synthetic rasters)
├── data/README.md              # data sources and licences (no raw data in git)
└── outputs/                    # generated indices / catalogs (git-ignored)
```

## Usage

### 1. Search Sentinel-2 scenes (requires internet access to Copernicus)

```bash
python scripts/search_sentinel2.py
```

Searches `sentinel-2-l2a` over a Beijing study-area bbox for summer 2021,
cloud cover < 20%, and writes the item list to `outputs/sentinel2_catalog.json`.

### 2. Preprocess bands (after downloading a scene)

```bash
python scripts/preprocess.py \
    --input-dir data/raw/sentinel2_2021 \
    --study-area data/raw/study_area.gpkg \
    --output-dir data/processed
```

Aligns B02/B03/B04/B08 to a common 10 m grid (EPSG:32650) and clips to the
study area. Validation: every aligned band reports identical CRS, transform,
width and height.

### 3. Compute NDVI / NDWI

```bash
python scripts/calculate_indices.py \
    --red data/processed/B04.tif \
    --nir data/processed/B08.tif \
    --green data/processed/B03.tif \
    --outdir outputs/indices
```

### 4. Run tests (offline, no download needed)

```bash
python -m pytest tests/ -v
```

## Principles

- **Band alignment first**: NDVI = (NIR − Red) / (NIR + Red) is only valid when
  both rasters share the same CRS, grid and resolution. Misaligned bands produce
  geographically meaningless indices.
- **NoData safety**: denominators equal to zero and NoData pixels are written as
  −9999, never as NaN-as-zero, so water/shadow pixels are not confused with
  valid values.
- **Index range**: valid NDVI / NDWI must lie in [−1, 1]; tests assert this.
- **STAC metadata ≠ downloadable asset**: Copernicus assets may require an
  account; the search script checks `item.assets` and reports links honestly.

## Data sources

- Copernicus Data Space Ecosystem (Sentinel-2 L2A) — ESA free licence
- ESA WorldCover 2021 v200 (land cover reference) — CC-BY 4.0
- Geofabrik OpenStreetMap Beijing extracts — ODbL

See `data/README.md`.

## Known limitations

- Real scene download requires external network access; the offline unit tests
  use synthetic rasters so the pipeline logic is still verified in CI-less
  environments.
- SCL cloud masking is applied in `calculate_indices.py` only when an SCL band
  is supplied (Sentinel-2 L2A).
