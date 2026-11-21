# cartography — the contract between its parts

`cartography` is a Tessel **library** (`tessel.toml` has `[library]`; pinned to
Tessel 0.24.0; depends on the published libraries `geodesy` 0.2 and
`viewport` 0.1). It is ONE module: every `.tsl` file at the root shares one
namespace. Subfolders `tests/`, `examples/`, `scratch/` are separate programs.

User's choices (2026-11-22): name `cartography`; a library **and** a ready-made
`MapView`; all of: vector layers + styles, basemap tiles, more file formats,
rasters. Meridian (~/Dev/meridian, the user's QGIS-like app in Tessel) is the
source most code is ported from, but **Meridian itself must not be changed**.

## Rules for everyone

- Tessel: read `~/Dev/tessel/website/src/content/docs/` (`reference/stdlib.md`
  lists every built-in; `language/*.md` the language). Use the pinned toolchain
  the project selects automatically: `tessel check .`, `tessel test tests`,
  `tessel run <folder>` from the library folder. **Never run bare `tessel`**
  (opens an IDE window) and never run a program with an `app` except headless
  with `TESSEL_SCRIPT=...` set.
- Do not edit or build anything in `~/Dev/tessel`, `~/Dev/meridian`,
  `~/Dev/geodesy` or `~/Dev/viewport`. Read them freely. If Tessel has a bug,
  write the smallest program that shows it into your report and work around it.
- Every top-level name must be unique in the module, `private` ones too. Give
  every private helper of your files your prefix (formats: `fmt`, tiles:
  `tile`, raster: `ras`) or mark it `private` AND prefix it.
- Only change the files you own (below). If the core is missing something you
  need, add the smallest possible thing to a file you own, or say so in your
  report; don't edit core files.
- Each new source file starts with a comment block: what the file is, then
  `// Author: Alexius Academia` and `// Date: 2026-11-22`.
- Doc comments (`///`) on every public declaration, in plain words.
- Tests: `tests/<area>.tsl` with Tessel `test "…" { expect(…) }` blocks
  (see `website/src/content/docs/guides/testing.md`); the tests program
  imports the library with `import ".."`. Fixture files go in
  `tests/data/<area>/` (small; generate large ones). Where an outside tool
  can produce exact answers (GDAL/ogr2ogr, Python with pyproj/shapely/
  rasterio/numpy in a venv under the project's `.venv/`, which is
  gitignored), use it as an oracle and keep the generator in `tools/oracle/`.
- Commit your work in your worktree with a clear message, no
  Co-Authored-By or other trailers.

## The core (written by the lead; don't edit)

- `geometry.tsl`: `GeomKind {point, line, polygon}`, `Box` (mutable `add`,
  `include`, `contains`, `intersects`, `grown(by:)`, `width()`…), `boxOf`,
  `Geometry {kind, parts: [[Float]], polygons: [Int], box}` (flat x,y; polygon
  rings closed; `polygons` = index in parts of each polygon's outer ring),
  `makeGeometry`, `pointGeometry`, `multiPointGeometry`, `lineGeometry`,
  `multiLineGeometry`, `polygonGeometry`, `multiPolygonGeometry`,
  `boxGeometry`, `ringArea2`, `ringContains`, `polygonContains`,
  `distanceTo`, `segmentDistance`, `lineLength`.
- `table.tsl`: `FieldKind {int, float, text}`, `Value {null, num, text, bool}`,
  `Column {name, kind, nums, texts}` (NaN / "" = null), `emptyColumn`,
  `textColumn`, `numberColumn`, `columnFromTexts`, `formatNumber`,
  `groupedNumber`.
- `layer.tsl`: `Rgba`, `rgb`, `colorFromHex`, `MarkerShape`, `FillStyle`,
  `Symbol`, `RendererKind {single, categorized, graduated}`, `ClassMode`,
  `StyleClass`, `Style`, `LabelStyle`, `LabelPlacement`,
  `LayerKind {vector, tiles, raster}`, `Raster`, `RasterLook`, `RasterStyle`,
  `Layer` (fields: name, kind, visible, opacity, source, crs (geodesy.Crs),
  geomKind, geoms (layer CRS), shapes (map CRS, made by `project(to:)`),
  columns, selection, style, labels, …, urlTemplate/minZoom/maxZoom/
  attribution for tiles, raster/rasterStyle for rasters), `newVectorLayer`.
- `style.tsl`: palette, ramps (`rampNames`, `rampColor`), `defaultSymbol`,
  `categorizedStyle`, `classBreaks`, `graduatedStyle`, `classForNumber`,
  `labelAnchor`, `labelAngle`, `oriented`, `powerOfTen`.
- `crs.tsl`: `webMercator()`, `lonLat()`, `sameCrs`, `transformCoords`,
  `reprojected`, `metersPerUnit`.
- `map.tsl`: `Map {layers (index 0 at the bottom), crs, vp: viewport.Viewport,
  background, tileFolder, version, loading: Set<String>, credit}` with `add`,
  `refresh(i)` (vector: project + classify; raster: `renderRaster`), `setCrs`,
  `extent`, `fit`, `fitAll`, `centerOn`, `toMap`, `toScreen`, `toLonLat`,
  `fromLonLat`, `visible`, `scaleDenominator`, `featuresAt`, `featuresIn`,
  `attributes`, `select`, `draw(g)`, `savePicture`. Helpers `visibleBox(vp)`,
  `unitsPerPoint(vp)`, `toViewportBox`, `fromViewportBox`.
- `render.tsl`: `drawMap(g, m)`, `beginMapSpace(g, vp)`, `drawPixels(g, raster,
  vp, opacity)` (draws `raster.pixels` over `raster.pixelBox` in map space),
  `drawPicture(g, path, box, vp, opacity)` (a PNG/JPEG file over a map box).

## Parts given to builders

### Formats (prefix `fmt`) — files `formats*.tsl` (e.g. `formats.tsl`,
`formats_json.tsl`, `formats_geojson.tsl`, `formats_shapefile.tsl`…)

Port from `~/Dev/meridian/formats/` (readers AND writers): GeoJSON, WKT (and
WKB if cheap), CSV (x/y columns or a WKT column), Shapefile (+ .dbf, .prj via
`geodesy.fromWkt`, .cpg), KML, GPX, GeoPackage read + write. Public API (names
may be refined, keep the spirit):

- `readGeoJSON(_ text: String, name: String = "") -> Result<Layer>`,
  `geoJSON(_ layer: Layer) -> String` (writes in WGS84 lon/lat, reprojecting).
- `geometryFromWkt(_ text: String) -> Result<Geometry>`, `wkt(_ g: Geometry) -> String`.
- `readCSV(_ text: String, name:, x: String = "", y: String = "", wkt: String = "", crs: geodesy.Crs = lonLat()) -> Result<Layer>` (guesses lon/lat/x/y/wkt columns when not given), `csv(_ layer: Layer) -> String`.
- `readShapefile(_ path: String) -> Result<Layer>`, `writeShapefile(_ layer: Layer, _ path: String) -> Result<Bool>`.
- `readKML`, `kml(layer)`; `readGPX` (waypoints, routes, tracks as layers), `gpx(layers)`.
- `readGeoPackage(_ path: String) -> Result<[Layer]>`, `writeGeoPackage(_ layers: [Layer], _ path: String) -> Result<Bool>`.
- `readLayers(_ path: String) -> Result<[Layer]>` and `writeLayer(_ layer: Layer, _ path: String) -> Result<Bool>` choosing by extension.
- Layers read get `crs`, `geomKind`, `geoms`, `columns`, `name`, `source`,
  and `style.symbol = defaultSymbol(kind, seed:)`. They are not projected:
  `Map.add` does that.

Tests against real files: ogr2ogr / GDAL in a venv (`pyogrio` or `fiona`) or
Python's sqlite3 can write and re-read fixtures; round trips; Natural Earth
samples exist in `~/Dev/meridian/samples/natural-earth/` (copy small ones).

### Tiles (prefix `tile`) — files `tiles*.tsl` (replace the stub `tiles.tsl`)

Port from `~/Dev/meridian/gis/tiles.tsl`, `~/Dev/meridian/app/render.tsl`
(drawTiles, tilePath) and `~/Dev/meridian/app/state.tsl` (`warpTiles`).

- `TileSource {name, url, minZoom, maxZoom, attribution}`, `tileSources()` (keyless:
  OpenStreetMap standard, OpenTopoMap, Esri World Imagery, CARTO light/dark
  etc., each with its required attribution), `tileLayer(_ s: TileSource) -> Layer`,
  `openStreetMap() -> Layer`, `xyzLayer(url:name:attribution:minZoom:maxZoom:) -> Layer`,
  `wmsLayer(service:layers:…) -> Layer` (WMS GetMap through a template).
- `Tile {z, x, y}`, `tilesFor(_ m: Map, layer: Layer) -> [Tile]`, the zoom
  for the map's scale, URL filling ({z} {x} {y} {s} {-y} {bbox}).
- **`drawTileLayer(_ g: Graphics, _ layer: Layer, _ m: Map)`** (called by
  `drawMap`; it must not change state): in Web Mercator maps, draw each tile
  file on disk with `drawPicture`, falling back to a parent tile's part;
  in other systems, draw `layer.raster` with `drawPixels` (warped tiles).
- **`fetchTiles(_ m: Map, done: fn([String]))`** — downloads the missing tiles
  the map shows (uses `download`, a polite limit of parallel downloads, and a
  `User-Agent` header naming "cartography (Tessel library)"; respects
  `m.loading`: callers keep the returned/marked set in their state). Design how
  the caller keeps `loading` (e.g. `tilesToFetch(m) -> [(url, path)]` +
  `fetchTile`), since `Map` is a value. Document the pattern; `MapView` (lead)
  will call it after every view change and bump a redraw counter on `done`.
- **`warpTiles(_ m: Map, _ layer: Layer) -> Raster`** — in a map whose CRS
  isn't Web Mercator, reads the tile pixels (`readImage`) and resamples them
  into the map's CRS over the visible box (pixels ~ the canvas size), giving
  `pixels/pixelWidth/pixelHeight/pixelBox`. The lead will call it from
  `MapView` after fetches and view changes.
- Tile folder: `m.tileFolder` or `joinPath(tempFolder(), "cartography-tiles")`;
  a per-source subfolder; `clearTileCache`.
- Tests: tile numbers/boxes/URLs against known values (and mercantile or
  hand values in Python); warping a synthetic tile set written with
  `writeImage` into a `file://` URL source — no network in tests.

### Rasters (prefix `ras`) — files `raster*.tsl` (replace the stub `raster.tsl`)

Port from `~/Dev/meridian/raster/` and Meridian's raster styling.

- Readers: `readGeoTIFF(_ path: String) -> Result<Layer>` (strips/tiles, none/
  LZW/Deflate/PackBits, 8/16/32-bit int and float, multi-band, GeoKeys →
  `geodesy.epsg`, nodata tag), `readAsciiGrid`, `readHGT` (SRTM), PNG/JPEG +
  world file (`.pgw/.jgw/.wld`) as an RGB raster, and a general
  `readRaster(path)` by extension. Writers: `writeGeoTIFF`, `writeAsciiGrid`.
- `rasterLayer(name:, raster:, crs:) -> Layer`, `Raster` helpers: value at a
  map point (`rasterValue(layer, x, y, band:)` in the layer's CRS),
  statistics, min/max per band filled in by readers.
- **`renderRaster(_ layer: Layer, _ crs: geodesy.Crs) -> Raster`** (keep this
  exact signature: `Map.refresh` calls it): returns `layer.raster` with
  `pixels/pixelWidth/pixelHeight/pixelBox` made from `rasterStyle` (gray,
  ramp with `rampColor`/custom colors, classes, gamma, invert, hillshade, rgb),
  warped into `crs` when the layer's CRS differs (cap the picture at ~2048 px).
- Terrain: `hillshade`, `slope`, `aspect` as new rasters; `contours(_ layer:
  Layer, interval:, band:) -> Layer` (a line layer with an elevation column).
- Tests against GDAL (gdal_translate / gdaldem / rasterio in a venv) on small
  generated rasters.

## The lead's part

`MapView` (the ready-made view: pan/zoom/identify, tile fetching and warping
triggers, scale bar, attribution), `drawLegend`, `drawScaleBar`, README,
examples, website, merging the builders' branches, tests of the core.
