"""Sample terrain/water tensors from a trained DDPM checkpoint."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import torch

from supmapai.ml.train_terrain_ddpm import DiffusionSchedule, TinyTerrainUNet


@torch.no_grad()
def sample_checkpoint(
    checkpoint_path: Path,
    out_dir: Path,
    sample_count: int,
    seed: int,
    device: torch.device,
) -> None:
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    checkpoint = torch.load(checkpoint_path, map_location=device)
    config = checkpoint["config"]
    channels = [str(item) for item in checkpoint["channels"]]
    model = TinyTerrainUNet(
        channels=len(channels),
        base_channels=int(config["base_channels"]),
        time_dim=int(config["time_dim"]),
    ).to(device)
    model.load_state_dict(checkpoint["model_state"])
    model.eval()
    schedule = DiffusionSchedule(int(config["diffusion_steps"]), device)
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
    out_dir.mkdir(parents=True, exist_ok=True)
    for index, sample in enumerate(samples):
        np.savez_compressed(
            out_dir / f"terrain_sample_{index:04d}.generated.npz",
            tensor=sample.astype(np.float32),
            channels=np.array(channels),
        )
    print(f"Wrote {sample_count} DDPM terrain sample(s) to {out_dir}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sample from a trained terrain/water DDPM.")
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--sample-count", default=8, type=int)
    parser.add_argument("--seed", default=20260712, type=int)
    parser.add_argument(
        "--device",
        default="cuda" if torch.cuda.is_available() else "cpu",
        choices=["cuda", "cpu"],
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    sample_checkpoint(
        checkpoint_path=args.checkpoint,
        out_dir=args.out_dir,
        sample_count=args.sample_count,
        seed=args.seed,
        device=torch.device(args.device),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
