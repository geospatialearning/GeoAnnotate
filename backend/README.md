# ML Annotations — Raster Tile Server

A lightweight, dynamic raster tile server built with FastAPI. Load any GeoTIFF (or other GDAL-supported raster) at runtime and serve XYZ tiles for OpenLayers.

## Setup

```bash
cd backend
pip install -r requirements.txt
```

## Start the server

```bash
uvicorn main:app --reload --port 8000
```

The API docs are available at **http://localhost:8000/docs** (Swagger UI).

---

## API Reference

### Load a raster

Register a raster file for tile serving. The file is reprojected to EPSG:3857 on load.

```bash
curl -X POST "http://localhost:8000/rasters/?name=dem_hp&file_path=/absolute/path/to/dem_hp.tif"
```

**Response:**

```json
{
  "message": "Raster 'dem_hp' loaded successfully",
  "info": {
    "name": "dem_hp",
    "path": "/absolute/path/to/dem_hp.tif",
    "width": 1024,
    "height": 1024,
    "min_value": 0,
    "max_value": 4500
  }
}
```

### List loaded rasters

```bash
curl http://localhost:8000/rasters/
```

**Response:**

```json
{
  "rasters": [
    { "name": "dem_hp", "path": "...", "width": 1024, "height": 1024, "min_value": 0, "max_value": 4500 },
    { "name": "ndvi", "path": "...", "width": 2048, "height": 2048, "min_value": -1, "max_value": 1 }
  ]
}
```

### Get raster info

```bash
curl http://localhost:8000/rasters/dem_hp
```

### Request a tile

Standard XYZ tile URL pattern. Returns a 256x256 PNG with transparency for no-data areas.

```
GET http://localhost:8000/tiles/{name}/{z}/{x}/{y}.png
```

```bash
curl http://localhost:8000/tiles/dem_hp/10/565/384.png --output tile.png
```

Tiles are cached to disk under `tiles/{name}/{z}/{x}/{y}.png` after the first render.

### Unload a raster

Removes the dataset from memory and deletes its cached tiles.

```bash
curl -X DELETE http://localhost:8000/rasters/dem_hp
```

---

## Using with OpenLayers

Add the tile layer to your map after loading a raster via the API:

```js
import TileLayer from 'ol/layer/Tile'
import XYZ from 'ol/source/XYZ'

const rasterLayer = new TileLayer({
  source: new XYZ({
    url: 'http://localhost:8000/tiles/dem_hp/{z}/{x}/{y}.png',
  }),
})

map.addLayer(rasterLayer)
```

---

## Multiple rasters

You can load and serve multiple rasters simultaneously — each gets its own name and tile endpoint:

```bash
# Load two different rasters
curl -X POST "http://localhost:8000/rasters/?name=elevation&file_path=/data/dem.tif"
curl -X POST "http://localhost:8000/rasters/?name=landcover&file_path=/data/landcover.tif"

# Tiles are served at separate URLs
# http://localhost:8000/tiles/elevation/{z}/{x}/{y}.png
# http://localhost:8000/tiles/landcover/{z}/{x}/{y}.png
```
