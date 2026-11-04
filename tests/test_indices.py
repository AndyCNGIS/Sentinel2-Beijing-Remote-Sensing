"""Offline unit tests for spectral index computation.

These tests use synthetic numpy arrays and in-memory rasters so they run
without any satellite download - the pipeline logic is verified even on a
network-isolated ARM64 server.
"""
import sys
from pathlib import Path

import numpy as np
import pytest
import rasterio

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.indices import ndvi, ndwi, scl_cloud_mask, NODATA  # noqa: E402


def make_bands(shape=(64, 64), seed=42):
    """Synthetic 16-bit reflectance-like bands scaled to [0, 1]."""
    rng = np.random.default_rng(seed)
    red = rng.uniform(0.0, 0.6, shape).astype(np.float32)
    nir = rng.uniform(0.1, 0.9, shape).astype(np.float32)
    green = rng.uniform(0.0, 0.7, shape).astype(np.float32)
    valid = np.ones(shape, dtype=bool)
    return red, nir, green, valid


class TestNdviNdwi:
    def test_values_in_range(self):
        red, nir, green, valid = make_bands()
        for arr in (ndvi(nir, red, valid), ndwi(green, nir, valid)):
            ok = arr != NODATA
            assert ok.all()
            assert arr[ok].min() >= -1.0
            assert arr[ok].max() <= 1.0

    def test_known_pixel(self):
        # Dense vegetation: NIR high, red low -> NDVI close to +1
        red = np.array([[0.1]], dtype=np.float32)
        nir = np.array([[0.8]], dtype=np.float32)
        v = np.array([[True]])
        assert ndvi(nir, red, v)[0, 0] == pytest.approx(0.7 / 0.9, abs=1e-6)
        # Open water: green high, NIR low -> NDWI close to +1
        green = np.array([[0.6]], dtype=np.float32)
        assert ndwi(green, nir, v)[0, 0] == pytest.approx(-0.2 / 1.4, abs=1e-6)

    def test_zero_denominator_is_nodata(self):
        red = np.array([[0.0]], dtype=np.float32)
        nir = np.array([[0.0]], dtype=np.float32)
        v = np.array([[True]])
        assert ndvi(nir, red, v)[0, 0] == NODATA

    def test_invalid_pixels_are_nodata(self):
        red, nir, green, _ = make_bands()
        valid = np.zeros_like(red, dtype=bool)
        arr = ndvi(nir, red, valid)
        assert (arr == NODATA).all()

    def test_real_tif_roundtrip(self, tmp_path):
        """Write synthetic bands to GeoTIFF, re-read, compute NDVI, write out,
        and validate the written index in [-1, 1] with correct profile."""
        red, nir, green, valid = make_bands(shape=(32, 32))
        profile = {
            "driver": "GTiff", "width": 32, "height": 32, "count": 1,
            "dtype": "float32", "crs": "EPSG:32650",
            "transform": rasterio.Affine(10, 0, 400000, 0, -10, 4400000),
            "nodata": NODATA,
        }
        out = tmp_path / "ndvi.tif"
        with rasterio.open(out, "w", **profile) as dst:
            dst.write(ndvi(nir, red, valid), 1)
        with rasterio.open(out) as src:
            arr = src.read(1)
            assert str(src.crs) == "EPSG:32650"
            assert src.res == (10.0, 10.0)
        ok = arr != NODATA
        assert ok.all()
        assert arr.min() >= -1.0 and arr.max() <= 1.0


class TestCloudMask:
    def test_valid_classes_kept(self):
        scl = np.array([[4, 5, 6, 7]])
        assert scl_cloud_mask(scl).all()

    def test_cloud_classes_removed(self):
        scl = np.array([[0, 3, 8, 9, 10, 11]])
        assert not scl_cloud_mask(scl).any()
