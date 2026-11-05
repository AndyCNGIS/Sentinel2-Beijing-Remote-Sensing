"""NoData-safe Sentinel-2 spectral index computation."""

import numpy as np

NODATA = -9999.0

# Conservative SCL policy:
# 4 = vegetation
# 5 = not vegetated
# 6 = water
#
# Classes 0, 1, 2, 3, 7, 8, 9, 10, 11 are excluded.
# Class 2 and class 7 are excluded as a quality-control decision.
VALID_SCL_CLASSES = (4, 5, 6)


def _safe_ratio(
    a: np.ndarray,
    b: np.ndarray,
    valid: np.ndarray,
) -> np.ndarray:
    """Compute (a-b)/(a+b) with NoData and physical-range checks."""
    a = np.asarray(a, dtype=np.float32)
    b = np.asarray(b, dtype=np.float32)
    valid = np.asarray(valid, dtype=bool)

    try:
        a, b, valid = np.broadcast_arrays(a, b, valid)
    except ValueError as exc:
        raise ValueError(
            "Input bands and validity mask are not broadcast-compatible"
        ) from exc

    denominator = a + b

    out = np.full(
        a.shape,
        NODATA,
        dtype=np.float32,
    )

    # Negative BOA reflectance can be valid in Sentinel-2 L2A.
    # Therefore, do not require denominator > 0 and do not
    # automatically discard index values outside [-1, 1].
    #
    # A near-zero denominator is numerically unstable and is
    # treated as NoData.
    denominator_epsilon = 1e-6

    good = (
        valid
        & np.isfinite(a)
        & np.isfinite(b)
        & np.isfinite(denominator)
        & (np.abs(denominator) > denominator_epsilon)
    )

    with np.errstate(
        divide="ignore",
        invalid="ignore",
        over="ignore",
    ):
        np.divide(
            a - b,
            denominator,
            out=out,
            where=good,
        )

    good &= np.isfinite(out)
    out[~good] = NODATA

    return out


def ndvi(
    nir: np.ndarray,
    red: np.ndarray,
    valid: np.ndarray,
) -> np.ndarray:
    """Normalized Difference Vegetation Index.

    NDVI = (NIR - Red) / (NIR + Red)

    Inputs must be reflectance values, not uncorrected DN.
    """
    return _safe_ratio(nir, red, valid)


def ndwi(
    green: np.ndarray,
    nir: np.ndarray,
    valid: np.ndarray,
) -> np.ndarray:
    """McFeeters Normalized Difference Water Index.

    NDWI = (Green - NIR) / (Green + NIR)

    This is the McFeeters definition, not the Gao vegetation-water index.

    Inputs must be reflectance values, not uncorrected DN.
    """
    return _safe_ratio(green, nir, valid)


def scl_cloud_mask(scl: np.ndarray) -> np.ndarray:
    """Return a conservative valid-pixel mask from Sentinel-2 L2A SCL.

    Retained classes:
        4: Vegetation
        5: Not vegetated
        6: Water

    Excluded classes:
        0: No data
        1: Saturated or defective
        2: Dark area / cast-shadow class
        3: Cloud shadows
        7: Unclassified
        8: Cloud medium probability
        9: Cloud high probability
        10: Thin cirrus
        11: Snow or ice

    This is a project quality-control policy, not a claim that
    every excluded pixel is cloud.
    """
    scl = np.asarray(scl)

    return np.isin(scl, VALID_SCL_CLASSES)
