"""Decode spawn/mex/hydro point candidates from tensor or prediction heatmaps."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw

DEFAULT_COUNTS = {
    "spawn_heatmap": 4,
    "mex_heatmap": 32,
    "hydro_heatmap": 4,
}


def _load_heatmaps(path: Path, array_name: str) -> tuple[np.ndarray, list[str]]:
    archive = np.load(path)
    if array_name == "tensor":
        tensor = archive["tensor"]
    elif array_name in archive.files:
        tensor = archive[array_name]
    else:
        raise ValueError(f"{array_name!r} not present in {path}")
    channels = (
        [str(item) for item in archive["channels"]]
        if "channels" in archive.files
        else [f"channel_{index:02d}" for index in range(tensor.shape[0])]
    )
    return tensor.astype(np.float32), channels


def _local_maxima(
    heatmap: np.ndarray,
    count: int,
    min_distance: int,
    threshold: float,
) -> list[dict[str, Any]]:
    work = heatmap.copy()
    points = []
    height, width = work.shape
    for _ in range(count):
        flat_index = int(np.argmax(work))
        score = float(work.flat[flat_index])
        if score < threshold:
            break
        y, x = np.unravel_index(flat_index, work.shape)
        points.append(
            {
                "x": int(x),
                "y": int(y),
                "norm_x": round(float(x / max(width - 1, 1)), 6),
                "norm_z": round(float(y / max(height - 1, 1)), 6),
                "score": round(score, 6),
            }
        )
        x0 = max(0, x - min_distance)
        x1 = min(width, x + min_distance + 1)
        y0 = max(0, y - min_distance)
        y1 = min(height, y + min_distance + 1)
        work[y0:y1, x0:x1] = 0.0
    return points


def decode_points(
    path: Path,
    array_name: str,
    counts: dict[str, int],
    min_distance: int,
    threshold: float,
) -> dict[str, Any]:
    tensor, channels = _load_heatmaps(path, array_name)
    decoded = {
        "source": str(path),
        "array": array_name,
        "grid_size": int(tensor.shape[-1]),
        "layers": {},
    }
    for channel_name, count in counts.items():
        if channel_name not in channels:
            continue
        index = channels.index(channel_name)
        decoded["layers"][channel_name] = _local_maxima(
            tensor[index],
            count=count,
            min_distance=min_distance,
            threshold=threshold,
        )
    return decoded


def _draw_preview(decoded: dict[str, Any], out_path: Path) -> None:
    grid_size = int(decoded["grid_size"])
    scale = max(1, 512 // grid_size)
    image = Image.new("RGB", (grid_size * scale, grid_size * scale), (18, 20, 24))
    draw = ImageDraw.Draw(image)
    colors = {
        "spawn_heatmap": (255, 80, 80),
        "mex_heatmap": (255, 220, 70),
        "hydro_heatmap": (60, 220, 255),
    }
    radii = {"spawn_heatmap": 5, "mex_heatmap": 3, "hydro_heatmap": 4}
    for layer, points in decoded["layers"].items():
        color = colors.get(layer, (230, 230, 230))
        radius = radii.get(layer, 3)
        for point in points:
            x = int(point["x"]) * scale
            y = int(point["y"]) * scale
            draw.ellipse(
                (
                    x - radius,
                    y - radius,
                    x + radius,
                    y + radius,
                ),
                fill=color,
            )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(out_path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Decode point candidates from heatmap layers.")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument(
        "--array",
        default="tensor",
        choices=["tensor", "original", "reconstruction"],
    )
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--preview-out", type=Path)
    parser.add_argument("--spawn-count", default=4, type=int)
    parser.add_argument("--mex-count", default=32, type=int)
    parser.add_argument("--hydro-count", default=4, type=int)
    parser.add_argument("--min-distance", default=8, type=int)
    parser.add_argument("--threshold", default=0.05, type=float)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    counts = dict(DEFAULT_COUNTS)
    counts["spawn_heatmap"] = args.spawn_count
    counts["mex_heatmap"] = args.mex_count
    counts["hydro_heatmap"] = args.hydro_count
    decoded = decode_points(
        path=args.input,
        array_name=args.array,
        counts=counts,
        min_distance=args.min_distance,
        threshold=args.threshold,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(decoded, indent=2), encoding="utf-8")
    if args.preview_out:
        _draw_preview(decoded, args.preview_out)
    print(f"Wrote decoded heatmap points to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
