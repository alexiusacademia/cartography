"""Fixtures for cartography's file formats, written by GDAL (through
pyogrio), and what GDAL reads back from each: tests/formats.tsl reads the
same files with cartography and compares.

    .venv/bin/python tools/oracle/formats_fixtures.py

Writes tests/data/formats/: the files, and expected.json, a list of
{file, layer, kind, epsg, count, fields, kinds, rows, wkts}: per feature
its values as text (None: no value) and its shape as WKT with every digit.

Author: Alexius Academia
Date: 2026-11-22
"""

import csv
import json
import os
import shutil
import sys

import numpy as np
import pyogrio
import pyogrio.raw
import shapely
from shapely.geometry import LineString, MultiLineString, MultiPoint, MultiPolygon, Point, Polygon

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "tests", "data", "formats")
NE = os.path.expanduser("~/Dev/meridian/samples/natural-earth")


def write(path, geoms, fields, crs="EPSG:4326", driver=None, layer=None, append=False, **options):
    """Writes features with pyogrio's raw writer. `fields` is a list of
    (name, numpy array)."""
    names = [f[0] for f in fields]
    arrays = [f[1] for f in fields]
    wkb = np.array([None if g is None else shapely.to_wkb(g, output_dimension=2) for g in geoms], dtype=object)
    kinds = {g.geom_type for g in geoms if g is not None}
    gtype = "Unknown"
    if len(kinds) == 1:
        gtype = kinds.pop()
    elif kinds <= {"Point", "MultiPoint"}:
        gtype = "MultiPoint"
    elif kinds <= {"LineString", "MultiLineString"}:
        gtype = "MultiLineString"
    elif kinds <= {"Polygon", "MultiPolygon"}:
        gtype = "MultiPolygon"
    if driver == "GPKG":
        # (Smaller files: GDAL and cartography read them as well without.)
        options["SPATIAL_INDEX"] = "NO"
    pyogrio.raw.write(path, wkb, arrays, fields=names, crs=crs, driver=driver, layer=layer, append=append,
                      geometry_type=gtype, **options)


def kml_coords(coords):
    return " ".join(f"{x!r},{y!r}" for x, y in coords)


def kml_geometry(g):
    if g.geom_type == "Point":
        return f"<Point><coordinates>{kml_coords(g.coords)}</coordinates></Point>"
    if g.geom_type == "LineString":
        return f"<LineString><coordinates>{kml_coords(g.coords)}</coordinates></LineString>"
    if g.geom_type == "Polygon":
        out = f"<Polygon><outerBoundaryIs><LinearRing><coordinates>{kml_coords(g.exterior.coords)}</coordinates></LinearRing></outerBoundaryIs>"
        for r in g.interiors:
            out += f"<innerBoundaryIs><LinearRing><coordinates>{kml_coords(r.coords)}</coordinates></LinearRing></innerBoundaryIs>"
        return out + "</Polygon>"
    return "<MultiGeometry>" + "".join(kml_geometry(p) for p in g.geoms) + "</MultiGeometry>"


def write_kml(path, geoms, fields, name_field):
    """KML as Google Earth writes it, by hand (pyogrio's writer puts the
    values in the wrong fields of KML's fixed ones): a Schema, a Folder of
    Placemarks with a name and ExtendedData."""
    from xml.sax.saxutils import escape
    others = [f for f in fields if f[0] != name_field]
    types = {"i": "int", "f": "double"}
    out = ['<?xml version="1.0" encoding="UTF-8"?>\n<kml xmlns="http://www.opengis.net/kml/2.2">\n<Document>\n',
           '<Schema name="data" id="data">']
    for n, a in others:
        out.append(f'<SimpleField name="{n}" type="{types.get(a.dtype.kind, "string")}"/>')
    out.append("</Schema>\n<Folder><name>features</name>\n")
    names = dict(fields)[name_field]
    for i, g in enumerate(geoms):
        out.append(f"<Placemark><name>{escape(str(names[i]))}</name><ExtendedData><SchemaData schemaUrl=\"#data\">")
        for n, a in others:
            v = a[i]
            if isinstance(v, float) and np.isnan(v):
                continue
            out.append(f'<SimpleData name="{n}">{escape(text_of(v))}</SimpleData>')
        out.append("</SchemaData></ExtendedData>" + kml_geometry(g) + "</Placemark>\n")
    out.append("</Folder>\n</Document>\n</kml>\n")
    with open(path, "w", encoding="utf-8") as f:
        f.write("".join(out))


def exact_wkt(g):
    """WKT with every digit (shapely's to_wkt keeps only 16 of them)."""
    def pts(coords):
        return "(" + ", ".join(f"{x!r} {y!r}" for x, y, *_ in coords) + ")"

    def poly(p):
        return "(" + ", ".join(pts(r.coords) for r in [p.exterior] + list(p.interiors)) + ")"

    t = g.geom_type
    if t == "Point":
        return "POINT " + pts(g.coords)
    if t == "LineString":
        return "LINESTRING " + pts(g.coords)
    if t == "Polygon":
        return "POLYGON " + poly(g)
    if t == "MultiPoint":
        return "MULTIPOINT (" + ", ".join(pts(p.coords) for p in g.geoms) + ")"
    if t == "MultiLineString":
        return "MULTILINESTRING (" + ", ".join(pts(l.coords) for l in g.geoms) + ")"
    if t == "MultiPolygon":
        return "MULTIPOLYGON (" + ", ".join(poly(p) for p in g.geoms) + ")"
    raise ValueError(t)


def kind_of(geom_type):
    t = (geom_type or "").replace(" Z", "").replace("25D", "").upper()
    if "POINT" in t:
        return "point"
    if "LINE" in t:
        return "line"
    if "POLYGON" in t:
        return "polygon"
    return "point"


def text_of(v):
    if v is None:
        return None
    if isinstance(v, float) or isinstance(v, np.floating):
        if np.isnan(v):
            return None
        return repr(float(v))
    if isinstance(v, (bool, np.bool_)):
        return "1" if v else "0"
    if isinstance(v, (int, np.integer)):
        return str(int(v))
    if isinstance(v, bytes):
        return None
    s = str(v)
    return s


def expect(path, layer=None, fields=None, **options):
    """What GDAL reads from a file (one layer of it)."""
    meta, _, geometry, values = pyogrio.raw.read(path, layer=layer, **options)
    info = pyogrio.read_info(path, layer=layer, **options)
    names = list(meta["fields"])
    dtypes = [str(d) for d in meta["dtypes"]]
    keep = [i for i, n in enumerate(names) if fields is None or n in fields]
    kinds = []
    for i in keep:
        d = dtypes[i]
        kinds.append("int" if d.startswith("int") or d == "bool" else "float" if d.startswith("float") else "text")
    rows = []
    wkts = []
    for r in range(len(geometry)):
        rows.append([text_of(values[i][r]) for i in keep])
        g = None if geometry[r] is None else shapely.from_wkb(geometry[r])
        if g is None or g.is_empty:
            wkts.append("")
        else:
            wkts.append(exact_wkt(g))
    crs = meta["crs"] or ""
    epsg = int(crs.split(":")[1]) if crs.upper().startswith("EPSG:") else 0
    return {
        "file": os.path.relpath(path, OUT),
        "layer": info["layer_name"] if "layer_name" in info else (layer or ""),
        "kind": kind_of(meta["geometry_type"] if meta["geometry_type"] != "Unknown" else
                        next((shapely.from_wkb(g).geom_type for g in geometry if g is not None), "")),
        "epsg": epsg,
        "count": len(geometry),
        "fields": [names[i] for i in keep],
        "kinds": kinds,
        "rows": rows,
        "wkts": wkts,
    }


def main():
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)
    expected = []

    # The same features in several formats.
    points = [Point(121.0, 14.6), Point(-73.98543, 40.758896), Point(2.2945, 48.8584), Point(151.2153, -33.8568),
              Point(0.0, 0.0)]
    pf = [
        ("id", np.array([1, 2, 3, 4, 5], dtype=np.int32)),
        ("name", np.array(["Manila", "Times Square, NYC", "Tour Eiffel \"Zoë\"", "Sydney Opera", "Null Island"], dtype=object)),
        ("value", np.array([1.5, -2.25, 1e-7, 123456.789, np.nan], dtype=np.float64)),
        ("count", np.array([10, 20, 30, 40, 50], dtype=np.int64)),
    ]
    lines = [LineString([(0, 0), (1, 1), (2, 0.5)]),
             MultiLineString([[(10, 10), (11, 12)], [(12, 12), (13, 11), (14, 15)]]),
             LineString([(-120.5, 35.25), (-119.75, 36.125)])]
    lf = [("id", np.array([1, 2, 3], dtype=np.int32)), ("road", np.array(["A1", "B2", "C3 ñ"], dtype=object)),
          ("len", np.array([2.5, 7.75, 1.0], dtype=np.float64))]
    polygons = [
        Polygon([(0, 0), (10, 0), (10, 10), (0, 10)], [[(2, 2), (2, 4), (4, 4), (4, 2)]]),
        MultiPolygon([Polygon([(20, 20), (25, 20), (25, 25), (20, 25)]),
                      Polygon([(30, 30), (35, 30), (32.5, 35)], [[(31, 31), (32.5, 33), (34, 31)]])]),
        Polygon([(-5, -5), (-1, -5), (-3, -1)]),
    ]
    gf = [("id", np.array([1, 2, 3], dtype=np.int32)), ("zone", np.array(["park", "lake", "farm"], dtype=object)),
          ("area", np.array([96.0, 31.5, 8.0], dtype=np.float64))]

    for name, geoms, fields, label in [("points", points, pf, "name"), ("lines", lines, lf, "road"),
                                       ("polygons", polygons, gf, "zone")]:
        for ext, driver in [("geojson", "GeoJSON"), ("shp", "ESRI Shapefile"), ("gpkg", "GPKG")]:
            path = os.path.join(OUT, f"{name}.{ext}")
            write(path, geoms, fields, driver=driver, layer=name)
            expected.append(expect(path))
        path = os.path.join(OUT, f"{name}.kml")
        write_kml(path, geoms, fields, label)
        expected.append(expect(path))
        path = os.path.join(OUT, f"{name}_wkt.csv")
        write(path, geoms, fields, driver="CSV", layer=name, GEOMETRY="AS_WKT")
        expected.append(expect(path))
    # Points in columns of coordinates (GDAL's CSV writer can't make these;
    # its reader, told the columns' names, reads them back).
    path = os.path.join(OUT, "points_xy.csv")
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "name", "longitude", "latitude", "value"])
        for i, p in enumerate(points):
            v = pf[2][1][i]
            w.writerow([i + 1, pf[1][1][i], repr(p.x), repr(p.y), "" if np.isnan(v) else repr(float(v))])
    expected.append(expect(path, X_POSSIBLE_NAMES="longitude", Y_POSSIBLE_NAMES="latitude", KEEP_GEOM_COLUMNS="YES",
                           AUTODETECT_TYPE="YES"))

    # A projected shapefile and GeoPackage (UTM zone 51N), and a GeoPackage
    # of several layers.
    utm = [shapely.affinity.translate(shapely.affinity.scale(p, 1000, 1000, origin=(0, 0)), 500000, 1600000)
           for p in polygons]
    for ext, driver in [("shp", "ESRI Shapefile"), ("gpkg", "GPKG")]:
        path = os.path.join(OUT, f"utm51.{ext}")
        write(path, utm, gf, crs="EPSG:32651", driver=driver, layer="utm51")
        expected.append(expect(path))
    path = os.path.join(OUT, "several.gpkg")
    write(path, points, pf, driver="GPKG", layer="cities")
    write(path, lines, lf, driver="GPKG", layer="roads", append=True)
    write(path, utm, gf, crs="EPSG:32651", driver="GPKG", layer="zones", append=True)
    for layer in ["cities", "roads", "zones"]:
        expected.append(expect(path, layer=layer))

    # GPX: waypoints, a route and a track.
    # (Written by hand: pyogrio's writer misplaces values among GPX's
    # fixed fields too.)
    path = os.path.join(OUT, "trip.gpx")
    with open(path, "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n'
                '<gpx version="1.1" creator="oracle" xmlns="http://www.topografix.com/GPX/1/1">\n'
                '<metadata><name>trip</name></metadata>\n')
        for p, n, e in zip(points[:3], ["a", "b & c", "d"], [10.5, 20.0, 30.25]):
            f.write(f'<wpt lat="{p.y!r}" lon="{p.x!r}"><ele>{e!r}</ele><name>{n.replace("&", "&amp;")}</name></wpt>\n')
        f.write('<rte><name>route one</name><rtept lat="14.5" lon="121.0"/><rtept lat="14.6" lon="121.1"/>'
                '<rtept lat="14.55" lon="121.2"/></rte>\n')
        f.write('<trk><name>morning walk</name><trkseg><trkpt lat="15.0" lon="120.0"><ele>3</ele></trkpt>'
                '<trkpt lat="15.02" lon="120.01"/></trkseg><trkseg><trkpt lat="15.03" lon="120.02"/>'
                '<trkpt lat="15.04" lon="120.05"/><trkpt lat="15.0" lon="120.06"/></trkseg></trk>\n</gpx>\n')
    for layer in ["waypoints", "routes", "tracks"]:
        expected.append(expect(path, layer=layer, fields=["name", "ele"] if layer == "waypoints" else ["name"]))

    # Natural Earth: some countries (multipolygons, holes, text in many
    # scripts) as a shapefile and a GeoPackage; populated places as points.
    src = os.path.join(NE, "ne_110m_admin_0_countries.shp")
    if os.path.exists(src):
        meta, _, geometry, values = pyogrio.raw.read(src)
        names = list(meta["fields"])
        wanted = ["Indonesia", "Fiji", "South Africa", "Lesotho", "Philippines", "Japan", "France", "Italy",
                  "New Zealand", "Chile"]
        at = names.index("ADMIN")
        rows = [r for r in range(len(geometry)) if values[at][r] in wanted]
        cols = ["ADMIN", "ISO_A3", "POP_EST", "CONTINENT", "NAME_ZH", "NAME_RU", "LABEL_X"]
        geoms = [shapely.from_wkb(geometry[r]) for r in rows]
        fields = [(c, values[names.index(c)][rows]) for c in cols]
        fields[2] = ("POP_EST", fields[2][1].astype(np.int64))
        for ext, driver in [("shp", "ESRI Shapefile"), ("gpkg", "GPKG")]:
            path = os.path.join(OUT, f"countries.{ext}")
            write(path, geoms, fields, driver=driver, layer="countries")
            expected.append(expect(path))
    else:
        print("Natural Earth samples not found; skipped", file=sys.stderr)

    # WKT and WKB: shapely's reading of each text, its parts as cartography
    # keeps them, and its WKB (plain 2D little-endian; and big-endian with
    # Z, and EWKB with a CRS number, for reading).
    cases = [
        "POINT (121 14.6)", "POINT Z (1.5 -2.25 3)", "POINT M (1 2 3)", "POINT ZM (1 2 3 4)",
        "MULTIPOINT ((1 2), (3 4))", "MULTIPOINT (5 6, 7 8, 9 10)",
        "LINESTRING (30 10, 10 30, 40 40)", "LINESTRING Z (0 0 1, 1e-7 2.5e3 2)",
        "MULTILINESTRING ((10 10, 20 20, 10 40), (40 40, 30 30, 40 20, 30 10))",
        "POLYGON ((30 10, 40 40, 20 40, 10 20, 30 10))",
        "POLYGON ((35 10, 45 45, 15 40, 10 20, 35 10), (20 30, 35 35, 30 20, 20 30))",
        "MULTIPOLYGON (((30 20, 45 40, 10 40, 30 20)), ((15 5, 40 10, 10 20, 5 10, 15 5)))",
        "MULTIPOLYGON (((40 40, 20 45, 45 30, 40 40)), ((20 35, 10 30, 10 10, 30 5, 45 20, 20 35), (30 20, 20 15, 20 25, 30 20)))",
        "polygon((0 0,1 0,1 1,0 0))", "  LINESTRING(0.1 0.2,0.30000000000000004 -1e-300)  ",
        "LINESTRING (-179.99999999999997 89.123456789012345, 1.7976931348623157e308 -0)",
    ]
    wkt_out = []
    for text in cases:
        g = shapely.from_wkt(text)
        g2 = shapely.force_2d(g)
        if g2.geom_type in ("Point", "MultiPoint"):
            parts = [[c for p in (g2.geoms if g2.geom_type == "MultiPoint" else [g2]) for c in p.coords[0]]]
            starts = []
        elif g2.geom_type in ("LineString", "MultiLineString"):
            parts = [[c for xy in l.coords for c in xy] for l in (g2.geoms if g2.geom_type == "MultiLineString" else [g2])]
            starts = []
        else:
            parts, starts = [], []
            for p in (g2.geoms if g2.geom_type == "MultiPolygon" else [g2]):
                starts.append(len(parts))
                for r in [p.exterior] + list(p.interiors):
                    parts.append([c for xy in r.coords for c in xy])
        wkt_out.append({
            "text": text,
            "kind": kind_of(g2.geom_type),
            "parts": parts,
            "polygons": starts,
            "wkb": shapely.to_wkb(g2, hex=True, output_dimension=2, byte_order=1),
            "wkbBig": shapely.to_wkb(g, hex=True, output_dimension=3, byte_order=0, flavor="iso"),
            "ewkb": shapely.to_wkb(shapely.set_srid(g, 4326), hex=True, output_dimension=3, byte_order=1,
                                   include_srid=True, flavor="extended"),
        })
    with open(os.path.join(OUT, "wkt_cases.json"), "w") as f:
        json.dump(wkt_out, f, indent=1)

    # GeoPackages made smaller (pages of 1 KB, without free ones).
    import sqlite3
    for name in os.listdir(OUT):
        if name.endswith(".gpkg"):
            con = sqlite3.connect(os.path.join(OUT, name))
            con.execute("PRAGMA page_size = 1024")
            con.execute("VACUUM")
            con.close()

    with open(os.path.join(OUT, "expected.json"), "w") as f:
        json.dump(expected, f, ensure_ascii=False, indent=1)
    print(f"{len(expected)} layers in {OUT}")


if __name__ == "__main__":
    main()
