"""Offline tests for Sentinel-2 spectral indices and SCL masking."""

import sys
from pathlib import Path

import numpy as np
import pytest
import rasterio

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.indices import (  # noqa: E402
    NODATA,
    ndvi,
    ndwi,
    scl_cloud_mask,
)


def make_bands(shape=(64, 64), seed=42):
    rng = np.random.default_rng(seed)

    red = rng.uniform(0.0, 0.6, shape).astype(np.float32)
    nir = rng.uniform(0.1, 0.9, shape).astype(np.float32)
    green = rng.uniform(0.0, 0.7, shape).astype(np.float32)

    valid = np.ones(shape, dtype=bool)

    return red, nir, green, valid


class TestNdviNdwi:

    def test_values_in_range(self):
        red, nir, green, valid = make_bands()

        for arr in (
            ndvi(nir, red, valid),
            ndwi(green, nir, valid),
        ):
            ok = arr != NODATA

            assert ok.any()
            assert arr[ok].min() >= -1.0
            assert arr[ok].max() <= 1.0

    def test_known_pixel(self):
        # Vegetation: NIR higher than red.
        red = np.array([[0.1]], dtype=np.float32)
        nir = np.array([[0.8]], dtype=np.float32)
        valid = np.array([[True]])

        result = ndvi(nir, red, valid)

        assert result[0, 0] == pytest.approx(
            0.7 / 0.9,
            abs=1e-6,
        )

        # Water example for McFeeters NDWI:
        # green higher than NIR.
        green = np.array([[0.8]], dtype=np.float32)
        nir_water = np.array([[0.1]], dtype=np.float32)

        result = ndwi(green, nir_water, valid)

        assert result[0, 0] == pytest.approx(
            0.7 / 0.9,
            abs=1e-6,
        )

    def test_zero_denominator_is_nodata(self):
        zero = np.array([[0.0]], dtype=np.float32)
        valid = np.array([[True]])

        result = ndvi(zero, zero, valid)

        assert result[0, 0] == NODATA

    def test_invalid_pixels_are_nodata(self):
        red, nir, _, _ = make_bands()

        valid = np.zeros_like(red, dtype=bool)

        result = ndvi(nir, red, valid)

        assert (result == NODATA).all()

    def test_nonfinite_inputs_and_negative_reflectance(self):
        # NaN must be NoData.
        # Negative BOA reflectance must not be discarded merely
        # because the resulting index can exceed [-1, 1].
        a = np.array(
            [[np.nan, -0.2, 0.5]],
            dtype=np.float32,
        )

        b = np.array(
            [[0.3, 0.1, -0.1]],
            dtype=np.float32,
        )

        valid = np.ones_like(a, dtype=bool)

        result = ndvi(a, b, valid)

        assert result[0, 0] == NODATA

        # (-0.2 - 0.1) / (-0.2 + 0.1) = 3.0
        assert result[0, 1] == pytest.approx(3.0)

        # (0.5 - (-0.1)) / (0.5 + (-0.1)) = 1.5
        assert result[0, 2] == pytest.approx(1.5)

    def test_real_tif_roundtrip(self, tmp_path):
        red, nir, _, valid = make_bands(shape=(32, 32))

        profile = {
            "driver": "GTiff",
            "width": 32,
            "height": 32,
            "count": 1,
            "dtype": "float32",
            "crs": "EPSG:32650",
            "transform": rasterio.Affine(
                10, 0, 400000,
                0, -10, 4400000,
            ),
            "nodata": NODATA,
        }

        out = tmp_path / "ndvi.tif"

        with rasterio.open(out, "w", **profile) as dst:
            dst.write(ndvi(nir, red, valid), 1)

        with rasterio.open(out) as src:
            arr = src.read(1)

            assert str(src.crs) == "EPSG:32650"
            assert src.res == (10.0, 10.0)
            assert src.nodata == NODATA

        good = arr != NODATA

        assert good.any()
        assert arr[good].min() >= -1.0
        assert arr[good].max() <= 1.0


class TestCloudMask:

    def test_only_expected_classes_are_kept(self):
        scl = np.array([[4, 5, 6]], dtype=np.uint8)

        assert scl_cloud_mask(scl).all()

    def test_invalid_and_unclassified_classes_are_removed(self):
        scl = np.array(
            [[0, 1, 2, 3, 7, 8, 9, 10, 11]],
            dtype=np.uint8,
        )

        assert not scl_cloud_mask(scl).any()


def test_near_zero_denominator_is_nodata():
    nir = np.array([[0.5]], dtype=np.float32)
    red = np.array([[-0.4999995]], dtype=np.float32)
    valid = np.array([[True]])

    result = ndvi(nir, red, valid)

    assert result[0, 0] == NODATA
