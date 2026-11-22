# cartography's website

The page for the cartography library, live at https://cartography-package.syncster.dev.

Author: Alexius Academia · Started 2026-11-22

A static page: no build step, no dependencies. Netlify (team syncster.dev)
deploys this folder by itself whenever `main` is pushed to GitHub.

```
index.html             # the page
docs.html              # every type and function
examples.html          # whole programs, each checked with `tessel check`
site.js                # code colors, copy buttons, the docs' filter and side menu
styles.css             # the other libraries' design, in green
assets/*.png           # the pictures `tessel run examples/pictures` draws (copied from ../docs)
assets/gauges.jpg      # the picture of the CSV example on examples.html
assets/share.png       # world.png cropped to 1981 x 1040 and scaled to 1200 x 630
assets/favicon.svg
netlify.toml           # no build; HTML isn't cached
```

To look at it locally: `python3 -m http.server 8080 -d website`, then
http://localhost:8080/.
