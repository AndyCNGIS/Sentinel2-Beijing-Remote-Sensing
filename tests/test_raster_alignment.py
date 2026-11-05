import pytest
import rasterio

from rasterio.transform import from_origin

from scripts.calculate_indices import assert_same_grid


def make_profile(
    crs="EPSG:32650",
    x_origin=400000,
    y_origin=4400000,
):
    return {
        "crs": rasterio.crs.CRS.from_string(crs),
        "width": 100,
        "height": 100,
        "transform": from_origin(
            x_origin,
            y_origin,
            10,
            10,
        ),
        "res": (10.0, 10.0),
    }


def test_identical_grid_passes():
    reference = make_profile()
    current = make_profile()

    assert_same_grid(
        reference,
        current,
        "test-band",
    )


def test_shifted_transform_fails():
    reference = make_profile()
    shifted = make_profile(
        x_origin=400005,
    )

    with pytest.raises(
        ValueError,
        match="affine transform mismatch",
    ):
        assert_same_grid(
            reference,
            shifted,
            "shifted-band",
        )


def test_different_crs_fails():
    reference = make_profile()
    different_crs = make_profile(
        crs="EPSG:32649",
    )

    with pytest.raises(
        ValueError,
        match="CRS mismatch",
    ):
        assert_same_grid(
            reference,
            different_crs,
            "different-crs-band",
        )


def test_different_dimensions_fail():
    reference = make_profile()
    different = make_profile()
    different["width"] = 101

    with pytest.raises(
        ValueError,
        match="width mismatch",
    ):
        assert_same_grid(
            reference,
            different,
            "different-width-band",
        )
