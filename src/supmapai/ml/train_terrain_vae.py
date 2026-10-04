"""Train a small terrain/water VAE and sample generated structural tensors."""

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

DEFAULT_TERRAIN_CHANNELS = [0, 1, 2]
DEFAULT_TERRAIN_WEIGHTS = [1.0, 2.0, 1.5]


@dataclass
class TrainConfig:
    tensor_manifest: str
    splits_csv: str | None
    out_dir: str
    epochs: int
    batch_size: int
    learning_rate: float
    base_channels: int
    latent_channels: int
    kl_weight: float
    max_train_maps: int | None
    max_val_maps: int | None
    sample_count: int
    seed: int
    device: str
    terrain_channels: list[int]


class _UpsampleBlock(nn.Module):
    def __init__(self, in_channels: int, out_channels: int) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Upsample(scale_factor=2, mode="bilinear", align_corners=False),
            nn.Conv2d(in_channels, out_channels, kernel_size=3, padding=1),
            nn.SiLU(),
            nn.Conv2d(out_channels, out_channels, kernel_size=3, padding=1),
            nn.SiLU(),
        )

    def forward(self, tensor: torch.Tensor) -> torch.Tensor:
        return self.net(tensor)


class TerrainVAE(nn.Module):
    """A small fully-convolutional VAE for 256x256 terrain-style channels."""

    def __init__(self, in_channels: int, base_channels: int, latent_channels: int) -> None:
        super().__init__()
        self.encoder = nn.Sequential(
            nn.Conv2d(in_channels, base_channels, kernel_size=3, stride=2, padding=1),
            nn.SiLU(),
            nn.Conv2d(base_channels, base_channels * 2, kernel_size=3, stride=2, padding=1),
            nn.SiLU(),
            nn.Conv2d(base_channels * 2, base_channels * 4, kernel_size=3, stride=2, padding=1),
            nn.SiLU(),
            nn.Conv2d(base_channels * 4, base_channels * 4, kernel_size=3, stride=2, padding=1),
            nn.SiLU(),
        )
        self.to_mu = nn.Conv2d(base_channels * 4, latent_channels, kernel_size=1)
        self.to_logvar = nn.Conv2d(base_channels * 4, latent_channels, kernel_size=1)
        self.decoder = nn.Sequential(
            nn.Conv2d(latent_channels, base_channels * 4, kernel_size=3, padding=1),
            nn.SiLU(),
            _UpsampleBlock(base_channels * 4, base_channels * 4),
            _UpsampleBlock(base_channels * 4, base_channels * 2),
            _UpsampleBlock(base_channels * 2, base_channels),
            _UpsampleBlock(base_channels, base_channels),
            nn.Conv2d(base_channels, in_channels, kernel_size=3, padding=1),
            nn.Sigmoid(),
        )

    def encode(self, tensor: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        encoded = self.encoder(tensor)
        return self.to_mu(encoded), self.to_logvar(encoded).clamp(min=-8.0, max=8.0)

    def reparameterize(self, mu: torch.Tensor, logvar: torch.Tensor) -> torch.Tensor:
        if not self.training:
            return mu
        std = torch.exp(0.5 * logvar)
        return mu + torch.randn_like(std) * std

    def decode(self, latent: torch.Tensor) -> torch.Tensor:
        return self.decoder(latent)

    def forward(self, tensor: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        mu, logvar = self.encode(tensor)
        return self.decode(self.reparameterize(mu, logvar)), mu, logvar


def _seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


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
        if len(dataset) < 2:
            raise ValueError("at least two tensors are required for train/validation split")
        train_count = max_train_maps or max(1, int(len(dataset) * 0.8))
        train_count = min(train_count, max(1, len(dataset) - 1))
        val_count = max_val_maps or max(1, len(dataset) - train_count)
        val_count = min(val_count, max(1, len(dataset) - train_count))
        train_dataset, val_dataset = random_split(
            dataset,
            [train_count, val_count],
            generator=torch.Generator().manual_seed(seed),
        )
    if len(train_dataset) == 0 or len(val_dataset) == 0:
        raise ValueError(
            f"empty train/val dataset: train={len(train_dataset)} val={len(val_dataset)}"
        )
    return (
        DataLoader(
            train_dataset,
            batch_size=batch_size,
            shuffle=True,
            num_workers=0,
            pin_memory=torch.cuda.is_available(),
        ),
        DataLoader(
            val_dataset,
            batch_size=batch_size,
            shuffle=False,
            num_workers=0,
            pin_memory=torch.cuda.is_available(),
        ),
    )


def _select_terrain(
    batch: dict[str, Any],
    device: torch.device,
    channels: list[int],
) -> torch.Tensor:
    tensor = batch["tensor"].to(device=device, dtype=torch.float32, non_blocking=True)
    return tensor[:, channels]


def _loss(
    reconstruction: torch.Tensor,
    target: torch.Tensor,
    mu: torch.Tensor,
    logvar: torch.Tensor,
    channel_weights: torch.Tensor,
    kl_weight: float,
) -> tuple[torch.Tensor, dict[str, float]]:
    weights = channel_weights.to(device=target.device, dtype=target.dtype).view(1, -1, 1, 1)
    if target.shape[1] >= 3:
        continuous_indexes = [index for index in range(target.shape[1]) if index != 1]
        continuous_loss = (
            (reconstruction[:, continuous_indexes] - target[:, continuous_indexes]).square()
            * weights[:, continuous_indexes]
        ).mean()
        water_loss = nn.functional.binary_cross_entropy(
            reconstruction[:, 1:2].clamp(min=1e-6, max=1.0 - 1e-6),
            target[:, 1:2],
        )
        recon_loss = continuous_loss + water_loss * float(channel_weights[1])
    else:
        recon_loss = ((reconstruction - target).square() * weights).mean()
    kl = -0.5 * torch.mean(1.0 + logvar - mu.square() - logvar.exp())
    total = recon_loss + kl * kl_weight
    return total, {
        "reconstruction": float(recon_loss.detach().cpu()),
        "kl": float(kl.detach().cpu()),
    }


def _run_epoch(
    model: TerrainVAE,
    loader: DataLoader[dict[str, Any]],
    optimizer: torch.optim.Optimizer | None,
    device: torch.device,
    terrain_channels: list[int],
    channel_weights: torch.Tensor,
    kl_weight: float,
) -> dict[str, float]:
    training = optimizer is not None
    model.train(training)
    totals = {"loss": 0.0, "reconstruction": 0.0, "kl": 0.0}
    count = 0
    for batch in loader:
        target = _select_terrain(batch, device, terrain_channels)
        with torch.set_grad_enabled(training):
            reconstruction, mu, logvar = model(target)
            loss, parts = _loss(reconstruction, target, mu, logvar, channel_weights, kl_weight)
            if training:
                optimizer.zero_grad(set_to_none=True)
                loss.backward()
                optimizer.step()
        totals["loss"] += float(loss.detach().cpu())
        totals["reconstruction"] += parts["reconstruction"]
        totals["kl"] += parts["kl"]
        count += 1
    return {key: value / max(count, 1) for key, value in totals.items()}


def _channels_from_manifest(path: Path, selected: list[int]) -> list[str]:
    for row in _read_csv(path):
        tensor_path = row.get("tensor_path", "")
        if tensor_path:
            channels = [str(item) for item in np.load(tensor_path)["channels"]]
            return [channels[index] for index in selected]
    return [f"channel_{index:02d}" for index in selected]


def _write_loss_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "epoch",
                "train_loss",
                "train_reconstruction",
                "train_kl",
                "val_loss",
                "val_reconstruction",
                "val_kl",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)


def _save_reconstructions(
    model: TerrainVAE,
    loader: DataLoader[dict[str, Any]],
    device: torch.device,
    out_dir: Path,
    max_items: int,
    channels: list[str],
    terrain_channels: list[int],
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    model.eval()
    saved = 0
    with torch.no_grad():
        for batch in loader:
            target = _select_terrain(batch, device, terrain_channels)
            reconstruction, _, _ = model(target)
            target_np = target.detach().cpu().numpy()
            recon_np = reconstruction.detach().cpu().numpy()
            map_ids = batch["map_id"]
            map_dirs = batch["map_dir"]
            for index in range(recon_np.shape[0]):
                if saved >= max_items:
                    return
                np.savez_compressed(
                    out_dir / f"{map_ids[index]}.terrain_reconstruction.npz",
                    original=target_np[index].astype(np.float32),
                    reconstruction=recon_np[index].astype(np.float32),
                    channels=np.array(channels),
                    map_id=np.array(map_ids[index]),
                    map_dir=np.array(map_dirs[index]),
                )
                saved += 1


def _save_samples(
    model: TerrainVAE,
    out_dir: Path,
    sample_count: int,
    channels: list[str],
    latent_channels: int,
    device: torch.device,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    model.eval()
    with torch.no_grad():
        latent = torch.randn(sample_count, latent_channels, 16, 16, device=device)
        samples = model.decode(latent).detach().cpu().numpy()
    for index, sample in enumerate(samples):
        np.savez_compressed(
            out_dir / f"terrain_sample_{index:04d}.generated.npz",
            tensor=sample.astype(np.float32),
            channels=np.array(channels),
        )


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
    model = TerrainVAE(
        in_channels=len(config.terrain_channels),
        base_channels=config.base_channels,
        latent_channels=config.latent_channels,
    ).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=config.learning_rate)
    weights = DEFAULT_TERRAIN_WEIGHTS[: len(config.terrain_channels)]
    if len(weights) < len(config.terrain_channels):
        weights.extend([1.0] * (len(config.terrain_channels) - len(weights)))
    channel_weights = torch.tensor(weights, dtype=torch.float32)
    channels = _channels_from_manifest(Path(config.tensor_manifest), config.terrain_channels)

    out_dir = Path(config.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "config.json").write_text(json.dumps(asdict(config), indent=2), encoding="utf-8")

    loss_rows = []
    best_val = float("inf")
    for epoch in range(1, config.epochs + 1):
        train_metrics = _run_epoch(
            model,
            train_loader,
            optimizer,
            device,
            config.terrain_channels,
            channel_weights,
            config.kl_weight,
        )
        val_metrics = _run_epoch(
            model,
            val_loader,
            None,
            device,
            config.terrain_channels,
            channel_weights,
            config.kl_weight,
        )
        loss_rows.append(
            {
                "epoch": epoch,
                "train_loss": round(train_metrics["loss"], 8),
                "train_reconstruction": round(train_metrics["reconstruction"], 8),
                "train_kl": round(train_metrics["kl"], 8),
                "val_loss": round(val_metrics["loss"], 8),
                "val_reconstruction": round(val_metrics["reconstruction"], 8),
                "val_kl": round(val_metrics["kl"], 8),
            }
        )
        _write_loss_csv(out_dir / "losses.csv", loss_rows)
        if val_metrics["loss"] < best_val:
            best_val = val_metrics["loss"]
            torch.save(
                {
                    "model_state": model.state_dict(),
                    "config": asdict(config),
                    "epoch": epoch,
                    "val_loss": best_val,
                    "channels": channels,
                },
                out_dir / "best.pt",
            )
        print(
            "epoch="
            f"{epoch} train_loss={train_metrics['loss']:.6f} "
            f"val_loss={val_metrics['loss']:.6f} val_kl={val_metrics['kl']:.6f}"
        )

    _save_reconstructions(
        model,
        val_loader,
        device,
        out_dir / "reconstructions",
        max_items=8,
        channels=channels,
        terrain_channels=config.terrain_channels,
    )
    _save_samples(
        model,
        out_dir / "samples",
        sample_count=config.sample_count,
        channels=channels,
        latent_channels=config.latent_channels,
        device=device,
    )
    return {
        "best_val_loss": best_val,
        "epochs": config.epochs,
        "train_batches": len(train_loader),
        "val_batches": len(val_loader),
        "channels": channels,
        "sample_count": config.sample_count,
    }


def _parse_channel_indexes(value: str) -> list[int]:
    return [int(part.strip()) for part in value.split(",") if part.strip()]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train a small terrain/water VAE generator.")
    parser.add_argument("--tensor-manifest", required=True, type=Path)
    parser.add_argument("--splits-csv", type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--epochs", default=5, type=int)
    parser.add_argument("--batch-size", default=8, type=int)
    parser.add_argument("--learning-rate", default=1e-3, type=float)
    parser.add_argument("--base-channels", default=32, type=int)
    parser.add_argument("--latent-channels", default=32, type=int)
    parser.add_argument("--kl-weight", default=1e-4, type=float)
    parser.add_argument("--max-train-maps", type=int)
    parser.add_argument("--max-val-maps", type=int)
    parser.add_argument("--sample-count", default=8, type=int)
    parser.add_argument("--seed", default=20260712, type=int)
    parser.add_argument(
        "--terrain-channels",
        default=",".join(str(index) for index in DEFAULT_TERRAIN_CHANNELS),
        help=(
            "Comma-separated channel indexes to train on. "
            "Default: height, water mask, water depth."
        ),
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
        base_channels=args.base_channels,
        latent_channels=args.latent_channels,
        kl_weight=args.kl_weight,
        max_train_maps=args.max_train_maps,
        max_val_maps=args.max_val_maps,
        sample_count=args.sample_count,
        seed=args.seed,
        device=args.device,
        terrain_channels=_parse_channel_indexes(args.terrain_channels),
    )
    summary = train(config)
    Path(args.out_dir, "summary.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
