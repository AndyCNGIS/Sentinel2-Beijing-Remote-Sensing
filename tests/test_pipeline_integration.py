"""Offline integration tests for the Sentinel-2 processing pipeline."""

import json
import sys
from pathlib import Path

import numpy as np
import pytest
import rasterio

from rasterio.transform import from_origin

from scripts.download_sentinel2 import crop_window
from scripts.calculate_indices import check_alignment


def create_raster(
    path,
    array,
    transform,
    crs="EPSG:4326",
    nodata=None,
):
    path.parent.mkdir(parents=True, exist_ok=True)

    profile = {
        "driver": "GTiff",
        "height": array.shape[0],
        "width": array.shape[1],
        "count": 1,
        "dtype": array.dtype,
        "crs": crs,
        "transform": transform,
        "nodata": nodata,
    }

    with rasterio.open(path, "w", **profile) as dst:
        dst.write(array, 1)


def test_crop_window_inside_raster(tmp_path):
    """A bbox should produce a valid crop window."""
    path = tmp_path / "test.tif"

    array = np.arange(
        100,
        dtype=np.uint16,
    ).reshape(10, 10)

    transform = from_origin(
        0.0, 0.01, 0.001, 0.001
    )

    create_raster(path, array, transform)

    with rasterio.open(path) as src:
        window = crop_window(
            src,
            [0.002, 0.002, 0.008, 0.008],
        )

        assert window.width > 0
        assert window.height > 0
        assert window.col_off >= 0
        assert window.row_off >= 0
        assert window.col_off + window.width <= src.width
        assert window.row_off + window.height <= src.height


def test_crop_window_outside_raster(tmp_path):
    """A bbox outside the image should fail explicitly."""
    path = tmp_path / "test.tif"

    array = np.ones((10, 10), dtype=np.uint16)

    transform = from_origin(
        0.0, 0.01, 0.001, 0.001
    )

    create_raster(path, array, transform)

    with rasterio.open(path) as src:
        with pytest.raises(ValueError):
            crop_window(
                src,
                [1.0, 1.0, 2.0, 2.0],
            )


def test_alignment_accepts_identical_grids(tmp_path):
    """All input rasters on the same grid should pass."""
    transform = from_origin(
        0.0, 0.01, 0.001, 0.001
    )

    paths = {}

    for name in ("B02", "B03", "B04", "B08", "SCL_10m"):
        path = tmp_path / f"{name}.tif"
        create_raster(
            path,
            np.ones((10, 10), dtype=np.float32),
            transform,
            nodata=-9999.0,
        )
        paths[name] = path

    datasets = {
        name: rasterio.open(path)
        for name, path in paths.items()
    }

    try:
        check_alignment(datasets)
    finally:
        for src in datasets.values():
            src.close()


def test_alignment_rejects_transform_mismatch(tmp_path):
    """A half-pixel shift must be rejected."""
    paths = {}

    for name, x_origin in (
        ("B04", 0.0),
        ("B08", 0.0005),
    ):
        path = tmp_path / f"{name}.tif"

        create_raster(
            path,
            np.ones((10, 10), dtype=np.float32),
            from_origin(
                x_origin, 0.01, 0.001, 0.001
            ),
            nodata=-9999.0,
        )

        paths[name] = path

    datasets = {
        name: rasterio.open(path)
        for name, path in paths.items()
    }

    try:
        with pytest.raises(ValueError):
            check_alignment(datasets)
    finally:
        for src in datasets.values():
            src.close()


def test_real_preprocess_and_indices_chain(tmp_path, monkeypatch):
    """Run preprocess.py and calculate_indices.py on synthetic rasters."""
    from scripts import preprocess
    from scripts import calculate_indices

    raw_dir = tmp_path / "raw" / "synthetic_scene"
    output_dir = tmp_path / "processed" / "synthetic_scene"

    raw_dir.mkdir(parents=True)

    # 8 x 8 reference grid, 10m-like synthetic grid in EPSG:4326.
    transform = from_origin(
        0.0, 0.0008, 0.0001, 0.0001
    )

    # Constant DN values make expected reflectance easy to verify.
    dn_values = {
        "B02": 2000,
        "B03": 3000,
        "B04": 2000,
        "B08": 6000,
    }

    for band, value in dn_values.items():
        array = np.full(
            (8, 8),
            value,
            dtype=np.uint16,
        )

        # Add one NoData pixel.
        array[0, 0] = 0

        create_raster(
            raw_dir / f"{band}.tif",
            array,
            transform,
            nodata=0,
        )

    # SCL is 4 x 4 at twice the pixel size.
    scl_transform = from_origin(
        0.0, 0.0008, 0.0002, 0.0002
    )

    scl = np.full(
        (4, 4),
        5,
        dtype=np.uint8,
    )
    scl[0, 0] = 4
    scl[1, 1] = 6
    scl[2, 2] = 2
    scl[3, 3] = 7

    create_raster(
        raw_dir / "SCL.tif",
        scl,
        scl_transform,
        nodata=0,
    )

    band_metadata = {
        band: {
            "asset_key": band,
            "raster:bands": [{
                "nodata": 0,
                "data_type": "uint16",
                "scale": 0.0001,
                "offset": -0.1,
            }],
        }
        for band in ("B02", "B03", "B04", "B08")
    }

    band_metadata["SCL"] = {
        "asset_key": "scl",
        "raster:bands": [{
            "nodata": 0,
            "data_type": "uint8",
        }],
    }

    metadata = {
        "item_id": "synthetic_scene",
        "datetime": "2021-06-01T00:00:00Z",
        "project": {
            "bbox_wgs84": [
                0.0, 0.0, 0.0008, 0.0008
            ]
        },
        "assets": band_metadata,
    }

    (raw_dir / "item_metadata.json").write_text(
        json.dumps(metadata),
        encoding="utf-8",
    )

    config = {
        "nodata": -9999.0,
        "scl_valid_classes": [4, 5, 6],
        "denominator_epsilon": 1e-6,
    }

    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(config),
        encoding="utf-8",
    )

    # Execute the actual preprocessing entry point.
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "preprocess.py",
            "--raw-dir",
            str(raw_dir),
            "--output-dir",
            str(output_dir),
            "--config",
            str(config_path),
        ],
    )

    preprocess.main()

    for band in ("B02", "B03", "B04", "B08", "SCL_10m"):
        assert (output_dir / f"{band}.tif").exists()

    # Verify calibration: 2000 * 0.0001 - 0.1 = 0.1.
    with rasterio.open(output_dir / "B04.tif") as src:
        data = src.read(1)
        assert data[2, 2] == pytest.approx(0.1)
        assert data[0, 0] == -9999.0
        reference_transform = src.transform
        reference_crs = src.crs

    # Verify all outputs share the same grid.
    for band in ("B02", "B03", "B08", "SCL_10m"):
        with rasterio.open(output_dir / f"{band}.tif") as src:
            assert src.transform == reference_transform
            assert src.crs == reference_crs
            assert src.width == 8
            assert src.height == 8

    # Execute the actual index calculation entry point.
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "calculate_indices.py",
            "--input-dir",
            str(output_dir),
            "--output-dir",
            str(output_dir),
            "--config",
            str(config_path),
        ],
    )

    calculate_indices.main()

    for name in ("NDVI", "NDWI"):
        path = output_dir / f"{name}.tif"
        assert path.exists()

        with rasterio.open(path) as src:
            result = src.read(1)
            valid = src.read_masks(1) > 0

            assert src.crs == reference_crs
            assert src.transform == reference_transform
            assert np.isfinite(result[valid]).all()
            assert (result[valid] != -9999.0).all()

    # Expected reflectance:
    # B08 = 0.5, B04 = 0.1, B03 = 0.2
    # NDVI = (0.5 - 0.1) / (0.5 + 0.1) = 2/3
    # NDWI = (0.2 - 0.5) / (0.2 + 0.5) = -3/7

    with rasterio.open(output_dir / "NDVI.tif") as src:
        ndvi = src.read(1)
        assert ndvi[2, 2] == pytest.approx(2 / 3, abs=1e-5)

    with rasterio.open(output_dir / "NDWI.tif") as src:
        ndwi = src.read(1)
        assert ndwi[2, 2] == pytest.approx(-3 / 7, abs=1e-5)

    assert (output_dir / "preprocess_report.json").exists()
    assert (output_dir / "indices_report.json").exists()
