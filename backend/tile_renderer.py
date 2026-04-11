"""Core tile rendering logic for raster files."""

import io
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import rioxarray  # noqa: F401 (activates rio accessor)
import xarray as xr
from PIL import Image
from rasterio.transform import from_bounds
from shapely.geometry import Polygon, mapping

WEB_MERCATOR_BOUNDS = (
    -20037508.342789244, -20037508.342789244,
    20037508.342789244, 20037508.342789244,
)


@dataclass
class RasterDataset:
    """A single loaded raster ready for tile serving."""

    path: str
    data: xr.DataArray
    min_value: int
    max_value: int
    width: int
    height: int
    bounds: list

@dataclass
class RasterRegistry:
    """Registry of loaded raster datasets keyed by name."""

    _datasets: dict[str, RasterDataset] = field(default_factory=dict)

    def load(self, name: str, file_path: str) -> RasterDataset:
        """Load a raster file, reproject to EPSG:3857, and register it."""
        ds = xr.open_dataset(file_path)
        da = ds.band_data if "band_data" in ds else ds[list(ds.data_vars)[0]]
        da = da.rio.reproject("EPSG:3857")
        # da = da.astype(np.int32)
        # da = da.rio.write_nodata(-9999, inplace=True)

        height, width = da.values[0].shape
        min_value = int(da.min())
        max_value = int(da.max())
        bounds = da.rio.bounds()

        dataset = RasterDataset(
            path=file_path,
            data=da,
            min_value=min_value,
            max_value=max_value,
            width=width,
            height=height,
            bounds=bounds
        )
        self._datasets[name] = dataset
        return dataset

    def get(self, name: str) -> RasterDataset | None:
        return self._datasets.get(name)

    def remove(self, name: str) -> bool:
        return self._datasets.pop(name, None) is not None

    def list_all(self) -> list[str]:
        return list(self._datasets.keys())

    def info(self, name: str) -> dict | None:
        ds = self.get(name)
        if ds is None:
            return None
        return {
            "name": name,
            "path": ds.path,
            "width": ds.width,
            "height": ds.height,
            "min_value": ds.min_value,
            "max_value": ds.max_value,
            "bounds": ds.bounds
        }


def st_tile_envelope(
    zoom: int, x: int, y: int,
    bounds: tuple[float, float, float, float] = WEB_MERCATOR_BOUNDS,
    margin: float = 0,
) -> tuple[float, float, float, float]:
    """Compute the geographic envelope for a tile at (z, x, y).

    Returns (xmin, ymin, xmax, ymax).
    """
    world_tile_size = 2 ** min(zoom, 31)
    xmin, ymin, xmax, ymax = bounds
    bounds_width = xmax - xmin
    bounds_height = ymax - ymin

    if bounds_width <= 0 or bounds_height <= 0:
        raise ValueError("Geometric bounds are too small")
    if zoom < 0 or zoom >= 32:
        raise ValueError("Invalid tile zoom value")
    if x < 0 or x >= world_tile_size:
        raise ValueError("Invalid tile x value")
    if y < 0 or y >= world_tile_size:
        raise ValueError("Invalid tile y value")

    tile_geo_size_x = bounds_width / world_tile_size
    tile_geo_size_y = bounds_height / world_tile_size

    margin = max(-0.5, min(0.5, margin))

    x1 = xmin + tile_geo_size_x * (x - margin)
    x2 = xmin + tile_geo_size_x * (x + 1 + margin)
    y1 = ymax - tile_geo_size_y * (y + 1 + margin)
    y2 = ymax - tile_geo_size_y * (y - margin)

    y1 = max(y1, ymin)
    y2 = min(y2, ymax)

    return (x1, y1, x2, y2)


def _normalize(arr: np.ndarray, min_val: int, max_val: int) -> np.ndarray:
    return ((arr - min_val) / (max_val - min_val) * 255)


def _make_black_transparent(image: Image.Image) -> Image.Image:
    """Set alpha to 0 for black (no-data) pixels."""
    arr = np.array(image)
    black = (arr[:, :, 0] == 0) & (arr[:, :, 1] == 0) & (arr[:, :, 2] == 0)
    arr[black, 3] = 0
    return Image.fromarray(arr)


def _boxes_intersect(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
) -> bool:
    """Check if two (xmin, ymin, xmax, ymax) bounding boxes overlap."""
    return a[0] < b[2] and a[2] > b[0] and a[1] < b[3] and a[3] > b[1]


def render_tile(dataset: RasterDataset, zoom: int, x: int, y: int) -> bytes | None:
    """Render a 256x256 PNG tile for the given dataset and tile coordinates.

    Returns PNG bytes, or None if no data falls within the tile bounds.
    """
    # Use global web mercator bounds for tile envelope (not dataset bounds)
    tile_bounds = st_tile_envelope(zoom, x, y)
    xmin, ymin, xmax, ymax = tile_bounds

    # Skip tiles that don't intersect the raster extent
    if not _boxes_intersect(tile_bounds, tuple(dataset.bounds)):
        return None

    try:
        clipped = dataset.data.rio.clip_box(
            minx=xmin, miny=ymin, maxx=xmax, maxy=ymax, auto_expand=True,
        )
        # Reproject to exact tile envelope so pixels align with the tile grid
        tile_transform = from_bounds(xmin, ymin, xmax, ymax, 256, 256)
        clipped = clipped.rio.reproject(
            clipped.rio.crs,
            shape=(256, 256),
            transform=tile_transform,
        )
    except Exception:
        return None

    data = clipped.values  # shape: (bands, H, W)
    num_bands = data.shape[0]

    if num_bands >= 3:
        # RGB: stack first 3 bands as (H, W, 3)
        rgb = np.stack([
            _normalize(data[0], dataset.min_value, dataset.max_value),
            _normalize(data[1], dataset.min_value, dataset.max_value),
            _normalize(data[2], dataset.min_value, dataset.max_value),
        ], axis=-1).astype(np.uint8)
        img = Image.fromarray(rgb, mode="RGB")
    else:
        # Single band grayscale
        arr = _normalize(data[0], dataset.min_value, dataset.max_value).astype(np.uint8)
        img = Image.fromarray(arr)

    img = img.convert("RGBA")
    img = _make_black_transparent(img)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def crop_raster_by_polygon(
    dataset: RasterDataset,
    polygon_coords: list[list[float]],
    output_dir: Path,
    annotation_id: str,
) -> tuple[Path, Path, list[float]]:
    """Crop a raster dataset using a polygon and save as PNG preview + binary mask.

    Args:
        dataset: The loaded raster dataset (already in EPSG:3857).
        polygon_coords: Ring of [x, y] coordinates in EPSG:3857.
        output_dir: Directory to write output files.
        annotation_id: Unique identifier for naming output files.

    Returns:
        (png_path, mask_path, bounds) where bounds is [minx, miny, maxx, maxy].
    """
    # Build shapely polygon and clip
    polygon = Polygon(polygon_coords)
    geojson_geom = [mapping(polygon)]

    clipped = dataset.data.rio.clip(geojson_geom, crs="EPSG:3857", drop=True)

    # Generate PNG preview
    data = clipped.values  # (bands, H, W)
    # Build mask before replacing NaN: 255 where data exists, 0 where nodata
    valid_mask = ~np.isnan(data[0])
    mask_arr = np.where(valid_mask, 255, 0).astype(np.uint8)

    data = np.nan_to_num(data, nan=0.0)
    num_bands = data.shape[0]

    if num_bands >= 3:
        rgb = np.stack([
            _normalize(data[0], dataset.min_value, dataset.max_value),
            _normalize(data[1], dataset.min_value, dataset.max_value),
            _normalize(data[2], dataset.min_value, dataset.max_value),
        ], axis=-1).astype(np.uint8)
        img = Image.fromarray(rgb, mode="RGB")
    else:
        arr = _normalize(data[0], dataset.min_value, dataset.max_value).astype(np.uint8)
        img = Image.fromarray(arr)

    img = img.convert("RGBA")
    img = _make_black_transparent(img)

    png_path = output_dir / f"{annotation_id}.png"
    img.save(str(png_path), format="PNG")

    # Save binary mask (white = inside polygon, black = outside)
    mask_img = Image.fromarray(mask_arr, mode="L")
    mask_path = output_dir / f"{annotation_id}_mask.png"
    mask_img.save(str(mask_path), format="PNG")

    bounds = list(clipped.rio.bounds())
    return png_path, mask_path, bounds
