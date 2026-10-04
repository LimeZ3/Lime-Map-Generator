"""Place a simple reclaim-density layer on a generated terrain/resource tensor."""

from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw

from supmapai.ml.rule_place_points import _buildable_mask, _nearest_valid, _terrain_layers


def _load_tensor(path: Path) -> tuple[np.ndarray, list[str]]:
    archive = np.load(path)
    tensor = archive["tensor"].astype(np.float32)
    channels = (
        [str(item) for item in archive["channels"]]
        if "channels" in archive.files
        else [f"channel_{index:02d}" for index in range(tensor.shape[0])]
    )
    return tensor, channels


def _point_dict(x: int, y: int, grid_size: int, kind: str, weight: float) -> dict[str, Any]:
    return {
        "kind": kind,
        "x": x,
        "y": y,
        "norm_x": round(float(x / max(grid_size - 1, 1)), 6),
        "norm_z": round(float(y / max(grid_size - 1, 1)), 6),
        "weight": round(weight, 6),
    }


def _weighted_stamp(points: list[dict[str, Any]], grid_size: int, sigma: float) -> np.ndarray:
    density = np.zeros((grid_size, grid_size), dtype=np.float32)
    radius = max(1, int(math.ceil(sigma * 3)))
    for point in points:
        x = int(point["x"])
        y = int(point["y"])
        weight = float(point.get("weight", 1.0))
        x0 = max(0, x - radius)
        x1 = min(grid_size - 1, x + radius)
        y0 = max(0, y - radius)
        y1 = min(grid_size - 1, y + radius)
        for py in range(y0, y1 + 1):
            for px in range(x0, x1 + 1):
                dist2 = (px - x) ** 2 + (py - y) ** 2
                density[py, px] += weight * math.exp(-dist2 / (2 * sigma**2))
    maximum = float(density.max())
    if maximum > 0.0:
        density /= maximum
    return density


def _spawn_reclaim(
    spawns: list[dict[str, Any]],
    valid: np.ndarray,
    per_spawn: int,
    seed: int,
) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    grid_size = valid.shape[0]
    points = []
    for spawn in spawns:
        sx = float(spawn["x"])
        sy = float(spawn["y"])
        for index in range(per_spawn):
            angle = math.tau * index / max(per_spawn, 1) + rng.uniform(-0.22, 0.22)
            radius = rng.uniform(grid_size * 0.035, grid_size * 0.085)
            x = sx + math.cos(angle) * radius
            y = sy + math.sin(angle) * radius
            px, py = _nearest_valid(x, y, valid, search_radius=36)
            points.append(_point_dict(px, py, grid_size, "early_reclaim", rng.uniform(0.7, 1.2)))
    return points


def _center_reclaim(valid: np.ndarray, count: int, seed: int) -> list[dict[str, Any]]:
    rng = random.Random(seed + 997)
    grid_size = valid.shape[0]
    center = (grid_size - 1) / 2.0
    points = []
    for index in range(count):
        angle = math.tau * index / max(count, 1) + rng.uniform(-0.18, 0.18)
        radius = rng.uniform(grid_size * 0.055, grid_size * 0.18)
        x = center + math.cos(angle) * radius
        y = center + math.sin(angle) * radius
        px, py = _nearest_valid(x, y, valid, search_radius=44)
        points.append(_point_dict(px, py, grid_size, "contested_reclaim", rng.uniform(0.9, 1.6)))
    return points


def _field_reclaim(valid: np.ndarray, count: int, seed: int) -> list[dict[str, Any]]:
    rng = random.Random(seed + 2027)
    ys, xs = np.where(valid)
    if len(xs) == 0:
        return []
    grid_size = valid.shape[0]
    points = []
    for _ in range(count):
        item_index = rng.randrange(len(xs))
        points.append(
            _point_dict(
                int(xs[item_index]),
                int(ys[item_index]),
                grid_size,
                "field_reclaim",
                rng.uniform(0.25, 0.8),
            )
        )
    return points


def _draw_preview(points: list[dict[str, Any]], grid_size: int, out_path: Path) -> None:
    scale = max(1, 512 // grid_size)
    image = Image.new("RGB", (grid_size * scale, grid_size * scale), (18, 20, 24))
    draw = ImageDraw.Draw(image)
    colors = {
        "early_reclaim": (70, 230, 120),
        "contested_reclaim": (255, 210, 80),
        "field_reclaim": (120, 170, 120),
    }
    for point in points:
        x = int(point["x"]) * scale
        y = int(point["y"]) * scale
        radius = 2 + int(float(point.get("weight", 1.0)))
        draw.ellipse(
            (x - radius, y - radius, x + radius, y + radius),
            fill=colors.get(str(point["kind"]), (180, 180, 180)),
        )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(out_path)


def place_reclaim(
    input_path: Path,
    point_metadata_path: Path,
    early_per_spawn: int,
    center_count: int,
    field_count: int,
    water_threshold: float,
    seed: int,
) -> tuple[np.ndarray, list[str], dict[str, Any]]:
    tensor, channels = _load_tensor(input_path)
    point_metadata = json.loads(point_metadata_path.read_text(encoding="utf-8"))
    height, water = _terrain_layers(tensor, channels)
    valid = _buildable_mask(height, water, water_threshold)
    spawns = list(point_metadata.get("points", {}).get("spawns", []))
    reclaim_points = []
    reclaim_points.extend(_spawn_reclaim(spawns, valid, early_per_spawn, seed))
    reclaim_points.extend(_center_reclaim(valid, center_count, seed))
    reclaim_points.extend(_field_reclaim(valid, field_count, seed))
    density = _weighted_stamp(reclaim_points, int(tensor.shape[-1]), sigma=2.4)
    output = np.concatenate([tensor, density[None, :, :]], axis=0)
    metadata = {
        "source": str(input_path),
        "point_metadata": str(point_metadata_path),
        "early_per_spawn": early_per_spawn,
        "center_count": center_count,
        "field_count": field_count,
        "reclaim_point_count": len(reclaim_points),
        "density_mean": round(float(density.mean()), 8),
        "density_max": round(float(density.max()), 8),
        "points": reclaim_points,
    }
    return output.astype(np.float32), [*channels, "reclaim_density"], metadata


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rule-place reclaim density.")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--point-metadata", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--metadata-out", required=True, type=Path)
    parser.add_argument("--preview-out", type=Path)
    parser.add_argument("--early-per-spawn", default=8, type=int)
    parser.add_argument("--center-count", default=14, type=int)
    parser.add_argument("--field-count", default=24, type=int)
    parser.add_argument("--water-threshold", default=0.5, type=float)
    parser.add_argument("--seed", default=20260712, type=int)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    tensor, channels, metadata = place_reclaim(
        input_path=args.input,
        point_metadata_path=args.point_metadata,
        early_per_spawn=args.early_per_spawn,
        center_count=args.center_count,
        field_count=args.field_count,
        water_threshold=args.water_threshold,
        seed=args.seed,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(args.out, tensor=tensor, channels=np.array(channels))
    args.metadata_out.parent.mkdir(parents=True, exist_ok=True)
    args.metadata_out.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    if args.preview_out:
        _draw_preview(metadata["points"], int(tensor.shape[-1]), args.preview_out)
    print(f"Wrote reclaim-placed tensor to {args.out}")
    print(f"Wrote reclaim metadata to {args.metadata_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
