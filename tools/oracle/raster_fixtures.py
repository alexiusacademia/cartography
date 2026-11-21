"""Makes the raster fixtures of tests/raster.tsl with GDAL (through rasterio)
and writes what GDAL reads in them to tests/data/raster/expected.json.

GeoTIFFs of every kind cartography reads (types, compressions, predictors,
strips and tiles, byte orders, band layouts, CRSs, no-data, pixel-is-point),
an ASCII grid, a PNG with a world file, a DEM with what gdaldem makes of it
(hillshade, slope, aspect: run through GDAL's own C function
GDALDEMProcessing in rasterio's libgdal), and its contour levels from
contourpy (matplotlib's marching squares).

Run:  .venv/bin/python tools/oracle/raster_fixtures.py

Author: Alexius Academia
Date: 2026-11-22
"""

import ctypes
import glob
import json
import math
import os

import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.transform import from_origin
from rasterio.warp import transform as warp_transform

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "tests", "data", "raster")
os.makedirs(OUT, exist_ok=True)

W, H = 37, 23


def base(dtype, bands=1):
    """Deterministic values that fill the type's range somewhat."""
    j, i = np.mgrid[0:H, 0:W]
    out = []
    for b in range(bands):
        k = (i * 7 + j * 13 + b * 29) % 251
        if dtype == "uint8":
            a = k
        elif dtype == "int8":
            a = k - 125
        elif dtype == "uint16":
            a = k * 251 + i * 3
        elif dtype == "int16":
            a = (k - 125) * 200 + j
        elif dtype == "uint32":
            a = k * 16000000 + i * 1000 + j
        elif dtype == "int32":
            a = (k - 125) * 16000000 - i * 1000 + j
        else:
            a = np.sin(i / 5.0 + b) * 100.0 + np.cos(j / 3.0) * 37.25 + i * 0.125
        out.append(np.asarray(a).astype(dtype))
    return np.stack(out)


def gdal_lib():
    lib = ctypes.CDLL(glob.glob(os.path.join(rasterio.__path__[0], ".dylibs", "libgdal*"))[0])
    lib.GDALAllRegister()
    lib.GDALOpen.restype = ctypes.c_void_p
    lib.GDALOpen.argtypes = [ctypes.c_char_p, ctypes.c_int]
    lib.GDALDEMProcessingOptionsNew.restype = ctypes.c_void_p
    lib.GDALDEMProcessingOptionsNew.argtypes = [ctypes.POINTER(ctypes.c_char_p), ctypes.c_void_p]
    lib.GDALDEMProcessingOptionsFree.argtypes = [ctypes.c_void_p]
    lib.GDALDEMProcessing.restype = ctypes.c_void_p
    lib.GDALDEMProcessing.argtypes = [ctypes.c_char_p, ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p,
                                      ctypes.c_void_p, ctypes.POINTER(ctypes.c_int)]
    lib.GDALClose.argtypes = [ctypes.c_void_p]
    return lib


def gdaldem(lib, src, dst, what, args):
    """What `gdaldem what src dst args...` does."""
    words = [a.encode() for a in args] + [None]
    argv = (ctypes.c_char_p * len(words))(*words)
    opts = lib.GDALDEMProcessingOptionsNew(argv, None)
    ds = lib.GDALOpen(src.encode(), 0)
    err = ctypes.c_int(0)
    out = lib.GDALDEMProcessing(dst.encode(), ds, what.encode(), None, opts, ctypes.byref(err))
    assert out, f"gdaldem {what} failed"
    lib.GDALClose(out)
    lib.GDALClose(ds)
    lib.GDALDEMProcessingOptionsFree(opts)


def summary(path):
    """What GDAL reads in a file: size, place, CRS, no-data and checksums of
    every band (no-data cells left out)."""
    with rasterio.open(path) as d:
        t = d.transform
        bands = []
        for b in range(1, d.count + 1):
            a = d.read(b).astype("float64")
            if d.nodata is not None and not math.isnan(d.nodata):
                valid = a != d.nodata
            else:
                valid = ~np.isnan(a)
            idx = np.arange(a.size).reshape(a.shape)
            v = a[valid]
            bands.append({
                "count": int(valid.sum()),
                "sum": float(v.sum()),
                "weighted": float((v * ((idx[valid] % 97) + 1)).sum()),
                "low": float(v.min()) if v.size else 0.0,
                "high": float(v.max()) if v.size else 0.0,
                "first": [float(x) if valid.flat[k] else -1.0e300 for k, x in enumerate(a.flat[:6])],
            })
        epsg = d.crs.to_epsg() if d.crs else 0
        # Where the raster's center is in lon/lat, for CRSs without a code.
        cx = t.c + t.a * d.width / 2.0
        cy = t.f + t.e * d.height / 2.0
        lon, lat = warp_transform(d.crs, CRS.from_epsg(4326), [cx], [cy]) if d.crs else ([cx], [cy])
        return {
            "file": os.path.basename(path),
            "width": d.width,
            "height": d.height,
            "minX": t.c,
            "maxY": t.f,
            "cellX": t.a,
            "cellY": -t.e,
            "epsg": epsg or 0,
            "hasNoData": d.nodata is not None and not math.isnan(d.nodata),
            "noData": float(d.nodata) if d.nodata is not None and not math.isnan(d.nodata) else 0.0,
            "centerLon": lon[0],
            "centerLat": lat[0],
            "bands": bands,
        }


def write(name, data, crs="EPSG:32651", transform=None, nodata=None, **opts):
    path = os.path.join(OUT, name)
    count, h, w = data.shape
    if transform is None:
        transform = from_origin(500000.0, 1600000.0, 30.0, 30.0)
    with rasterio.open(path, "w", driver="GTiff", width=w, height=h, count=count, dtype=data.dtype.name,
                       crs=crs, transform=transform, nodata=nodata, **opts) as d:
        d.write(data)
    return path


def main():
    entries = []
    tiffs = [
        ("u8_none_strip.tif", "uint8", 1, dict(compress="none", blockysize=5)),
        ("u8_lzw_strip.tif", "uint8", 1, dict(compress="lzw", blockysize=4)),
        ("u8_lzw_pred2.tif", "uint8", 1, dict(compress="lzw", predictor=2)),
        ("u8_deflate_tile.tif", "uint8", 1, dict(compress="deflate", tiled=True, blockxsize=16, blockysize=16)),
        ("u8_packbits.tif", "uint8", 1, dict(compress="packbits", blockysize=7)),
        ("i8_deflate.tif", "int8", 1, dict(compress="deflate")),
        ("u16_lzw_pred2_tile.tif", "uint16", 1, dict(compress="lzw", predictor=2, tiled=True, blockxsize=16, blockysize=16)),
        ("u16_none_big.tif", "uint16", 1, dict(compress="none", endianness="BIG")),
        ("i16_deflate_pred2.tif", "int16", 1, dict(compress="deflate", predictor=2, blockysize=6)),
        ("i16_packbits.tif", "int16", 1, dict(compress="packbits")),
        ("i16_lzw_big_pred2.tif", "int16", 1, dict(compress="lzw", predictor=2, endianness="BIG")),
        ("u32_deflate.tif", "uint32", 1, dict(compress="deflate")),
        ("i32_lzw_pred2.tif", "int32", 1, dict(compress="lzw", predictor=2)),
        ("f32_none.tif", "float32", 1, dict(compress="none")),
        ("f32_lzw_pred3.tif", "float32", 1, dict(compress="lzw", predictor=3)),
        ("f32_deflate_pred3_tile.tif", "float32", 1, dict(compress="deflate", predictor=3, tiled=True, blockxsize=16, blockysize=16)),
        ("f32_deflate_pred2.tif", "float32", 1, dict(compress="deflate", predictor=2)),
        ("f32_lzw_big_pred3.tif", "float32", 1, dict(compress="lzw", predictor=3, endianness="BIG")),
        ("f32_packbits_tile.tif", "float32", 1, dict(compress="packbits", tiled=True, blockxsize=16, blockysize=16)),
        ("f64_deflate_pred3.tif", "float64", 1, dict(compress="deflate", predictor=3)),
        ("f64_none_tile.tif", "float64", 1, dict(compress="none", tiled=True, blockxsize=16, blockysize=16)),
        ("rgb_pixel_lzw.tif", "uint8", 3, dict(compress="lzw", interleave="pixel", photometric="RGB")),
        ("rgb_band_deflate_tile.tif", "uint8", 3, dict(compress="deflate", interleave="band", tiled=True, blockxsize=16, blockysize=16)),
        ("u16_4band_pred2.tif", "uint16", 4, dict(compress="deflate", predictor=2, interleave="pixel")),
        ("f32_2band_band_lzw.tif", "float32", 2, dict(compress="lzw", interleave="band", predictor=3)),
    ]
    for name, dtype, bands, opts in tiffs:
        entries.append(summary(write(name, base(dtype, bands), **opts)))

    # No-data, in a decimal and a whole number type.
    a = base("float32")
    a[0, 2:5, 3:9] = -9999.0
    entries.append(summary(write("f32_nodata.tif", a, nodata=-9999.0, compress="deflate")))
    b = base("int16")
    b[0, 10:12, :] = -32768
    entries.append(summary(write("i16_nodata.tif", b, nodata=-32768, compress="lzw")))
    c = base("float32")
    c[0, 5, 5:15] = np.nan
    entries.append(summary(write("f32_nan_nodata.tif", c, nodata=np.nan, compress="deflate")))

    # Coordinate systems.
    lonlat = from_origin(120.5, 15.25, 0.01, 0.01)
    entries.append(summary(write("crs_4326.tif", base("int16"), crs="EPSG:4326", transform=lonlat, compress="deflate")))
    entries.append(summary(write("crs_3857.tif", base("int16"), crs="EPSG:3857",
                                 transform=from_origin(13450000.0, 1700000.0, 100.0, 100.0), compress="deflate")))
    entries.append(summary(write("crs_3123.tif", base("int16"), crs="EPSG:3123",
                                 transform=from_origin(480000.0, 1650000.0, 25.0, 25.0), compress="deflate")))
    custom = CRS.from_proj4("+proj=tmerc +lat_0=0 +lon_0=125 +k=0.99995 +x_0=500000 +y_0=0 +ellps=clrk66 +units=m +no_defs")
    entries.append(summary(write("crs_custom_tmerc.tif", base("int16"), crs=custom,
                                 transform=from_origin(450000.0, 1400000.0, 50.0, 50.0), compress="deflate")))
    lcc = CRS.from_proj4("+proj=lcc +lat_1=12 +lat_2=18 +lat_0=10 +lon_0=122 +x_0=0 +y_0=0 +datum=WGS84 +units=m +no_defs")
    entries.append(summary(write("crs_custom_lcc.tif", base("int16"), crs=lcc,
                                 transform=from_origin(-20000.0, 400000.0, 100.0, 100.0), compress="deflate")))
    # Pixel is point: the tie point is a cell's center (GDAL shifts it).
    entries.append(summary(write("point_cells.tif", base("uint8"), compress="none", AREA_OR_POINT="Point")))

    # A DEM: smooth hills with a valley, 30 m cells in UTM 51N.
    j, i = np.mgrid[0:45, 0:60].astype("float64")
    dem = (400.0 + 180.0 * np.exp(-((i - 18) ** 2 + (j - 15) ** 2) / 120.0)
           + 120.0 * np.exp(-((i - 42) ** 2 + (j - 30) ** 2) / 80.0)
           - 60.0 * np.exp(-((i - 30) ** 2) / 30.0) + 1.5 * i - 0.8 * j)
    dem = dem.astype("float32")[None]
    demt = from_origin(500000.0, 1600000.0, 30.0, 30.0)
    dem_path = write("dem.tif", dem, transform=demt, compress="deflate", predictor=3)
    entries.append(summary(dem_path))
    holes = dem.copy()
    holes[0, 20:23, 25:29] = -9999.0
    holes_path = write("dem_holes.tif", holes, transform=demt, nodata=-9999.0, compress="deflate")
    entries.append(summary(holes_path))
    # A DEM in degrees (gdaldem is given the size of a degree, see below).
    dem_ll_path = write("dem_4326.tif", dem, crs="EPSG:4326", transform=from_origin(121.0, 15.0, 0.0003, 0.0003), compress="deflate")
    entries.append(summary(dem_ll_path))

    # The size of a degree on WGS84 at the DEM's middle latitude, for
    # gdaldem's -xscale and -yscale.
    a, f = 6378137.0, 1.0 / 298.257223563
    e2 = f * (2.0 - f)
    phi = math.radians(15.0 - 0.0003 * 22.5)
    q = 1.0 - e2 * math.sin(phi) ** 2
    xscale = a / math.sqrt(q) * math.cos(phi) * math.pi / 180.0
    yscale = a * (1.0 - e2) / (q * math.sqrt(q)) * math.pi / 180.0

    lib = gdal_lib()
    jobs = [
        (dem_path, "dem_hillshade.tif", "hillshade", ["-compute_edges"]),
        (dem_path, "dem_hillshade_135_30_z2.tif", "hillshade", ["-compute_edges", "-az", "135", "-alt", "30", "-z", "2"]),
        (dem_path, "dem_slope.tif", "slope", ["-compute_edges"]),
        (dem_path, "dem_aspect.tif", "aspect", ["-compute_edges"]),
        (holes_path, "dem_holes_slope.tif", "slope", ["-compute_edges"]),
        (dem_ll_path, "dem_4326_slope.tif", "slope", ["-compute_edges", "-xscale", repr(xscale), "-yscale", repr(yscale)]),
    ]
    for src, name, what, args in jobs:
        dst = os.path.join(OUT, name)
        gdaldem(lib, src, dst, what, args + ["-of", "GTiff", "-co", "COMPRESS=DEFLATE"])
        entries.append(summary(dst))

    # Contours of the DEM, every 25 m, on the cells' centers.
    import contourpy
    z = dem[0].astype("float64")
    xs = 500000.0 + 15.0 + 30.0 * np.arange(60)
    ys = 1600000.0 - 15.0 - 30.0 * np.arange(45)
    gen = contourpy.contour_generator(xs, ys, z, name="serial", line_type="Separate")
    levels = []
    for level in np.arange(math.ceil(z.min() / 25.0) * 25.0, z.max(), 25.0):
        lines = gen.lines(level)
        total = sum(float(np.sum(np.hypot(np.diff(l[:, 0]), np.diff(l[:, 1])))) for l in lines)
        closed = sum(1 for l in lines if np.allclose(l[0], l[-1]))
        levels.append({"level": float(level), "lines": len(lines), "closed": closed, "length": total})

    # An ASCII grid with a .prj, through GDAL's AAIGrid driver.
    asc = os.path.join(OUT, "dem.asc")
    with rasterio.open(asc, "w", driver="AAIGrid", width=60, height=45, count=1, dtype="float32",
                       crs="EPSG:32651", transform=demt, nodata=-9999.0) as d:
        d.write(holes)
    for extra in glob.glob(asc + ".aux.xml"):
        os.remove(extra)
    entries.append(summary(asc))

    # A PNG with a world file (and a .prj), read by GDAL's PNG driver.
    png = os.path.join(OUT, "picture.png")
    rgb = base("uint8", 3)
    with rasterio.open(png, "w", driver="PNG", width=W, height=H, count=3, dtype="uint8") as d:
        d.write(rgb)
    for extra in glob.glob(png + ".aux.xml"):
        os.remove(extra)
    with open(os.path.join(OUT, "picture.pgw"), "w") as f:
        f.write("0.5\n0.0\n0.0\n-0.5\n121.25\n14.75\n")
    with open(os.path.join(OUT, "picture.prj"), "w") as f:
        f.write(CRS.from_epsg(4326).to_wkt("WKT1_GDAL"))
    entries.append(summary(png))

    with open(os.path.join(OUT, "expected.json"), "w") as f:
        json.dump({"files": entries, "contours": levels}, f, indent=1)
    print(f"{len(entries)} files, {len(levels)} contour levels")


if __name__ == "__main__":
    main()
