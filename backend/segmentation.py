"""Segmentation model: lightweight U-Net, training, and georeferenced inference."""

import io
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import rioxarray  # noqa: F401
import torch
import torch.nn as nn
import torch.nn.functional as F
from PIL import Image
from rasterio.transform import from_bounds
from torch.utils.data import DataLoader, Dataset

from tile_renderer import RasterDataset

logger = logging.getLogger(__name__)

PATCH_SIZE = 128
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
MODELS_DIR = Path(__file__).parent.parent / "models"


# ── Dataset ──────────────────────────────────────────────────────────


class AnnotationDataset(Dataset):
    """Loads annotation PNG + mask pairs, resizes to fixed patch size."""

    def __init__(self, annotations_dir: Path, scenario: str, patch_size: int = PATCH_SIZE):
        self.patch_size = patch_size
        self.pairs: list[tuple[Path, Path]] = []

        scenario_dir = annotations_dir / scenario
        if not scenario_dir.exists():
            return

        for mask_path in sorted(scenario_dir.glob("*_mask.png")):
            img_id = mask_path.name.replace("_mask.png", "")
            img_path = scenario_dir / f"{img_id}.png"
            if img_path.exists():
                self.pairs.append((img_path, mask_path))

    def __len__(self) -> int:
        return len(self.pairs)

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, torch.Tensor]:
        img_path, mask_path = self.pairs[idx]

        # Load image as RGB (drop alpha)
        img = Image.open(img_path).convert("RGB")
        mask = Image.open(mask_path).convert("L")

        # Resize to fixed patch size
        img = img.resize((self.patch_size, self.patch_size), Image.BILINEAR)
        mask = mask.resize((self.patch_size, self.patch_size), Image.NEAREST)

        # To tensors: image [0,1] float, mask binary {0,1}
        img_arr = np.array(img, dtype=np.float32) / 255.0
        mask_arr = (np.array(mask, dtype=np.float32) / 255.0).clip(0, 1)
        mask_arr = (mask_arr > 0.5).astype(np.float32)

        img_tensor = torch.from_numpy(img_arr).permute(2, 0, 1)  # (3, H, W)
        mask_tensor = torch.from_numpy(mask_arr).unsqueeze(0)  # (1, H, W)

        return img_tensor, mask_tensor


# ── U-Net Model ──────────────────────────────────────────────────────


class ConvBlock(nn.Module):
    def __init__(self, in_ch: int, out_ch: int):
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv2d(in_ch, out_ch, 3, padding=1),
            nn.BatchNorm2d(out_ch),
            nn.ReLU(inplace=True),
            nn.Conv2d(out_ch, out_ch, 3, padding=1),
            nn.BatchNorm2d(out_ch),
            nn.ReLU(inplace=True),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.conv(x)


class UNetSmall(nn.Module):
    """Lightweight U-Net for binary segmentation (3-channel input, 1-channel output)."""

    def __init__(self, in_channels: int = 3, features: list[int] | None = None):
        super().__init__()
        if features is None:
            features = [32, 64, 128, 256]

        # Encoder
        self.encoders = nn.ModuleList()
        self.pools = nn.ModuleList()
        ch = in_channels
        for f in features:
            self.encoders.append(ConvBlock(ch, f))
            self.pools.append(nn.MaxPool2d(2))
            ch = f

        # Bottleneck
        self.bottleneck = ConvBlock(features[-1], features[-1] * 2)

        # Decoder
        self.upconvs = nn.ModuleList()
        self.decoders = nn.ModuleList()
        rev = list(reversed(features))
        ch = features[-1] * 2
        for f in rev:
            self.upconvs.append(nn.ConvTranspose2d(ch, f, 2, stride=2))
            self.decoders.append(ConvBlock(f * 2, f))
            ch = f

        self.head = nn.Conv2d(features[0], 1, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        skips = []
        for enc, pool in zip(self.encoders, self.pools):
            x = enc(x)
            skips.append(x)
            x = pool(x)

        x = self.bottleneck(x)

        for upconv, dec, skip in zip(self.upconvs, self.decoders, reversed(skips)):
            x = upconv(x)
            # Handle size mismatch from odd dimensions
            if x.shape != skip.shape:
                x = F.interpolate(x, size=skip.shape[2:], mode="bilinear", align_corners=False)
            x = torch.cat([x, skip], dim=1)
            x = dec(x)

        return self.head(x)


# ── Training ─────────────────────────────────────────────────────────


@dataclass
class TrainingProgress:
    """Mutable training state shared with the API layer."""
    running: bool = False
    epoch: int = 0
    total_epochs: int = 0
    loss: float = 0.0
    finished: bool = False
    error: str | None = None
    model_path: str | None = None


# Global registry of training jobs
_training_jobs: dict[str, TrainingProgress] = {}


def get_training_progress(job_id: str) -> TrainingProgress | None:
    return _training_jobs.get(job_id)


def train_model(
    raster_name: str,
    scenario: str,
    annotations_dir: Path,
    epochs: int = 50,
    lr: float = 1e-3,
    batch_size: int = 4,
    job_id: str = "",
) -> Path:
    """Train a U-Net on annotation patches. Returns path to saved model."""

    progress = TrainingProgress(running=True, total_epochs=epochs)
    _training_jobs[job_id] = progress

    try:
        dataset = AnnotationDataset(annotations_dir / raster_name, scenario)

        if len(dataset) == 0:
            raise ValueError(f"No annotations found for {raster_name}/{scenario}")

        logger.info("Training on %d annotation patches", len(dataset))

        loader = DataLoader(
            dataset,
            batch_size=batch_size,
            shuffle=True,
            num_workers=0,
            drop_last=False,
        )

        model = UNetSmall().to(DEVICE)
        optimizer = torch.optim.Adam(model.parameters(), lr=lr)
        criterion = nn.BCEWithLogitsLoss()

        model.train()
        for epoch in range(epochs):
            epoch_loss = 0.0
            count = 0
            for images, masks in loader:
                images = images.to(DEVICE)
                masks = masks.to(DEVICE)

                preds = model(images)
                loss = criterion(preds, masks)

                optimizer.zero_grad()
                loss.backward()
                optimizer.step()

                epoch_loss += loss.item() * images.size(0)
                count += images.size(0)

            avg_loss = epoch_loss / max(count, 1)
            progress.epoch = epoch + 1
            progress.loss = avg_loss
            logger.info("Epoch %d/%d — loss: %.4f", epoch + 1, epochs, avg_loss)

        # Save model
        out_dir = MODELS_DIR / raster_name / scenario
        out_dir.mkdir(parents=True, exist_ok=True)
        model_path = out_dir / "model.pt"
        torch.save(model.state_dict(), model_path)

        progress.finished = True
        progress.running = False
        progress.model_path = str(model_path)
        logger.info("Model saved to %s", model_path)
        return model_path

    except Exception as e:
        progress.error = str(e)
        progress.running = False
        raise


# ── Inference on full raster ─────────────────────────────────────────


def predict_raster(
    dataset: RasterDataset,
    model_path: Path,
    raster_name: str,
    scenario: str,
    patch_size: int = PATCH_SIZE,
    stride: int | None = None,
) -> Path:
    """Run sliding-window inference on the full raster and save georeferenced GeoTIFF.

    Returns the path to the output prediction GeoTIFF.
    """
    if stride is None:
        stride = patch_size // 2

    # Load model
    model = UNetSmall().to(DEVICE)
    model.load_state_dict(torch.load(model_path, map_location=DEVICE, weights_only=True))
    model.eval()

    da = dataset.data  # (bands, H, W) in EPSG:3857
    raw = da.values  # numpy (bands, H, W)
    raw = np.nan_to_num(raw, nan=0.0)
    num_bands, h, w = raw.shape

    # Normalize full raster to [0,1] using same min/max as tile renderer
    bands_norm = []
    for b in range(min(num_bands, 3)):
        band = raw[b].astype(np.float32)
        if dataset.max_value != dataset.min_value:
            band = (band - dataset.min_value) / (dataset.max_value - dataset.min_value)
        band = band.clip(0, 1)
        bands_norm.append(band)

    # If single band, replicate to 3 channels
    while len(bands_norm) < 3:
        bands_norm.append(bands_norm[0])

    full_img = np.stack(bands_norm, axis=0)  # (3, H, W)

    # Accumulator for predictions + count for averaging overlaps
    pred_sum = np.zeros((h, w), dtype=np.float32)
    pred_count = np.zeros((h, w), dtype=np.float32)

    logger.info("Running inference on %dx%d raster (patch=%d, stride=%d)", w, h, patch_size, stride)

    with torch.no_grad():
        for y0 in range(0, h, stride):
            for x0 in range(0, w, stride):
                y1 = min(y0 + patch_size, h)
                x1 = min(x0 + patch_size, w)
                # Adjust start if patch goes beyond edge
                y0_adj = max(0, y1 - patch_size)
                x0_adj = max(0, x1 - patch_size)

                patch = full_img[:, y0_adj:y1, x0_adj:x1]  # (3, ph, pw)
                ph, pw = patch.shape[1], patch.shape[2]

                # Resize to model input size
                patch_tensor = torch.from_numpy(patch).unsqueeze(0).to(DEVICE)
                patch_resized = F.interpolate(
                    patch_tensor, size=(patch_size, patch_size),
                    mode="bilinear", align_corners=False,
                )

                logits = model(patch_resized)
                prob = torch.sigmoid(logits)

                # Resize prediction back to actual patch size
                prob_resized = F.interpolate(
                    prob, size=(ph, pw),
                    mode="bilinear", align_corners=False,
                )
                prob_np = prob_resized.squeeze().cpu().numpy()

                pred_sum[y0_adj:y1, x0_adj:x1] += prob_np
                pred_count[y0_adj:y1, x0_adj:x1] += 1.0

    # Average overlapping predictions
    pred_count = np.maximum(pred_count, 1.0)
    pred_avg = pred_sum / pred_count

    # Binary mask at 0.5 threshold
    pred_binary = (pred_avg > 0.5).astype(np.uint8)

    # Save as georeferenced GeoTIFF using rioxarray
    import xarray as xr

    # Build coords for a single-band output, keeping only spatial dims from source
    spatial_dims = {k: v for k, v in da.coords.items() if k != "band"}
    pred_da = xr.DataArray(
        pred_binary[np.newaxis, :, :],  # (1, H, W)
        dims=da.dims,
        coords={"band": [1], **spatial_dims},
    )
    pred_da = pred_da.rio.write_crs(da.rio.crs)
    pred_da = pred_da.rio.write_transform(da.rio.transform())
    pred_da = pred_da.rio.write_nodata(0)

    out_dir = MODELS_DIR / raster_name / scenario
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "prediction.tif"
    pred_da.rio.to_raster(str(out_path), dtype="uint8")

    logger.info("Prediction saved to %s", out_path)
    return out_path
