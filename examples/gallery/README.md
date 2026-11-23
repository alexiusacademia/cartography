# cartography's gallery

The programs on the website's examples page
(https://cartography-package.syncster.dev/examples.html), one folder each.
Here they import the library from this repository (`import "../../.."`); on
the website they say `import cartography`, as a project that has run
`tessel add cartography` would.

Author: Alexius Academia · 2026-11-22

Check them all after changing the library:

```sh
for d in examples/gallery/*/; do tessel check "$d"; done
```

They read their files from the folder they're run in:

- `countries.geojson`, `rivers.geojson`, `places.geojson`: `examples/data`
- `dem.tif`: `tests/data/raster`
- `gauges.csv`: in `csv-points/`
- `hike.gpx` (a made-up loop trail near Tanay, Rizal): in `gpx-track/`
- `lots.shp`, `zones.gpkg`: your own files

| Folder | Kind | Shows |
|---|---|---|
| `first-map` | app | MapView over OpenStreetMap, a layer made in code |
| `find-places` | app | Filtering a layer with `hidden`, clicking features |
| `gpx-track` | app | GPX, arrows along a line, swapping basemaps |
| `utm` | app | A map in UTM, `setCrs`, eastings and northings |
| `own-canvas` | app | A Canvas instead of MapView, `fetchTiles`, `featuresIn` (on `places.geojson`) |
| `world` | picture | Equal Earth, a categorized style, `renderImage` |
| `choropleth` | picture | A graduated style by natural breaks |
| `terrain` | picture | Hillshade, a ramp and labeled contours |
| `csv-points` | picture | `readCSV`, sizes by a field, labels by scale |
| `convert` | program | Reading a shapefile, writing other formats |
| `build-layer` | program | `addFeature`, WKT and GeoJSON |
| `raster-stats` | program | Statistics, histogram, profile, zonal stats, slope |
