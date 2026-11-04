# Data directory

Raw satellite data is **not** committed to git (see `.gitignore`).

## Sources

| Dataset | URL | Licence | Use |
|---|---|---|---|
| Sentinel-2 L2A (SR) | https://dataspace.copernicus.eu | ESA free licence | multispectral imagery |
| ESA WorldCover 2021 v200 | https://esa-worldcover.org | CC-BY 4.0 | land cover reference labels |
| Geofabrik Beijing OSM | https://download.geofabrik.de/asia/china/beijing.html | ODbL | study area / buildings |

## Expected layout after download

```
data/
├── raw/
│   ├── sentinel2_2021/
│   │   ├── B02.tif  B03.tif  B04.tif  B08.tif  B11.tif  SCL.tif
│   └── study_area.gpkg
└── processed/
    ├── B02_aligned.tif ... B08_aligned.tif
```

## Notes

- Sentinel-2 L2A surface reflectance is the recommended processing level for
  index computation (baseline 04.00, scale factor 10000).
- STAC search results (metadata only) are stored in `outputs/`.
- Asset URLs from the Copernicus STAC API may require registration; check
  `scripts/search_sentinel2.py` output before assuming anonymous download.
