import numpy as np
import rasterio

from rasterio.transform import from_origin

from scripts.preprocess import write_reflectance
from src.indices import NODATA


def test_write_reflectance_applies_boa_offset(tmp_path):
    source = tmp_path / "B04_dn.tif"
    output = tmp_path / "B04_reflectance.tif"

    dn = np.array(
        [
            [0, 500, 1000],
            [3000, 5000, 10000],
        ],
        dtype=np.uint16,
    )

    profile = {
        "driver": "GTiff",
        "width": 3,
        "height": 2,
        "count": 1,
        "dtype": "uint16",
        "crs": "EPSG:32650",
        "transform": from_origin(
            400000,
            4400000,
            10,
            10,
        ),
        "nodata": 0,
    }

    with rasterio.open(source, "w", **profile) as dst:
        dst.write(dn, 1)

    write_reflectance(
        source,
        output,
        offset=-1000,
        quantification_value=10000,
    )

    with rasterio.open(output) as src:
        result = src.read(1)

        assert src.dtypes[0] == "float32"
        assert src.nodata == NODATA
        assert src.crs.to_epsg() == 32650
        assert src.transform == profile["transform"]

    expected = np.array(
        [
            [NODATA, -0.05, 0.0],
            [0.2, 0.4, 0.9],
        ],
        dtype=np.float32,
    )

    np.testing.assert_allclose(
        result,
        expected,
        rtol=1e-6,
        atol=1e-7,
    )


def test_zero_dn_remains_nodata(tmp_path):
    source = tmp_path / "zero_dn.tif"
    output = tmp_path / "zero_reflectance.tif"

    profile = {
        "driver": "GTiff",
        "width": 2,
        "height": 2,
        "count": 1,
        "dtype": "uint16",
        "crs": "EPSG:32650",
        "transform": from_origin(
            400000,
            4400000,
            10,
            10,
        ),
        "nodata": 0,
    }

    with rasterio.open(source, "w", **profile) as dst:
        dst.write(
            np.zeros((2, 2), dtype=np.uint16),
            1,
        )

    write_reflectance(
        source,
        output,
        offset=-1000,
        quantification_value=10000,
    )

    with rasterio.open(output) as src:
        result = src.read(1)

    assert (result == NODATA).all()
