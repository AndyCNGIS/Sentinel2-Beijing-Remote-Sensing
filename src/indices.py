# Reusable, NoData-safe spectral index computation.
#
# NDVI = (NIR - Red)  / (NIR + Red)   -> vegetation vigour
# NDWI = (Green - NIR) / (Green + NIR) -> open water (McFeeters 1996)
#
# All functions accept numpy arrays plus a validity mask, so they can be unit
# tested with synthetic data without any real satellite download.
import numpy as np

NODATA = -9999.0


def _safe_ratio(a: np.ndarray, b: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """(a - b) / (a + b) with divide-by-zero and NoData protection."""
    denom = a + b
    ok = valid & np.isfinite(a) & np.isfinite(b) & (denom != 0)
    out = np.full(np.broadcast(a, b).shape, NODATA, dtype=np.float32)
    np.divide(a - b, denom, out=out, where=ok)
    out[~ok] = NODATA
    return out


def ndvi(nir: np.ndarray, red: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """Normalised Difference Vegetation Index, NoData-safe."""
    return _safe_ratio(nir.astype(np.float32), red.astype(np.float32), valid)


def ndwi(green: np.ndarray, nir: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """Normalised Difference Water Index (McFeeters), NoData-safe."""
    return _safe_ratio(green.astype(np.float32), nir.astype(np.float32), valid)


def scl_cloud_mask(scl: np.ndarray) -> np.ndarray:
    """Return a boolean mask of *valid* (non-cloud) pixels from a Sentinel-2
    L2A Scene Classification Layer (SCL) band.

    SCL codes treated as invalid: 0 (no data), 1 (saturated), 2 (dark), 3
    (cloud shadow), 8 (cloud medium prob.), 9 (cloud high prob.), 10 (thin
    cirrus), 11 (snow).
    """
    scl = np.asarray(scl)
    return ~np.isin(scl, [0, 1, 2, 3, 8, 9, 10, 11])
