"""Sample terrain/water tensors from a trained TerrainVAE."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch.utils.data import DataLoader

from supmapai.ml.tensor_dataset import MapTensorDataset
from supmapai.ml.train_terrain_vae import (
    DEFAULT_TERRAIN_CHANNELS,
    TerrainVAE,
    _channels_from_manifest,
)


def _load_checkpoint(checkpoint_path: Path, device: torch.device) -> dict[str, Any]:
    return torch.load(checkpoint_path, map_location=device)


def _model_from_checkpoint(checkpoint: dict[str, Any], device: torch.device) -> TerrainVAE:
    config = checkpoint["config"]
    model = TerrainVAE(
        in_channels=len(config["terrain_channels"]),
        base_channels=int(config["base_channels"]),
        latent_channels=int(config["latent_channels"]),
    ).to(device)
    model.load_state_dict(checkpoint["model_state"])
    model.eval()
    return model


def _save_generated(
    out_dir: Path,
    index: int,
    tensor: np.ndarray,
    channels: list[str],
    source_map_id: str = "",
    source_map_dir: str = "",
    noise_scale: float | None = None,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        out_dir / f"terrain_sample_{index:04d}.generated.npz",
        tensor=tensor.astype(np.float32),
        channels=np.array(channels),
        source_map_id=np.array(source_map_id),
        source_map_dir=np.array(source_map_dir),
        noise_scale=np.array(noise_scale if noise_scale is not None else np.nan),
    )


def _sample_normal(
    model: TerrainVAE,
    out_dir: Path,
    sample_count: int,
    latent_channels: int,
    channels: list[str],
    device: torch.device,
) -> None:
    with torch.no_grad():
        latent = torch.randn(sample_count, latent_channels, 16, 16, device=device)
        samples = model.decode(latent).detach().cpu().numpy()
    for index, sample in enumerate(samples):
        _save_generated(out_dir, index, sample, channels)


def _sample_encoded(
    model: TerrainVAE,
    tensor_manifest: Path,
    splits_csv: Path | None,
    split: str | None,
    terrain_channels: list[int],
    out_dir: Path,
    sample_count: int,
    noise_scale: float,
    channels: list[str],
    device: torch.device,
) -> None:
    dataset = MapTensorDataset(
        tensor_manifest=tensor_manifest,
        splits_csv=splits_csv,
        split=split,
        max_maps=sample_count,
    )
    loader = DataLoader(dataset, batch_size=1, shuffle=False, num_workers=0)
    saved = 0
    with torch.no_grad():
        for batch in loader:
            source = batch["tensor"].to(device=device, dtype=torch.float32)[:, terrain_channels]
            mu, logvar = model.encode(source)
            std = torch.exp(0.5 * logvar)
            latent = mu + torch.randn_like(std) * std * noise_scale
            sample = model.decode(latent).detach().cpu().numpy()[0]
            _save_generated(
                out_dir,
                saved,
                sample,
                channels,
                source_map_id=batch["map_id"][0],
                source_map_dir=batch["map_dir"][0],
                noise_scale=noise_scale,
            )
            saved += 1
            if saved >= sample_count:
                return


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sample from a trained terrain/water VAE.")
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--tensor-manifest", type=Path)
    parser.add_argument("--splits-csv", type=Path)
    parser.add_argument("--split", default="val")
    parser.add_argument("--mode", default="encoded", choices=["encoded", "normal"])
    parser.add_argument("--sample-count", default=8, type=int)
    parser.add_argument("--noise-scale", default=0.25, type=float)
    parser.add_argument("--seed", default=20260712, type=int)
    parser.add_argument(
        "--device",
        default="cuda" if torch.cuda.is_available() else "cpu",
        choices=["cuda", "cpu"],
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)
    device = torch.device(args.device)
    checkpoint = _load_checkpoint(args.checkpoint, device)
    config = checkpoint["config"]
    terrain_channels = [
        int(index) for index in config.get("terrain_channels", DEFAULT_TERRAIN_CHANNELS)
    ]
    channels = (
        [str(item) for item in checkpoint["channels"]]
        if "channels" in checkpoint
        else _channels_from_manifest(Path(config["tensor_manifest"]), terrain_channels)
    )
    model = _model_from_checkpoint(checkpoint, device)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "sampling_config.json").write_text(
        json.dumps(
            {
                "checkpoint": str(args.checkpoint),
                "mode": args.mode,
                "sample_count": args.sample_count,
                "noise_scale": args.noise_scale,
                "seed": args.seed,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    if args.mode == "normal":
        _sample_normal(
            model,
            args.out_dir,
            args.sample_count,
            int(config["latent_channels"]),
            channels,
            device,
        )
    else:
        if args.tensor_manifest is None:
            raise ValueError("--tensor-manifest is required for encoded sampling")
        _sample_encoded(
            model,
            args.tensor_manifest,
            args.splits_csv,
            args.split,
            terrain_channels,
            args.out_dir,
            args.sample_count,
            args.noise_scale,
            channels,
            device,
        )
    print(f"Wrote {args.sample_count} terrain sample(s) to {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
