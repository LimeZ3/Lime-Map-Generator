"""Train a small DDPM terrain/water generator."""

from __future__ import annotations

import argparse
import csv
import json
import math
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


@dataclass
class TrainConfig:
    tensor_manifest: str
    splits_csv: str | None
    out_dir: str
    epochs: int
    batch_size: int
    learning_rate: float
    base_channels: int
    time_dim: int
    diffusion_steps: int
    max_train_maps: int | None
    max_val_maps: int | None
    sample_count: int
    seed: int
    device: str
    terrain_channels: list[int]


class SinusoidalTimeEmbedding(nn.Module):
    def __init__(self, dim: int) -> None:
        super().__init__()
        self.dim = dim

    def forward(self, timesteps: torch.Tensor) -> torch.Tensor:
        half = self.dim // 2
        frequencies = torch.exp(
            -math.log(10000.0)
            * torch.arange(half, device=timesteps.device, dtype=torch.float32)
            / max(half - 1, 1)
        )
        angles = timesteps.float()[:, None] * frequencies[None, :]
        embedding = torch.cat([torch.sin(angles), torch.cos(angles)], dim=1)
        if self.dim % 2 == 1:
            embedding = nn.functional.pad(embedding, (0, 1))
        return embedding


class ResBlock(nn.Module):
    def __init__(self, in_channels: int, out_channels: int, time_dim: int) -> None:
        super().__init__()
        self.conv1 = nn.Conv2d(in_channels, out_channels, kernel_size=3, padding=1)
        self.conv2 = nn.Conv2d(out_channels, out_channels, kernel_size=3, padding=1)
        self.time = nn.Linear(time_dim, out_channels)
        self.skip = (
            nn.Conv2d(in_channels, out_channels, kernel_size=1)
            if in_channels != out_channels
            else nn.Identity()
        )
        self.act = nn.SiLU()

    def forward(self, tensor: torch.Tensor, time_embedding: torch.Tensor) -> torch.Tensor:
        hidden = self.act(self.conv1(tensor))
        hidden = hidden + self.time(time_embedding)[:, :, None, None]
        hidden = self.act(self.conv2(hidden))
        return hidden + self.skip(tensor)


class TinyTerrainUNet(nn.Module):
    def __init__(self, channels: int, base_channels: int, time_dim: int) -> None:
        super().__init__()
        self.time_mlp = nn.Sequential(
            SinusoidalTimeEmbedding(time_dim),
            nn.Linear(time_dim, time_dim),
            nn.SiLU(),
            nn.Linear(time_dim, time_dim),
        )
        self.enc1 = ResBlock(channels, base_channels, time_dim)
        self.down1 = nn.Conv2d(base_channels, base_channels * 2, kernel_size=3, stride=2, padding=1)
        self.enc2 = ResBlock(base_channels * 2, base_channels * 2, time_dim)
        self.down2 = nn.Conv2d(
            base_channels * 2,
            base_channels * 4,
            kernel_size=3,
            stride=2,
            padding=1,
        )
        self.mid = ResBlock(base_channels * 4, base_channels * 4, time_dim)
        self.up2 = nn.Sequential(
            nn.Upsample(scale_factor=2, mode="bilinear", align_corners=False),
            nn.Conv2d(base_channels * 4, base_channels * 2, kernel_size=3, padding=1),
            nn.SiLU(),
        )
        self.dec2 = ResBlock(base_channels * 4, base_channels * 2, time_dim)
        self.up1 = nn.Sequential(
            nn.Upsample(scale_factor=2, mode="bilinear", align_corners=False),
            nn.Conv2d(base_channels * 2, base_channels, kernel_size=3, padding=1),
            nn.SiLU(),
        )
        self.dec1 = ResBlock(base_channels * 2, base_channels, time_dim)
        self.out = nn.Conv2d(base_channels, channels, kernel_size=3, padding=1)

    def forward(self, tensor: torch.Tensor, timesteps: torch.Tensor) -> torch.Tensor:
        time_embedding = self.time_mlp(timesteps)
        enc1 = self.enc1(tensor, time_embedding)
        enc2 = self.enc2(self.down1(enc1), time_embedding)
        mid = self.mid(self.down2(enc2), time_embedding)
        dec2 = self.up2(mid)
        dec2 = self.dec2(torch.cat([dec2, enc2], dim=1), time_embedding)
        dec1 = self.up1(dec2)
        dec1 = self.dec1(torch.cat([dec1, enc1], dim=1), time_embedding)
        return self.out(dec1)


class DiffusionSchedule:
    def __init__(self, steps: int, device: torch.device) -> None:
        betas = torch.linspace(1e-4, 0.02, steps, device=device)
        alphas = 1.0 - betas
        alphas_cumprod = torch.cumprod(alphas, dim=0)
        self.steps = steps
        self.betas = betas
        self.alphas = alphas
        self.alphas_cumprod = alphas_cumprod
        self.sqrt_alphas_cumprod = torch.sqrt(alphas_cumprod)
        self.sqrt_one_minus_alphas_cumprod = torch.sqrt(1.0 - alphas_cumprod)

    def q_sample(
        self,
        clean: torch.Tensor,
        timesteps: torch.Tensor,
        noise: torch.Tensor,
    ) -> torch.Tensor:
        signal = self.sqrt_alphas_cumprod[timesteps].view(-1, 1, 1, 1)
        noise_scale = self.sqrt_one_minus_alphas_cumprod[timesteps].view(-1, 1, 1, 1)
        return signal * clean + noise_scale * noise


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
    return tensor[:, channels] * 2.0 - 1.0


def _run_epoch(
    model: TinyTerrainUNet,
    loader: DataLoader[dict[str, Any]],
    optimizer: torch.optim.Optimizer | None,
    schedule: DiffusionSchedule,
    device: torch.device,
    terrain_channels: list[int],
) -> float:
    training = optimizer is not None
    model.train(training)
    losses = []
    for batch in loader:
        clean = _select_terrain(batch, device, terrain_channels)
        noise = torch.randn_like(clean)
        timesteps = torch.randint(0, schedule.steps, (clean.shape[0],), device=device)
        noisy = schedule.q_sample(clean, timesteps, noise)
        with torch.set_grad_enabled(training):
            predicted_noise = model(noisy, timesteps)
            loss = nn.functional.mse_loss(predicted_noise, noise)
            if training:
                optimizer.zero_grad(set_to_none=True)
                loss.backward()
                optimizer.step()
        losses.append(float(loss.detach().cpu()))
    return sum(losses) / max(len(losses), 1)


def _read_first_channels(path: Path, selected: list[int]) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            tensor_path = row.get("tensor_path", "")
            if tensor_path:
                channels = [str(item) for item in np.load(tensor_path)["channels"]]
                return [channels[index] for index in selected]
    return [f"channel_{index:02d}" for index in selected]


def _write_loss_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["epoch", "train_loss", "val_loss"])
        writer.writeheader()
        writer.writerows(rows)


@torch.no_grad()
def _sample(
    model: TinyTerrainUNet,
    schedule: DiffusionSchedule,
    sample_count: int,
    channels: list[str],
    out_dir: Path,
    device: torch.device,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    model.eval()
    tensor = torch.randn(sample_count, len(channels), 256, 256, device=device)
    for step in reversed(range(schedule.steps)):
        timesteps = torch.full((sample_count,), step, device=device, dtype=torch.long)
        predicted_noise = model(tensor, timesteps)
        beta = schedule.betas[step]
        alpha = schedule.alphas[step]
        alpha_cumprod = schedule.alphas_cumprod[step]
        tensor = (tensor - beta / torch.sqrt(1.0 - alpha_cumprod) * predicted_noise) / torch.sqrt(
            alpha
        )
        if step > 0:
            tensor = tensor + torch.sqrt(beta) * torch.randn_like(tensor)
    samples = torch.clamp((tensor + 1.0) / 2.0, 0.0, 1.0).detach().cpu().numpy()
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
    model = TinyTerrainUNet(
        channels=len(config.terrain_channels),
        base_channels=config.base_channels,
        time_dim=config.time_dim,
    ).to(device)
    schedule = DiffusionSchedule(config.diffusion_steps, device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=config.learning_rate)
    channels = _read_first_channels(Path(config.tensor_manifest), config.terrain_channels)
    out_dir = Path(config.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "config.json").write_text(json.dumps(asdict(config), indent=2), encoding="utf-8")

    loss_rows = []
    best_val = float("inf")
    for epoch in range(1, config.epochs + 1):
        train_loss = _run_epoch(
            model,
            train_loader,
            optimizer,
            schedule,
            device,
            config.terrain_channels,
        )
        val_loss = _run_epoch(
            model,
            val_loader,
            None,
            schedule,
            device,
            config.terrain_channels,
        )
        loss_rows.append(
            {
                "epoch": epoch,
                "train_loss": round(train_loss, 8),
                "val_loss": round(val_loss, 8),
            }
        )
        _write_loss_csv(out_dir / "losses.csv", loss_rows)
        if val_loss < best_val:
            best_val = val_loss
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
        print(f"epoch={epoch} train_loss={train_loss:.6f} val_loss={val_loss:.6f}")

    _sample(
        model,
        schedule,
        sample_count=config.sample_count,
        channels=channels,
        out_dir=out_dir / "samples",
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
    parser = argparse.ArgumentParser(description="Train a tiny terrain/water DDPM generator.")
    parser.add_argument("--tensor-manifest", required=True, type=Path)
    parser.add_argument("--splits-csv", type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--epochs", default=10, type=int)
    parser.add_argument("--batch-size", default=8, type=int)
    parser.add_argument("--learning-rate", default=2e-4, type=float)
    parser.add_argument("--base-channels", default=32, type=int)
    parser.add_argument("--time-dim", default=128, type=int)
    parser.add_argument("--diffusion-steps", default=200, type=int)
    parser.add_argument("--max-train-maps", type=int)
    parser.add_argument("--max-val-maps", type=int)
    parser.add_argument("--sample-count", default=8, type=int)
    parser.add_argument("--seed", default=20260712, type=int)
    parser.add_argument(
        "--terrain-channels",
        default=",".join(str(index) for index in DEFAULT_TERRAIN_CHANNELS),
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
        time_dim=args.time_dim,
        diffusion_steps=args.diffusion_steps,
        max_train_maps=args.max_train_maps,
        max_val_maps=args.max_val_maps,
        sample_count=args.sample_count,
        seed=args.seed,
        device=args.device,
        terrain_channels=_parse_channel_indexes(args.terrain_channels),
    )
    summary = train(config)
    Path(args.out_dir, "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
