#!/usr/bin/env python3
# Writes tests/tiles_oracle.tsl: tile numbers, boxes, TMS rows, quadkeys and
# tile URLs worked out with mercantile, the answers tests/tiles.tsl checks
# cartography's tile maths against.
#
#   python3 -m venv .venv && .venv/bin/pip install mercantile
#   .venv/bin/python tools/oracle/tiles_oracle.py
#
# Author: Alexius Academia
# Date: 2026-11-22

import os
import random

import mercantile

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "..", "tests", "tiles_oracle.tsl")

random.seed(20261122)

cases = [
    (0.0, 0.0, 0),
    (121.0244, 14.5547, 12),     # Manila
    (-0.1276, 51.5072, 15),      # London
    (-73.9857, 40.7484, 17),     # New York
    (151.2093, -33.8688, 9),     # Sydney
    (-179.9, -84.9, 4),
    (179.9, 84.9, 6),
    (2.3522, 48.8566, 19),       # Paris
]
for _ in range(40):
    lon = random.uniform(-179.99, 179.99)
    lat = random.uniform(-85.0, 85.0)
    z = random.randint(0, 20)
    cases.append((round(lon, 6), round(lat, 6), z))

rows = []
quadkeys = []
for lon, lat, z in cases:
    t = mercantile.tile(lon, lat, z)
    b = mercantile.xy_bounds(t)
    tms = (2 ** z) - 1 - t.y
    rows.append([lon, lat, z, t.x, t.y, b.left, b.bottom, b.right, b.top, tms])
    quadkeys.append(mercantile.quadkey(t) if z > 0 else "")

# URL templates filled in for a few tiles.
templates = [
    "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
    "https://example.com/tms/{z}/{x}/{-y}.png",
    "https://example.com/q/{q}.jpeg",
    "https://example.com/wms?BBOX={bbox}&WIDTH=256",
]
urls = []
for tpl in templates:
    for lon, lat, z in cases[:6]:
        t = mercantile.tile(lon, lat, z)
        b = mercantile.xy_bounds(t)
        s = "abc"[(t.x + t.y) % 3]
        u = (tpl.replace("{z}", str(z)).replace("{x}", str(t.x)).replace("{y}", str(t.y))
             .replace("{-y}", str((2 ** z) - 1 - t.y)).replace("{s}", s)
             .replace("{q}", mercantile.quadkey(t) if z > 0 else "")
             .replace("{bbox}", "%s,%s,%s,%s" % (repr(b.left), repr(b.bottom), repr(b.right), repr(b.top))))
        urls.append((tpl, z, t.x, t.y, u))


def num(v):
    return repr(float(v))


def esc(s):
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("{", "\\{").replace("}", "\\}")


with open(OUT, "w") as f:
    f.write("// cartography tests: expected tile numbers, boxes and URLs, written by\n")
    f.write("// tools/oracle/tiles_oracle.py with mercantile. Don't edit by hand.\n")
    f.write("//\n// Author: Alexius Academia\n// Date: 2026-11-22\n\n")
    f.write("// lon, lat, zoom, x, y, minX, minY, maxX, maxY (EPSG:3857), TMS row\n")
    f.write("let tileOracleRows: [[Float]] = [\n")
    for r in rows:
        f.write("    [" + ", ".join(num(v) for v in r) + "],\n")
    f.write("]\n\n")
    f.write("// The quadkey of each row's tile.\n")
    f.write("let tileOracleQuadkeys: [String] = [\n")
    for q in quadkeys:
        f.write('    "%s",\n' % q)
    f.write("]\n\n")
    f.write("// template, zoom, x, y, URL\n")
    f.write("let tileOracleUrls: [(String, Int, Int, Int, String)] = [\n")
    for tpl, z, x, y, u in urls:
        f.write('    ("%s", %d, %d, %d, "%s"),\n' % (esc(tpl), z, x, y, esc(u)))
    f.write("]\n")

print("wrote", os.path.normpath(OUT), len(rows), "tiles,", len(urls), "urls")
