"""Train a tiny convolutional autoencoder on exported map tensors."""

from __future__ import annotations

import argparse
import csv
import json
import random
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, random_split

from supmapai.ml.tensor_dataset import MapTensorDataset

DEFAULT_CHANNEL_WEIGHTS = [
    1.0,  # height_norm
    1.0,  # water_mask
    1.0,  # water_depth_norm
    1.0,  # land_mask
    1.0,  # land_passable_mask
    1.0,  # buildable_mask
    1.0,  # slope_norm
    8.0,  # spawn_heatmap
    6.0,  # mex_heatmap
    8.0,  # hydro_heatmap
    3.0,  # reclaim_density
    3.0,  # civilian_structure_density
]


@dataclass
class TrainConfig:
    tensor_manifest: str
    splits_csv: str | None
    out_dir: str
    epochs: int
    batch_size: int
    learning_rate: float
    latent_channels: int
    max_train_maps: int | None
    max_val_maps: int | None
    seed: int
    device: str
    use_default_channel_weights: bool


class TinyConvAutoencoder(nn.Module):
    def __init__(self, channels: int, latent_channels: int = 64) -> None:
        super().__init__()
        self.encoder = nn.Sequential(
            nn.Conv2d(channels, 32, kernel_size=3, stride=2, padding=1),
            nn.SiLU(),
            nn.Conv2d(32, 64, kernel_size=3, stride=2, padding=1),
            nn.SiLU(),
            nn.Conv2d(64, latent_channels, kernel_size=3, stride=2, padding=1),
            nn.SiLU(),
        )
        self.decoder = nn.Sequential(
            nn.ConvTranspose2d(
                latent_channels,
                64,
                kernel_size=4,
                stride=2,
                padding=1,
            ),
            nn.SiLU(),
            nn.ConvTranspose2d(64, 32, kernel_size=4, stride=2, padding=1),
            nn.SiLU(),
            nn.ConvTranspose2d(32, channels, kernel_size=4, stride=2, padding=1),
            nn.Sigmoid(),
        )

    def forward(self, tensor: torch.Tensor) -> torch.Tensor:
        return self.decoder(self.encoder(tensor))


def _seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def _make_loaders(
    tensor_manifest: Path,
    splits_csv: Path | None,
    batch_size: int,
    max_train_maps: int | None,
    max_val_maps: int | None,
    seed: int,
) -> tuple[DataLoader[dict[str, Any]], DataLoader[dict[str, Any]]]:
    if splits_csv is not None:
        train_dataset = MapTensorDataset(
            tensor_manifest=tensor_manifest,
            splits_csv=splits_csv,
            split="train",
            max_maps=max_train_maps,
        )
        val_dataset = MapTensorDataset(
            tensor_manifest=tensor_manifest,
            splits_csv=splits_csv,
            split="val",
            max_maps=max_val_maps,
        )
    else:
        max_maps = None
        if max_train_maps is not None or max_val_maps is not None:
            max_maps = (max_train_maps or 0) + (max_val_maps or 0)
        dataset = MapTensorDataset(tensor_manifest=tensor_manifest, max_maps=max_maps)
        if max_train_maps is not None and max_val_maps is not None:
            train_count = min(max_train_maps, max(1, len(dataset) - 1))
            val_count = min(max_val_maps, max(1, len(dataset) - train_count))
        else:
            train_count = max(1, int(len(dataset) * 0.8))
            val_count = max(1, len(dataset) - train_count)
        if train_count + val_count > len(dataset):
            val_count = max(1, len(dataset) - train_count)
        train_dataset, val_dataset = random_split(
            dataset,
            [train_count, val_count],
            generator=torch.Generator().manual_seed(seed),
        )
    if len(train_dataset) == 0 or len(val_dataset) == 0:
        raise ValueError(
            f"empty train/val dataset: train={len(train_dataset)} val={len(val_dataset)}"
        )
    train_loader = DataLoader(
        train_dataset,
        batch_size=batch_size,
        shuffle=True,
        num_workers=0,
        pin_memory=torch.cuda.is_available(),
    )
    val_loader = DataLoader(
        val_dataset,
        batch_size=batch_size,
        shuffle=False,
        num_workers=0,
        pin_memory=torch.cuda.is_available(),
    )
    return train_loader, val_loader


def _batch_tensor(batch: dict[str, Any], device: torch.device) -> torch.Tensor:
    return batch["tensor"].to(device=device, dtype=torch.float32, non_blocking=True)


def _weighted_mse(
    reconstruction: torch.Tensor,
    target: torch.Tensor,
    channel_weights: torch.Tensor | None,
) -> torch.Tensor:
    loss = (reconstruction - target).square().mean(dim=(0, 2, 3))
    if channel_weights is not None:
        weights = channel_weights.to(device=loss.device, dtype=loss.dtype)
        if weights.numel() != loss.numel():
            raise ValueError(
                f"channel weight count {weights.numel()} != channel count {loss.numel()}"
            )
        loss = loss * weights
        return loss.sum() / weights.sum()
    return loss.mean()


def _run_epoch(
    model: nn.Module,
    loader: DataLoader[dict[str, Any]],
    optimizer: torch.optim.Optimizer | None,
    device: torch.device,
    channel_weights: torch.Tensor | None,
) -> float:
    training = optimizer is not None
    model.train(training)
    losses = []
    for batch in loader:
        tensor = _batch_tensor(batch, device)
        with torch.set_grad_enabled(training):
            recon = model(tensor)
            loss = _weighted_mse(recon, tensor, channel_weights)
            if training:
                optimizer.zero_grad(set_to_none=True)
                loss.backward()
                optimizer.step()
        losses.append(float(loss.detach().cpu()))
    return sum(losses) / max(len(losses), 1)


def _write_loss_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["epoch", "train_loss", "val_loss"])
        writer.writeheader()
        writer.writerows(rows)


def _channels_from_manifest(path: Path, fallback_count: int) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            tensor_path = row.get("tensor_path", "")
            if tensor_path:
                return [str(item) for item in np.load(tensor_path)["channels"]]
    return [f"channel_{index:02d}" for index in range(fallback_count)]


def _save_reconstructions(
    model: nn.Module,
    loader: DataLoader[dict[str, Any]],
    device: torch.device,
    out_dir: Path,
    max_items: int,
    channels: list[str],
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    model.eval()
    saved = 0
    with torch.no_grad():
        for batch in loader:
            tensor = _batch_tensor(batch, device)
            recon = model(tensor).detach().cpu().numpy()
            original = tensor.detach().cpu().numpy()
            map_ids = batch["map_id"]
            map_dirs = batch["map_dir"]
            for index in range(recon.shape[0]):
                if saved >= max_items:
                    return
                out_path = out_dir / f"{map_ids[index]}.reconstruction.npz"
                np.savez_compressed(
                    out_path,
                    original=original[index].astype(np.float32),
                    reconstruction=recon[index].astype(np.float32),
                    channels=np.array(channels),
                    map_id=np.array(map_ids[index]),
                    map_dir=np.array(map_dirs[index]),
                )
                saved += 1


def train(config: TrainConfig) -> dict[str, Any]:
    _seed_everything(config.seed)
    device = torch.device(config.device)
    train_loader, val_loader = _make_loaders(
        tensor_manifest=Path(config.tensor_manifest),
        splits_csv=Path(config.splits_csv) if config.splits_csv else None,
        batch_size=config.batch_size,
        max_train_maps=config.max_train_maps,
        max_val_maps=config.max_val_maps,
        seed=config.seed,
    )
    sample = next(iter(train_loader))["tensor"]
    channel_count = int(sample.shape[1])
    channel_weights = None
    if config.use_default_channel_weights:
        channel_weights = torch.tensor(DEFAULT_CHANNEL_WEIGHTS[:channel_count], dtype=torch.float32)
    model = TinyConvAutoencoder(
        channels=channel_count,
        latent_channels=config.latent_channels,
    ).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=config.learning_rate)

    out_dir = Path(config.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "config.json").write_text(json.dumps(asdict(config), indent=2), encoding="utf-8")
    loss_rows = []
    best_val = float("inf")
    for epoch in range(1, config.epochs + 1):
        train_loss = _run_epoch(model, train_loader, optimizer, device, channel_weights)
        val_loss = _run_epoch(model, val_loader, None, device, channel_weights)
        row = {
            "epoch": epoch,
            "train_loss": round(train_loss, 8),
            "val_loss": round(val_loss, 8),
        }
        loss_rows.append(row)
        _write_loss_csv(out_dir / "losses.csv", loss_rows)
        if val_loss < best_val:
            best_val = val_loss
            torch.save(
                {
                    "model_state": model.state_dict(),
                    "config": asdict(config),
                    "epoch": epoch,
                    "val_loss": val_loss,
                },
                out_dir / "best.pt",
            )
        print(f"epoch={epoch} train_loss={train_loss:.6f} val_loss={val_loss:.6f}")

    channels = _channels_from_manifest(Path(config.tensor_manifest), channel_count)
    _save_reconstructions(
        model,
        val_loader,
        device,
        out_dir / "reconstructions",
        max_items=8,
        channels=channels,
    )
    return {
        "best_val_loss": best_val,
        "epochs": config.epochs,
        "train_batches": len(train_loader),
        "val_batches": len(val_loader),
        "channel_count": channel_count,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train a tiny tensor autoencoder baseline.")
    parser.add_argument("--tensor-manifest", required=True, type=Path)
    parser.add_argument("--splits-csv", type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--epochs", default=3, type=int)
    parser.add_argument("--batch-size", default=8, type=int)
    parser.add_argument("--learning-rate", default=1e-3, type=float)
    parser.add_argument("--latent-channels", default=64, type=int)
    parser.add_argument("--max-train-maps", type=int)
    parser.add_argument("--max-val-maps", type=int)
    parser.add_argument("--seed", default=20260711, type=int)
    parser.add_argument(
        "--no-default-channel-weights",
        action="store_true",
        help="Use plain unweighted MSE instead of sparse-channel-aware weighted MSE.",
    )
    parser.add_argument(
        "--device",
        default="cuda" if torch.cuda.is_available() else "cpu",
        choices=["cuda", "cpu"],
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = TrainConfig(
        tensor_manifest=str(args.tensor_manifest),
        splits_csv=str(args.splits_csv) if args.splits_csv else None,
        out_dir=str(args.out_dir),
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.learning_rate,
        latent_channels=args.latent_channels,
        max_train_maps=args.max_train_maps,
        max_val_maps=args.max_val_maps,
        seed=args.seed,
        device=args.device,
        use_default_channel_weights=not args.no_default_channel_weights,
    )
    summary = train(config)
    Path(args.out_dir, "summary.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
