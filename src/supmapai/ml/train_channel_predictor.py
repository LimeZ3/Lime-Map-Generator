"""Train a tiny terrain-to-gameplay channel predictor baseline."""

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

INPUT_CHANNELS = list(range(7))
TARGET_CHANNELS = list(range(7, 12))
DEFAULT_POS_WEIGHTS = [24.0, 12.0, 28.0, 6.0, 50.0]


@dataclass
class TrainConfig:
    tensor_manifest: str
    splits_csv: str | None
    out_dir: str
    epochs: int
    batch_size: int
    learning_rate: float
    base_channels: int
    architecture: str
    max_train_maps: int | None
    max_val_maps: int | None
    seed: int
    device: str


class TinyChannelPredictor(nn.Module):
    def __init__(self, in_channels: int, out_channels: int, base_channels: int) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Conv2d(in_channels, base_channels, kernel_size=3, padding=1),
            nn.SiLU(),
            nn.Conv2d(base_channels, base_channels, kernel_size=3, padding=1),
            nn.SiLU(),
            nn.Conv2d(base_channels, base_channels * 2, kernel_size=3, padding=1),
            nn.SiLU(),
            nn.Conv2d(base_channels * 2, base_channels, kernel_size=3, padding=1),
            nn.SiLU(),
            nn.Conv2d(base_channels, out_channels, kernel_size=1),
        )

    def forward(self, tensor: torch.Tensor) -> torch.Tensor:
        return self.net(tensor)


class _ConvBlock(nn.Module):
    def __init__(self, in_channels: int, out_channels: int) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Conv2d(in_channels, out_channels, kernel_size=3, padding=1),
            nn.SiLU(),
            nn.Conv2d(out_channels, out_channels, kernel_size=3, padding=1),
            nn.SiLU(),
        )

    def forward(self, tensor: torch.Tensor) -> torch.Tensor:
        return self.net(tensor)


class SmallUNetPredictor(nn.Module):
    def __init__(self, in_channels: int, out_channels: int, base_channels: int) -> None:
        super().__init__()
        self.enc1 = _ConvBlock(in_channels, base_channels)
        self.down1 = nn.Conv2d(base_channels, base_channels * 2, kernel_size=3, stride=2, padding=1)
        self.enc2 = _ConvBlock(base_channels * 2, base_channels * 2)
        self.down2 = nn.Conv2d(
            base_channels * 2,
            base_channels * 4,
            kernel_size=3,
            stride=2,
            padding=1,
        )
        self.mid = _ConvBlock(base_channels * 4, base_channels * 4)
        self.up2 = nn.ConvTranspose2d(
            base_channels * 4,
            base_channels * 2,
            kernel_size=4,
            stride=2,
            padding=1,
        )
        self.dec2 = _ConvBlock(base_channels * 4, base_channels * 2)
        self.up1 = nn.ConvTranspose2d(
            base_channels * 2,
            base_channels,
            kernel_size=4,
            stride=2,
            padding=1,
        )
        self.dec1 = _ConvBlock(base_channels * 2, base_channels)
        self.out = nn.Conv2d(base_channels, out_channels, kernel_size=1)

    def forward(self, tensor: torch.Tensor) -> torch.Tensor:
        enc1 = self.enc1(tensor)
        enc2 = self.enc2(self.down1(enc1))
        mid = self.mid(self.down2(enc2))
        dec2 = self.up2(mid)
        dec2 = self.dec2(torch.cat([dec2, enc2], dim=1))
        dec1 = self.up1(dec2)
        dec1 = self.dec1(torch.cat([dec1, enc1], dim=1))
        return self.out(dec1)


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


def _split_batch(batch: dict[str, Any], device: torch.device) -> tuple[torch.Tensor, torch.Tensor]:
    tensor = batch["tensor"].to(device=device, dtype=torch.float32, non_blocking=True)
    return tensor[:, INPUT_CHANNELS], tensor[:, TARGET_CHANNELS]


def _loss(logits: torch.Tensor, target: torch.Tensor, pos_weights: torch.Tensor) -> torch.Tensor:
    prediction = torch.sigmoid(logits)
    positive_weights = pos_weights.to(device=logits.device, dtype=logits.dtype).view(1, -1, 1, 1)
    binary_target = (target > 0.05).to(dtype=logits.dtype)
    bce = nn.functional.binary_cross_entropy_with_logits(
        logits,
        binary_target,
        pos_weight=positive_weights,
    )
    heat_weights = 1.0 + target * positive_weights
    heat_mse = ((prediction - target).square() * heat_weights).mean()
    return bce * 0.7 + heat_mse * 0.3


def _run_epoch(
    model: nn.Module,
    loader: DataLoader[dict[str, Any]],
    optimizer: torch.optim.Optimizer | None,
    device: torch.device,
    pos_weights: torch.Tensor,
) -> float:
    training = optimizer is not None
    model.train(training)
    losses = []
    for batch in loader:
        inputs, target = _split_batch(batch, device)
        with torch.set_grad_enabled(training):
            logits = model(inputs)
            loss = _loss(logits, target, pos_weights)
            if training:
                optimizer.zero_grad(set_to_none=True)
                loss.backward()
                optimizer.step()
        losses.append(float(loss.detach().cpu()))
    return sum(losses) / max(len(losses), 1)


def _channels_from_manifest(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            tensor_path = row.get("tensor_path", "")
            if tensor_path:
                return [str(item) for item in np.load(tensor_path)["channels"]]
    return []


def _write_loss_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["epoch", "train_loss", "val_loss"])
        writer.writeheader()
        writer.writerows(rows)


def _save_predictions(
    model: nn.Module,
    loader: DataLoader[dict[str, Any]],
    device: torch.device,
    out_dir: Path,
    target_channels: list[str],
    max_items: int,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    model.eval()
    saved = 0
    with torch.no_grad():
        for batch in loader:
            inputs, target = _split_batch(batch, device)
            prediction = torch.sigmoid(model(inputs)).detach().cpu().numpy()
            target_np = target.detach().cpu().numpy()
            map_ids = batch["map_id"]
            map_dirs = batch["map_dir"]
            for index in range(prediction.shape[0]):
                if saved >= max_items:
                    return
                np.savez_compressed(
                    out_dir / f"{map_ids[index]}.prediction.npz",
                    original=target_np[index].astype(np.float32),
                    reconstruction=prediction[index].astype(np.float32),
                    channels=np.array(target_channels),
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
    if config.architecture == "unet":
        model = SmallUNetPredictor(
            in_channels=len(INPUT_CHANNELS),
            out_channels=len(TARGET_CHANNELS),
            base_channels=config.base_channels,
        )
    else:
        model = TinyChannelPredictor(
            in_channels=len(INPUT_CHANNELS),
            out_channels=len(TARGET_CHANNELS),
            base_channels=config.base_channels,
        )
    model = model.to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=config.learning_rate)
    pos_weights = torch.tensor(DEFAULT_POS_WEIGHTS, dtype=torch.float32)
    out_dir = Path(config.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "config.json").write_text(json.dumps(asdict(config), indent=2), encoding="utf-8")

    loss_rows = []
    best_val = float("inf")
    for epoch in range(1, config.epochs + 1):
        train_loss = _run_epoch(model, train_loader, optimizer, device, pos_weights)
        val_loss = _run_epoch(model, val_loader, None, device, pos_weights)
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
                    "val_loss": val_loss,
                },
                out_dir / "best.pt",
            )
        print(f"epoch={epoch} train_loss={train_loss:.6f} val_loss={val_loss:.6f}")

    all_channels = _channels_from_manifest(Path(config.tensor_manifest))
    target_channels = [all_channels[index] for index in TARGET_CHANNELS] if all_channels else []
    _save_predictions(
        model,
        val_loader,
        device,
        out_dir / "predictions",
        target_channels,
        max_items=8,
    )
    return {
        "best_val_loss": best_val,
        "epochs": config.epochs,
        "train_batches": len(train_loader),
        "val_batches": len(val_loader),
        "input_channels": [all_channels[index] for index in INPUT_CHANNELS] if all_channels else [],
        "target_channels": target_channels,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train a tiny terrain-to-gameplay predictor.")
    parser.add_argument("--tensor-manifest", required=True, type=Path)
    parser.add_argument("--splits-csv", type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--epochs", default=5, type=int)
    parser.add_argument("--batch-size", default=8, type=int)
    parser.add_argument("--learning-rate", default=1e-3, type=float)
    parser.add_argument("--base-channels", default=32, type=int)
    parser.add_argument("--architecture", default="unet", choices=["tiny", "unet"])
    parser.add_argument("--max-train-maps", type=int)
    parser.add_argument("--max-val-maps", type=int)
    parser.add_argument("--seed", default=20260711, type=int)
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
        architecture=args.architecture,
        max_train_maps=args.max_train_maps,
        max_val_maps=args.max_val_maps,
        seed=args.seed,
        device=args.device,
    )
    summary = train(config)
    Path(args.out_dir, "summary.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
