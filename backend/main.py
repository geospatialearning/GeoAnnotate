"""Dynamic raster tile server.

Usage:
    uvicorn main:app --reload --port 8000

    Set DATASET_DIR env var to the directory containing raster files.
    Defaults to ../dataset/raster
"""

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from starlette.responses import FileResponse

from tile_renderer import RasterRegistry, render_tile, crop_raster_by_polygon

RASTER_EXTENSIONS = {".tif", ".tiff", ".geotiff", ".jp2", ".nc", ".hdf", ".img"}
DATASET_DIR = Path(os.environ.get("DATASET_DIR", Path(__file__).parent.parent / "dataset")).resolve()
ANNOTATIONS_DIR = Path(os.environ.get("ANNOTATIONS_DIR", Path(__file__).parent.parent / "annotations")).resolve()

app = FastAPI(title="ML Annotations Tile Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

TILE_CACHE_DIR = Path("tiles")
registry = RasterRegistry()


# ── Pydantic models ───────────────────────────────────────────────────

class AnnotationRequest(BaseModel):
    raster_name: str
    scenario: str
    polygon: list[list[float]]  # [[lon, lat], ...] in EPSG:3857


# ── File browsing ────────────────────────────────────────────────────

@app.get("/browse/")
async def browse_raster_files():
    """List all supported raster files in the configured dataset directory."""
    if not DATASET_DIR.exists():
        raise HTTPException(status_code=404, detail=f"Dataset directory not found: {DATASET_DIR}")

    files = []
    for f in sorted(DATASET_DIR.iterdir()):
        if f.is_file() and f.suffix.lower() in RASTER_EXTENSIONS:
            files.append({
                "name": f.stem,
                "filename": f.name,
                "path": str(f.resolve()),
                "size_mb": round(f.stat().st_size / (1024 * 1024), 2),
            })

    return {"directory": str(DATASET_DIR), "files": files}


# ── Raster management ────────────────────────────────────────────────

@app.post("/rasters/")
async def load_raster(
    name: str = Query(..., description="Unique name for this raster layer"),
    file_path: str = Query(..., description="Absolute path to the raster file"),
):
    """Load a raster file and make it available for tile serving."""
    if not Path(file_path).exists():
        raise HTTPException(status_code=404, detail=f"File not found: {file_path}")

    try:
        dataset = registry.load(name, file_path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to load raster: {e}")

    return {
        "message": f"Raster '{name}' loaded successfully",
        "info": registry.info(name),
    }


@app.delete("/rasters/{name}")
async def unload_raster(name: str):
    """Unload a raster dataset and free memory."""
    if not registry.remove(name):
        raise HTTPException(status_code=404, detail=f"Raster '{name}' not found")

    # Clear cached tiles for this raster
    cache_dir = TILE_CACHE_DIR / name
    if cache_dir.exists():
        import shutil
        shutil.rmtree(cache_dir)

    return {"message": f"Raster '{name}' unloaded"}


@app.get("/rasters/")
async def list_rasters():
    """List all loaded raster datasets."""
    names = registry.list_all()
    return {
        "rasters": [registry.info(n) for n in names],
    }


@app.get("/rasters/{name}")
async def get_raster_info(name: str):
    """Get info about a loaded raster dataset."""
    info = registry.info(name)
    if info is None:
        raise HTTPException(status_code=404, detail=f"Raster '{name}' not found")
    return info


# ── Tile serving ─────────────────────────────────────────────────────

@app.get("/tiles/{name}/{z}/{x}/{y}.png")
async def get_tile(name: str, z: int, x: int, y: int):
    """Serve a 256x256 PNG tile for the named raster at (z, x, y)."""
    dataset = registry.get(name)
    if dataset is None:
        raise HTTPException(status_code=404, detail=f"Raster '{name}' not loaded")

    # Check cache first
    tile_path = TILE_CACHE_DIR / name / str(z) / str(x) / f"{y}.png"

    if tile_path.exists():
        return FileResponse(tile_path, media_type="image/png")

    # Render tile
    tile_data = render_tile(dataset, z, x, y)

    if tile_data is None:
        return Response(content=b"", media_type="image/png", status_code=204)

    # Cache to disk
    tile_path.parent.mkdir(parents=True, exist_ok=True)
    tile_path.write_bytes(tile_data)

    return Response(content=tile_data, media_type="image/png")


# ── Annotations ────────────────────────────────────────────────────────

@app.post("/annotations/")
async def create_annotation(req: AnnotationRequest):
    """Crop raster data using a polygon and save the annotation."""
    dataset = registry.get(req.raster_name)
    if dataset is None:
        raise HTTPException(
            status_code=404,
            detail=f"Raster '{req.raster_name}' not loaded",
        )

    if len(req.polygon) < 3:
        raise HTTPException(status_code=400, detail="Polygon must have at least 3 coordinates")

    # Create output directory: annotations/<raster_name>/<scenario>/
    out_dir = ANNOTATIONS_DIR / req.raster_name / req.scenario
    out_dir.mkdir(parents=True, exist_ok=True)

    annotation_id = uuid.uuid4().hex[:10]

    try:
        png_path, mask_path, crop_bounds = crop_raster_by_polygon(
            dataset=dataset,
            polygon_coords=req.polygon,
            output_dir=out_dir,
            annotation_id=annotation_id,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to crop raster: {e}")

    # Save metadata
    metadata = {
        "id": annotation_id,
        "raster_name": req.raster_name,
        "raster_path": dataset.path,
        "scenario": req.scenario,
        "polygon": req.polygon,
        "bounds": crop_bounds,
        "png_file": str(png_path),
        "mask_file": str(mask_path),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    meta_path = out_dir / f"{annotation_id}_meta.json"
    meta_path.write_text(json.dumps(metadata, indent=2))

    return {
        "id": annotation_id,
        "scenario": req.scenario,
        "raster_name": req.raster_name,
        "png_file": str(png_path.name),
        "mask_file": str(mask_path.name),
    }


@app.get("/annotations/{raster_name}")
async def list_annotations(raster_name: str, scenario: str | None = None):
    """List saved annotations for a raster, optionally filtered by scenario."""
    base_dir = ANNOTATIONS_DIR / raster_name
    if not base_dir.exists():
        return {"annotations": []}

    annotations = []
    dirs = [base_dir / scenario] if scenario else [d for d in base_dir.iterdir() if d.is_dir()]

    for d in dirs:
        if not d.exists():
            continue
        for meta_file in sorted(d.glob("*_meta.json")):
            annotations.append(json.loads(meta_file.read_text()))

    return {"annotations": annotations}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
