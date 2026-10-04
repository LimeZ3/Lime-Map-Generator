"""Place spawn/mex/hydro point heatmaps on generated terrain using simple rules."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw


def _load_generated(path: Path) -> tuple[np.ndarray, list[str]]:
    archive = np.load(path)
    tensor = archive["tensor"].astype(np.float32)
    channels = (
        [str(item) for item in archive["channels"]]
        if "channels" in archive.files
        else [f"channel_{index:02d}" for index in range(tensor.shape[0])]
    )
    return tensor, channels


def _terrain_layers(tensor: np.ndarray, channels: list[str]) -> tuple[np.ndarray, np.ndarray]:
    lookup = {name: index for index, name in enumerate(channels)}
    height = tensor[lookup.get("height_norm", 0)]
    water = tensor[lookup.get("water_mask", min(1, tensor.shape[0] - 1))]
    return height, water


def _buildable_mask(height: np.ndarray, water: np.ndarray, water_threshold: float) -> np.ndarray:
    gy, gx = np.gradient(height)
    slope = np.hypot(gx, gy)
    slope_cutoff = max(float(np.quantile(slope, 0.72)), 0.015)
    return (water < water_threshold) & (slope <= slope_cutoff)


def _nearest_valid(
    x: float,
    y: float,
    valid: np.ndarray,
    search_radius: int,
) -> tuple[int, int]:
    height, width = valid.shape
    cx = int(np.clip(round(x), 0, width - 1))
    cy = int(np.clip(round(y), 0, height - 1))
    if valid[cy, cx]:
        return cx, cy
    best: tuple[int, int] | None = None
    best_dist = float("inf")
    x0 = max(0, cx - search_radius)
    x1 = min(width - 1, cx + search_radius)
    y0 = max(0, cy - search_radius)
    y1 = min(height - 1, cy + search_radius)
    for py in range(y0, y1 + 1):
        for px in range(x0, x1 + 1):
            if not valid[py, px]:
                continue
            dist = (px - x) ** 2 + (py - y) ** 2
            if dist < best_dist:
                best = (px, py)
                best_dist = dist
    return best if best is not None else (cx, cy)


def _circle_points(
    count: int,
    radius: float,
    angle_offset: float,
    grid_size: int,
) -> list[tuple[float, float]]:
    center = (grid_size - 1) / 2.0
    points = []
    for index in range(count):
        angle = angle_offset + math.tau * index / count
        points.append(
            (
                center + math.cos(angle) * radius * grid_size,
                center + math.sin(angle) * radius * grid_size,
            )
        )
    return points


def _point_dict(x: int, y: int, grid_size: int, kind: str) -> dict[str, Any]:
    return {
        "kind": kind,
        "x": x,
        "y": y,
        "norm_x": round(float(x / max(grid_size - 1, 1)), 6),
        "norm_z": round(float(y / max(grid_size - 1, 1)), 6),
    }


def _place_spawns(
    valid: np.ndarray,
    players: int,
    spawn_radius: float,
    search_radius: int,
) -> list[dict[str, Any]]:
    grid_size = valid.shape[0]
    raw_points = _circle_points(players, spawn_radius, -math.pi / 4.0, grid_size)
    return [
        _point_dict(*_nearest_valid(x, y, valid, search_radius), grid_size, "spawn")
        for x, y in raw_points
    ]


def _place_ring_resources(
    valid: np.ndarray,
    spawns: list[dict[str, Any]],
    per_spawn: int,
    distance: float,
    angle_jitter: float,
    search_radius: int,
    kind: str,
) -> list[dict[str, Any]]:
    grid_size = valid.shape[0]
    center = (grid_size - 1) / 2.0
    points = []
    for spawn_index, spawn in enumerate(spawns):
        sx = float(spawn["x"])
        sy = float(spawn["y"])
        base_angle = math.atan2(center - sy, center - sx)
        for item_index in range(per_spawn):
            side = -1 if item_index % 2 == 0 else 1
            ring = 1 + item_index // 2
            angle = base_angle + side * angle_jitter * ring
            radius = distance * (1.0 + 0.14 * (ring - 1))
            x = sx + math.cos(angle) * radius
            y = sy + math.sin(angle) * radius
            px, py = _nearest_valid(x, y, valid, search_radius)
            points.append(_point_dict(px, py, grid_size, kind))
        if kind == "mex" and spawn_index < len(spawns):
            px, py = _nearest_valid(sx, sy, valid, search_radius)
            points.append(_point_dict(px, py, grid_size, kind))
    return points


def _place_center_mexes(
    valid: np.ndarray,
    count: int,
    search_radius: int,
) -> list[dict[str, Any]]:
    grid_size = valid.shape[0]
    raw_points = _circle_points(max(count, 1), 0.11, 0.0, grid_size)
    return [
        _point_dict(*_nearest_valid(x, y, valid, search_radius), grid_size, "mex")
        for x, y in raw_points[:count]
    ]


def _stamp_heatmap(points: list[dict[str, Any]], grid_size: int, sigma: float) -> np.ndarray:
    heatmap = np.zeros((grid_size, grid_size), dtype=np.float32)
    radius = max(1, int(math.ceil(sigma * 3)))
    for point in points:
        x = int(point["x"])
        y = int(point["y"])
        x0 = max(0, x - radius)
        x1 = min(grid_size - 1, x + radius)
        y0 = max(0, y - radius)
        y1 = min(grid_size - 1, y + radius)
        for py in range(y0, y1 + 1):
            for px in range(x0, x1 + 1):
                dist2 = (px - x) ** 2 + (py - y) ** 2
                heatmap[py, px] = max(heatmap[py, px], math.exp(-dist2 / (2 * sigma**2)))
    return heatmap


def _draw_preview(points: dict[str, list[dict[str, Any]]], grid_size: int, out_path: Path) -> None:
    scale = max(1, 512 // grid_size)
    image = Image.new("RGB", (grid_size * scale, grid_size * scale), (18, 20, 24))
    draw = ImageDraw.Draw(image)
    colors = {
        "spawns": (255, 80, 80),
        "mexes": (255, 220, 70),
        "hydros": (60, 220, 255),
    }
    radii = {"spawns": 5, "mexes": 3, "hydros": 4}
    for layer, layer_points in points.items():
        for point in layer_points:
            x = int(point["x"]) * scale
            y = int(point["y"]) * scale
            radius = radii[layer]
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=colors[layer])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(out_path)


def place_points(
    input_path: Path,
    players: int,
    mex_per_spawn: int,
    center_mexes: int,
    hydros_per_spawn: int,
    water_threshold: float,
    search_radius: int,
) -> tuple[np.ndarray, list[str], dict[str, Any]]:
    tensor, channels = _load_generated(input_path)
    height, water = _terrain_layers(tensor, channels)
    valid = _buildable_mask(height, water, water_threshold)
    grid_size = int(tensor.shape[-1])
    spawns = _place_spawns(valid, players, 0.36, search_radius)
    mexes = _place_ring_resources(
        valid,
        spawns,
        mex_per_spawn,
        distance=grid_size * 0.09,
        angle_jitter=0.55,
        search_radius=search_radius,
        kind="mex",
    )
    mexes.extend(_place_center_mexes(valid, center_mexes, search_radius))
    hydros = _place_ring_resources(
        valid,
        spawns,
        hydros_per_spawn,
        distance=grid_size * 0.075,
        angle_jitter=0.38,
        search_radius=search_radius,
        kind="hydro",
    )
    point_layers = {
        "spawns": spawns,
        "mexes": mexes,
        "hydros": hydros,
    }
    output = np.concatenate(
        [
            tensor,
            _stamp_heatmap(spawns, grid_size, sigma=2.2)[None, :, :],
            _stamp_heatmap(mexes, grid_size, sigma=1.8)[None, :, :],
            _stamp_heatmap(hydros, grid_size, sigma=2.0)[None, :, :],
        ],
        axis=0,
    )
    output_channels = [*channels, "spawn_heatmap", "mex_heatmap", "hydro_heatmap"]
    metadata = {
        "source": str(input_path),
        "players": players,
        "mex_per_spawn": mex_per_spawn,
        "center_mexes": center_mexes,
        "hydros_per_spawn": hydros_per_spawn,
        "water_threshold": water_threshold,
        "buildable_percent": round(float(valid.mean() * 100.0), 6),
        "points": point_layers,
    }
    return output.astype(np.float32), output_channels, metadata


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rule-place spawns, mexes, and hydros on terrain.")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--metadata-out", required=True, type=Path)
    parser.add_argument("--preview-out", type=Path)
    parser.add_argument("--players", default=4, type=int)
    parser.add_argument("--mex-per-spawn", default=4, type=int)
    parser.add_argument("--center-mexes", default=4, type=int)
    parser.add_argument("--hydros-per-spawn", default=1, type=int)
    parser.add_argument("--water-threshold", default=0.5, type=float)
    parser.add_argument("--search-radius", default=36, type=int)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    tensor, channels, metadata = place_points(
        input_path=args.input,
        players=args.players,
        mex_per_spawn=args.mex_per_spawn,
        center_mexes=args.center_mexes,
        hydros_per_spawn=args.hydros_per_spawn,
        water_threshold=args.water_threshold,
        search_radius=args.search_radius,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(args.out, tensor=tensor, channels=np.array(channels))
    args.metadata_out.parent.mkdir(parents=True, exist_ok=True)
    args.metadata_out.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    if args.preview_out:
        _draw_preview(metadata["points"], int(tensor.shape[-1]), args.preview_out)
    print(f"Wrote point-placed tensor to {args.out}")
    print(f"Wrote point metadata to {args.metadata_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
