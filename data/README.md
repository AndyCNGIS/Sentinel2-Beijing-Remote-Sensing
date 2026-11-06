# Data Directory

This directory stores local Sentinel-2 source data and processed rasters.

Large raster files are excluded from Git. See the repository-level
`.gitignore`.

## Data source

The primary workflow uses Sentinel-2 L2A assets from the Element 84
Earth Search STAC catalog:

https://earth-search.aws.element84.com/v1

STAC collection:

`sentinel-2-l2a`

The example AOI, time range, item selection, and processing parameters
are defined in:

`configs/beijing_2021_summer.json`

## Raw data layout

After running `python -m scripts.download_sentinel2`, the default
directory layout is:

```text
data/
└── raw/
    └── sentinel2/
        └── S2B_50TMK_20210601_1_L2A/
            ├── B02.tif
            ├── B03.tif
            ├── B04.tif
            ├── B08.tif
            ├── SCL.tif
            └── item_metadata.json


B02, B03, B04, and B08 are reflectance-band source assets.
SCL is the Scene Classification Layer and remains at its native
20 m resolution in the raw directory.

item_metadata.json records the selected STAC item and relevant
asset metadata, including the radiometric information used by
preprocessing.

An original Sentinel-2 product XML file is not required by the
Earth Search COG workflow.
Radiometric conversion
The preprocessing stage reads the scale and offset values from
STAC raster-band metadata.

The conversion is:

BOA reflectance = DN * scale + offset

The values must be applied once. Do not apply the transformation
again to data that has already been converted to physical reflectance.

DN = 0 is treated as NoData for the reflectance bands.
Processed data layout
After running python -m scripts.preprocess, the expected layout is:
data/
└── processed/
    └── S2B_50TMK_20210601_1_L2A/
        ├── B02.tif
        ├── B03.tif
        ├── B04.tif
        ├── B08.tif
        ├── SCL_10m.tif
        └── preprocess_report.json


The reflectance bands are Float32 and share a common 10 m grid.
The configured output CRS is EPSG:32650.

B04 defines the reference grid. Other reflectance bands are aligned
to this grid when necessary. Continuous reflectance data use
bilinear resampling when resampling is required.

SCL is resampled to the 10 m reference grid using nearest-neighbour
resampling because its values represent categorical classes, not
continuous measurements.
Index outputs
The index-calculation script writes generated results under outputs/
by default or to the directory specified by --output-dir.

Typical files include:
- NDVI.tif
- NDWI.tif
- indices_report.json
NDVI uses B08 and B04. NDWI uses the McFeeters green-NIR definition,
using B03 and B08.

The configured valid SCL classes are 4, 5, and 6.
Invalid pixels are written with the configured NoData value.
Data licensing and attribution
The source imagery is Sentinel-2 data accessed through Earth Search.
Consult the applicable Copernicus Sentinel data legal notice and
terms before redistributing source data or derived products.

Official Sentinel data information:

https://sentiwiki.copernicus.eu/web/s2-processing

Earth Search STAC catalog:

https://earth-search.aws.element84.com/v1
