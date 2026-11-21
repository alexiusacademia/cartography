"""Checks cartography's raster writers with GDAL: runs the Tessel program
tools/oracle/raster_writes (which writes GeoTIFFs of every packing and type,
an ASCII grid, and GeoTIFFs in a CRS without an EPSG code and in degrees),
then reads each file with rasterio and compares it with the source fixture
as GDAL reads it: size, geotransform, CRS, no-data and every value.

Run from the library's folder (named `cartography`):
    .venv/bin/python tools/oracle/raster_check_writes.py [library folder]

Author: Alexius Academia
Date: 2026-11-22
"""

import os
import subprocess
import sys
import tempfile

import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.warp import transform as warp_transform

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA = os.path.join(ROOT, "tests", "data", "raster")

failures = 0
checks = 0


def check(ok, what):
    global failures, checks
    checks += 1
    if not ok:
        failures += 1
        print("FAIL", what)


def masked(d, b):
    a = d.read(b).astype("float64")
    if d.nodata is not None and not np.isnan(d.nodata):
        a[a == d.nodata] = np.nan
    return a


def compare(written, source, what, convert=None, crs_by_points=False):
    with rasterio.open(written) as w, rasterio.open(source) as s:
        check(w.width == s.width and w.height == s.height, f"{what}: size")
        check(w.count == s.count, f"{what}: bands")
        check(np.allclose(tuple(w.transform)[:6], tuple(s.transform)[:6], rtol=0, atol=1e-9), f"{what}: transform {w.transform} vs {s.transform}")
        if crs_by_points:
            # No EPSG code: the same places in lon/lat.
            xs = [s.bounds.left, s.bounds.right, (s.bounds.left + s.bounds.right) / 2]
            ys = [s.bounds.bottom, s.bounds.top, (s.bounds.bottom + s.bounds.top) / 2]
            a = warp_transform(w.crs, CRS.from_epsg(4326), xs, ys)
            b = warp_transform(s.crs, CRS.from_epsg(4326), xs, ys)
            check(np.allclose(a, b, atol=1e-7), f"{what}: CRS {w.crs} vs {s.crs}")
        else:
            check(w.crs.to_epsg() == s.crs.to_epsg(), f"{what}: CRS {w.crs} vs {s.crs}")
        for b in range(1, s.count + 1):
            got = masked(w, b)
            want = masked(s, b)
            if convert:
                want = convert(want)
            same = np.array_equal(np.isnan(got), np.isnan(want)) and np.allclose(got[~np.isnan(got)], want[~np.isnan(want)], rtol=0, atol=0)
            check(same, f"{what}: band {b} values")


def main():
    out = tempfile.mkdtemp(prefix="cartography-writes-")
    subprocess.run(["tessel", "run", "tools/oracle/raster_writes", out], cwd=ROOT, check=True)
    for how in ["deflate", "lzw", "none"]:
        compare(os.path.join(out, f"dem_float32_{how}.tif"), os.path.join(DATA, "dem_holes.tif"), f"float32 {how}")
        compare(os.path.join(out, f"dem_float64_{how}.tif"), os.path.join(DATA, "dem_holes.tif"), f"float64 {how}")
        compare(os.path.join(out, f"rgb_uint8_{how}.tif"), os.path.join(DATA, "rgb_pixel_lzw.tif"), f"uint8 {how}")
    ranges = {"int16": (-32768, 32767), "uint16": (0, 65535), "int32": (-2**31, 2**31 - 1), "uint32": (0, 2**32 - 1)}
    for t, (lo, hi) in ranges.items():
        compare(os.path.join(out, f"i16_{t}.tif"), os.path.join(DATA, "i16_nodata.tif"), t,
                convert=lambda a, lo=lo, hi=hi: np.where(np.isnan(a), np.nan, np.clip(np.round(a), lo, hi)))
    compare(os.path.join(out, "lcc.tif"), os.path.join(DATA, "crs_custom_lcc.tif"), "CRS without a code", crs_by_points=True)
    compare(os.path.join(out, "lonlat.tif"), os.path.join(DATA, "dem_4326.tif"), "EPSG:4326")
    compare(os.path.join(out, "dem.asc"), os.path.join(DATA, "dem_holes.tif"), "ASCII grid", crs_by_points=True)
    print(f"{checks - failures} of {checks} checks passed")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
