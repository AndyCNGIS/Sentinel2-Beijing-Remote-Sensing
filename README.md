# Sentinel-2 Beijing Remote Sensing

A reproducible Sentinel-2 L2A remote-sensing data pipeline for a Beijing
study area. The project uses Earth Search STAC and public Sentinel-2 COG
assets, Rasterio/GDAL for raster processing, and Python for spectral-index
calculation.

The pipeline supports:

- STAC catalog search and Sentinel-2 scene selection
- COG asset download and AOI cropping
- Multispectral band alignment and BOA reflectance conversion
- SCL-based cloud and invalid-pixel masking
- NDVI and NDWI calculation
- Raster alignment checks, processing reports, and automated tests

The project has been developed and tested in a Linux ARM64 (aarch64)
environment.

## Study area and configuration

The example configuration is:

`configs/beijing_2021_summer.json`

| Parameter | Value |
|---|---|
| STAC catalog | https://earth-search.aws.element84.com/v1 |
| Collection | sentinel-2-l2a |
| AOI (WGS84) | 116.25, 39.80, 116.50, 40.05 |
| Date range | 2021-06-01 to 2021-09-30 |
| Maximum cloud cover | 20% |
| Output CRS | EPSG:32650 |
| Reflectance output resolution | 10 m |
| Valid SCL classes | 4, 5, 6 |
| Example item | S2B_50TMK_20210601_1_L2A |

The configuration can be copied and modified for another study area or
time range.

## Environment

Activate the Conda environment containing Python, Rasterio, GDAL,
PySTAC Client, NumPy, and the other project dependencies:

```bash
conda activate gis-core


The development environment used for testing includes Python 3.12 on
Linux aarch64.
Project structure
Sentinel2-Beijing-Remote-Sensing/
├── configs/
│   └── beijing_2021_summer.json
├── data/
│   └── README.md
├── scripts/
│   ├── download_sentinel2.py
│   ├── preprocess.py
│   ├── calculate_indices.py
│   ├── inspect_real_metadata.py
│   └── search_sentinel2.py
├── src/
│   ├── stac_utils.py
│   ├── indices.py
│   └── sentinel2_metadata.py
├── tests/
│   ├── test_indices.py
│   ├── test_pipeline_integration.py
│   ├── test_preprocess_radiometry.py
│   ├── test_raster_alignment.py
│   └── test_sentinel2_metadata.py
└── README.md


search_sentinel2.py is a legacy Copernicus STAC search script.
The Earth Search workflow documented below uses download_sentinel2.py.
Workflow
Run commands from the repository root. The examples below use the
example Sentinel-2 item configured in the JSON file.
1. Search and download Sentinel-2 COG assets
python -m scripts.download_sentinel2


Optional arguments:
python -m scripts.download_sentinel2 --help


To force a new download and overwrite existing files:
python -m scripts.download_sentinel2 --overwrite


The default raw-data directory is:
data/raw/sentinel2/S2B_50TMK_20210601_1_L2A/
├── B02.tif
├── B03.tif
├── B04.tif
├── B08.tif
├── SCL.tif
└── item_metadata.json


The four reflectance bands are retained on their source 10 m grid.
SCL is retained at its native 20 m resolution in the raw-data directory.
2. Preprocess and align the bands
python -m scripts.preprocess \
    --raw-dir data/raw/sentinel2/S2B_50TMK_20210601_1_L2A \
    --output-dir data/processed/S2B_50TMK_20210601_1_L2A


The preprocessing stage:
- Uses B04 as the 10 m reference grid.
- Checks and aligns B02, B03, B04, and B08.
- Reads radiometric scale and offset information from STAC asset metadata.
- Converts raw digital numbers to BOA reflectance using the metadata
  transformation reflectance = DN * scale + offset.
- Treats DN = 0 as NoData.
- Resamples SCL to the 10 m grid using nearest-neighbour resampling.
- Writes a preprocessing report.
Expected processed files include:
data/processed/S2B_50TMK_20210601_1_L2A/
├── B02.tif
├── B03.tif
├── B04.tif
├── B08.tif
├── SCL_10m.tif
└── preprocess_report.json


3. Calculate NDVI and NDWI
python -m scripts.calculate_indices \
    --input-dir data/processed/S2B_50TMK_20210601_1_L2A \
    --output-dir outputs/indices


The index calculations are:

NDVI (Normalized Difference Vegetation Index)

NDVI = (B08 - B04) / (B08 + B04)

NDWI (McFeeters Normalized Difference Water Index)

NDWI = (B03 - B08) / (B03 + B08)

This project uses the McFeeters green-NIR NDWI definition. It should
not be confused with the Gao NIR-SWIR water index.

The calculation stage uses SCL classes 4, 5, and 6 as valid classes,
together with raster masks and finite-value checks. Invalid pixels and
zero-denominator pixels are written as NoData.

Expected outputs:
outputs/indices/
├── NDVI.tif
├── NDWI.tif
└── indices_report.json


4. Run automated tests
The test suite uses synthetic rasters and does not require downloading
satellite data:
python -m compileall -q src scripts tests
python -m pytest tests/ -v
git diff --check


Processing and data-quality principles
- Consistent grids: raster calculations require matching CRS,
  affine transform, width, height, and pixel resolution.
- Radiometric correctness: scale and offset are read from STAC
  raster-band metadata and applied once during preprocessing.
- Categorical resampling: SCL uses nearest-neighbour resampling;
  continuous reflectance bands use bilinear resampling when alignment
  is required.
- NoData handling: invalid pixels and zero denominators are not
  treated as valid observations. The configured output NoData value
  is -9999.
- Reproducibility: processing parameters are stored in JSON
  configuration and output reports.
Data source and attribution
The example workflow accesses Sentinel-2 L2A assets through the
Element 84 Earth Search STAC catalog:

https://earth-search.aws.element84.com/v1

The imagery is Sentinel-2 data. Users should consult the applicable
Copernicus Sentinel data terms and attribution requirements before
redistributing source imagery or derived products.

See data/README.md for data layout and processing notes.
Limitations and validation status
The automated tests cover index calculations, raster alignment,
radiometric conversion, metadata parsing, and a synthetic end-to-end
preprocessing/index-calculation chain.

A successful synthetic test does not by itself establish that a
real-world Sentinel-2 scene has completed the entire download and
processing workflow. Real-data validation should be performed in an
environment with access to the Earth Search catalog and COG assets.

Large raw and processed rasters and generated outputs are excluded
from Git. They can be regenerated from the public data source and
project configuration.
