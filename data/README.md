# Data Directory

Raw satellite data are not committed to Git.

See `.gitignore`.

## Data Sources

| Dataset | Source | Intended use |
|---|---|---|
| Sentinel-2 L2A BOA reflectance | Copernicus Data Space Ecosystem | Multispectral imagery |
| ESA WorldCover 2021 v200 | ESA WorldCover | Optional land-cover reference |
| Geofabrik Beijing OSM | Geofabrik | Optional study-area reference |

## Expected Local Layout

```text
data/
├── raw/
│   ├── sentinel2_2021/
│   │   ├── MTD_MSIL2A.xml
│   │   ├── B02.tif
│   │   ├── B03.tif
│   │   ├── B04.tif
│   │   ├── B08.tif
│   │   └── SCL.tif
│   └── study_area.gpkg
└── processed/
    ├── B02_aligned.tif
    ├── B03_aligned.tif
    ├── B04_aligned.tif
    ├── B08_aligned.tif
    └── SCL_aligned.tif


Input Data Requirements
The four spectral-band TIFF files must contain raw Sentinel-2
L2A digital numbers (DN) from the same product and acquisition.

The MTD_MSIL2A.xml file must belong to that same product.

Do not use this DN conversion workflow on imagery that has already
been converted to physical reflectance by another service.
Radiometric Conversion
For Sentinel-2 L2A products:

BOA reflectance = (DN + BOA_ADD_OFFSET) / QUANTIFICATION_VALUE

The processing script reads the quantification value, processing
baseline, and band-specific BOA offsets from product metadata.

DN = 0 remains NoData.

For processing baselines earlier than 04.00, absent BOA offsets
are treated as zero. For baseline 04.00 and later, required
band offsets must be present in the XML.
Spatial Processing
The project uses EPSG:32650 and a common 10 m output grid.

B04 establishes the reference grid.

B02, B03, B08 are resampled to that exact grid using bilinear
resampling.

SCL is resampled using nearest-neighbour interpolation because
it contains categorical class codes.
Outputs
The following files are Float32 BOA reflectance:
- B02_aligned.tif
- B03_aligned.tif
- B04_aligned.tif
- B08_aligned.tif
SCL_aligned.tif retains categorical values and uses 0 as NoData.

Large raw and processed raster files are excluded from Git.
Data Licensing and Attribution
Consult the official Copernicus Data Space Ecosystem terms and
the applicable Sentinel data legal notice before redistribution.

Copernicus Sentinel data attribution should be retained when
publishing results.

Official data access:

https://dataspace.copernicus.eu/

Sentinel-2 processing documentation:

https://sentiwiki.copernicus.eu/web/s2-processing
