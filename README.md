# GeoAnnotate

A web-based platform for annotating geospatial raster imagery and training machine learning models for land cover classification.

## Overview

GeoAnnotate lets you load satellite/raster imagery onto an interactive map, annotate features like vegetation, water bodies, and buildings, and (in the future) use those annotations to train ML models for automated classification.

## Project Structure

```
geoannotate/
├── backend/          # FastAPI tile server
│   ├── main.py           # API endpoints (browse, load, serve tiles)
│   └── tile_renderer.py  # Raster loading, reprojection, and tile rendering
├── frontend/         # Vue 3 web application
│   └── src/
│       ├── components/
│       │   ├── MapViewer.vue    # OpenLayers map display
│       │   └── LayerPanel.vue   # Layer management + annotation tools
│       └── stores/
│           └── map.ts           # Pinia store (map state, layers, basemaps)
└── dataset/          # Raster files and annotation data
```

## Tech Stack

**Frontend**: Vue 3, TypeScript, OpenLayers, Quasar UI, Pinia

**Backend**: FastAPI, rioxarray, xarray, rasterio, Pillow

## Getting Started

### Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Set `DATASET_DIR` env var to point to your raster files directory (defaults to `../dataset`).

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## Current Features

- **Dynamic raster tile server** — load any GeoTIFF/JP2 raster via API, served as XYZ tiles with disk caching
- **RGB and single-band support** — renders multi-band satellite imagery in true color
- **Interactive map** — OpenLayers with pan, zoom, and view state sync
- **Layer panel** — add/remove raster layers, toggle visibility, basemap switching (OSM + Microsoft Satellite)
- **Annotation tools** — draw points, lines, and polygons with scenario categories (vegetation, water bodies)

## Future Plans

- **More annotation scenarios** — buildings, roads, agricultural land, bare soil
- **Export annotations** — save drawn features as GeoJSON with scenario metadata
- **ML model training** — use annotations as labeled training data for land cover classification models
- **Model inference** — run trained models on new rasters and visualize predictions as overlay layers
- **Annotation import** — load existing GeoJSON/Shapefile annotations onto the map
- **Multi-user support** — collaborative annotation with user accounts
- **Pre-trained model library** — ship common land cover models ready to use out of the box
