"""Has GDAL (and shapely and pyproj) read the files cartography writes.

    .venv/bin/python tools/oracle/formats_check_written.py [library folder]

Runs the test "files are written for the oracle" of tests/formats.tsl,
which reads the GDAL-written GeoPackages of tests/data/formats with
cartography and writes each as GeoJSON, a shapefile, a GeoPackage, CSV,
KML, WKT lines and GPX into <temp>/cartography-formats-oracle. Then reads
every one of those with GDAL (WKT lines with shapely) and compares the
features, their values and their coordinates with what GDAL read from the
fixtures (expected.json); formats in WGS 84 are compared with the
fixture's shapes brought to WGS 84 by pyproj. Prints one line a file and
exits with 1 if anything differs.

Author: Alexius Academia
Date: 2026-11-22
"""

import json
import os
import sqlite3
import subprocess
import sys
import tempfile

import numpy as np
import pyogrio
import pyogrio.raw
import pyproj
import shapely
import shapely.ops

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else HERE
DATA = os.path.join(HERE, "tests", "data", "formats")
OUT = os.path.join(tempfile.gettempdir(), "cartography-formats-oracle")

problems = []


def problem(what):
    problems.append(what)
    print("  DIFFERS:", what)


def to_wgs84(geom, epsg):
    if epsg in (0, 4326):
        return geom
    t = pyproj.Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326", always_xy=True)
    return shapely.ops.transform(t.transform, geom)


def same_shape(a, b, tolerance):
    """Same points (polygons: same rings, whatever their direction)."""
    if a is None or a.is_empty or b is None or b.is_empty:
        return (a is None or a.is_empty) == (b is None or b.is_empty)
    a = shapely.normalize(shapely.force_2d(a))
    b = shapely.normalize(shapely.force_2d(b))
    # A single shape and a multi one of one member are the same here.
    if a.geom_type.startswith("Multi") and len(a.geoms) == 1:
        a = a.geoms[0]
    if b.geom_type.startswith("Multi") and len(b.geoms) == 1:
        b = b.geoms[0]
    return a.equals_exact(b, tolerance)


def same_value(got, want):
    if want is None or want == "":
        return got is None or got == "" or (isinstance(got, float) and np.isnan(got))
    try:
        w = float(want)
        g = float(got)
        return abs(w - g) <= 1e-12 * max(1.0, abs(w))
    except (TypeError, ValueError):
        return str(got) == want


def compare(path, e, layer=None, tolerance=0.0, wgs84=False, fields=True, **options):
    meta, _, geometry, values = pyogrio.raw.read(path, layer=layer, **options)
    names = [n.lower() for n in meta["fields"]]
    n = len(geometry)
    name = os.path.basename(path) + (f" ({layer})" if layer else "")
    if n != e["count"]:
        problem(f"{name}: {n} features, not {e['count']}")
        return
    if not wgs84 and e["epsg"]:
        crs = meta["crs"] or ""
        if crs != f"EPSG:{e['epsg']}":
            got = pyproj.CRS.from_user_input(crs) if crs else None
            if got is None or not got.equals(pyproj.CRS.from_epsg(e["epsg"]), ignore_axis_order=True):
                problem(f"{name}: CRS {crs!r}, not EPSG:{e['epsg']}")
    shapes = 0
    for r in range(n):
        got = None if geometry[r] is None else shapely.from_wkb(geometry[r])
        want = shapely.from_wkt(e["wkts"][r]) if e["wkts"][r] else None
        if want is not None and wgs84:
            want = to_wgs84(want, e["epsg"])
        if not same_shape(got, want, tolerance):
            problem(f"{name} row {r}: {got} isn't {want}"[:300])
        shapes += 1
    checked = 0
    if fields:
        for f, field in enumerate(e["fields"]):
            if field.lower() not in names:
                problem(f"{name}: no field {field}")
                continue
            at = names.index(field.lower())
            for r in range(n):
                v = values[at][r]
                if not same_value(None if v is None else v.item() if hasattr(v, "item") else v, e["rows"][r][f]):
                    problem(f"{name} {field} row {r}: {v!r}, not {e['rows'][r][f]!r}")
                checked += 1
    print(f"ok-ish {name}: {shapes} shapes, {checked} values compared")


def main():
    print(f"writing with cartography from {ROOT} …")
    run = subprocess.run(["tessel", "test", "tests", "--filter", "files are written for the oracle"], cwd=ROOT,
                         capture_output=True, text=True)
    print(run.stdout.strip().splitlines()[-1] if run.stdout.strip() else run.stderr)
    if run.returncode != 0:
        print(run.stdout, run.stderr)
        sys.exit(1)
    expected = {(x["file"], x["layer"]): x for x in json.load(open(os.path.join(DATA, "expected.json")))}

    for name in ["points", "lines", "polygons", "utm51", "countries"]:
        e = expected[(name + ".gpkg", name)]
        base = os.path.join(OUT, name)
        compare(base + ".gpkg", e)
        compare(base + ".shp", e)
        compare(base + ".geojson", e, tolerance=1e-7, wgs84=True)
        if e["kind"] == "point":
            compare(base + ".csv", e, X_POSSIBLE_NAMES="X", Y_POSSIBLE_NAMES="Y", AUTODETECT_TYPE="YES")
        else:
            compare(base + ".csv", e, GEOM_POSSIBLE_NAMES="WKT", KEEP_GEOM_COLUMNS="NO", AUTODETECT_TYPE="YES")
        # GDAL's KML reader has only Name and Description.
        compare(base + ".kml", e, tolerance=1e-7, wgs84=True, fields=False)
        if e["kind"] != "polygon":
            compare(base + ".gpx", e, layer="waypoints" if e["kind"] == "point" else "tracks", tolerance=1e-7, wgs84=True, fields=False)
        # WKT lines, with shapely.
        lines = open(base + ".wkt", encoding="utf-8").read().splitlines()
        if len(lines) != e["count"]:
            problem(f"{name}.wkt: {len(lines)} lines, not {e['count']}")
        for r, line in enumerate(lines):
            text = line.split(";", 1)[1] if line.startswith("SRID=") else line
            got = shapely.from_wkt(text)
            want = shapely.from_wkt(e["wkts"][r]) if e["wkts"][r] else None
            if not same_shape(got, want, 0.0):
                problem(f"{name}.wkt row {r}: {got} isn't {want}"[:300])
        print(f"ok-ish {name}.wkt: {len(lines)} shapes")
        # The GeoPackage's own tables.
        con = sqlite3.connect(base + ".gpkg")
        app = con.execute("PRAGMA application_id").fetchone()[0]
        version = con.execute("PRAGMA user_version").fetchone()[0]
        check = con.execute("PRAGMA integrity_check").fetchone()[0]
        srs = con.execute("SELECT srs_id FROM gpkg_geometry_columns").fetchone()[0]
        con.close()
        if app != 0x47504B47 or version < 10200 or check != "ok" or srs != (e["epsg"] or 4326):
            problem(f"{name}.gpkg: application_id {app:x}, user_version {version}, integrity {check}, srs {srs}")

    for layer in ["cities", "roads", "zones"]:
        compare(os.path.join(OUT, "several.gpkg"), expected[("several.gpkg", layer)], layer=layer)
    for layer in ["waypoints", "routes", "tracks"]:
        compare(os.path.join(OUT, "trip.gpx"), expected[("trip.gpx", layer)], layer=layer, tolerance=1e-7)

    if problems:
        print(f"{len(problems)} differences")
        sys.exit(1)
    print("GDAL reads every file cartography wrote as the features it was given")


if __name__ == "__main__":
    main()
