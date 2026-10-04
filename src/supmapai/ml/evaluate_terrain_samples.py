"""Compute simple sanity metrics for generated terrain/water samples."""

from __future__ import annotations

import argparse
import csv
import json
from collections import deque
from pathlib import Path
from typing import Any

import numpy as np


def _connected_components(mask: np.ndarray) -> tuple[int, int]:
    visited = np.zeros(mask.shape, dtype=bool)
    height, width = mask.shape
    count = 0
    largest = 0
    for y in range(height):
        for x in range(width):
            if visited[y, x] or not mask[y, x]:
                continue
            count += 1
            size = 0
            queue: deque[tuple[int, int]] = deque([(y, x)])
            visited[y, x] = True
            while queue:
                cy, cx = queue.popleft()
                size += 1
                for ny, nx in (
                    (cy - 1, cx),
                    (cy + 1, cx),
                    (cy, cx - 1),
                    (cy, cx + 1),
                ):
                    in_bounds = 0 <= ny < height and 0 <= nx < width
                    if in_bounds and not visited[ny, nx] and mask[ny, nx]:
                        visited[ny, nx] = True
                        queue.append((ny, nx))
            largest = max(largest, size)
    return count, largest


def _shoreline_length(water_mask: np.ndarray) -> int:
    vertical = water_mask[1:, :] != water_mask[:-1, :]
    horizontal = water_mask[:, 1:] != water_mask[:, :-1]
    return int(vertical.sum() + horizontal.sum())


def evaluate_sample(path: Path, water_threshold: float) -> dict[str, Any]:
    archive = np.load(path)
    tensor = archive["tensor"].astype(np.float32)
    channels = (
        [str(item) for item in archive["channels"]]
        if "channels" in archive.files
        else [f"channel_{index:02d}" for index in range(tensor.shape[0])]
    )
    channel_lookup = {name: index for index, name in enumerate(channels)}
    height = tensor[channel_lookup.get("height_norm", 0)]
    water = tensor[channel_lookup.get("water_mask", min(1, tensor.shape[0] - 1))]
    water_depth = tensor[channel_lookup.get("water_depth_norm", min(2, tensor.shape[0] - 1))]
    water_mask = water >= water_threshold
    water_body_count, largest_water_body = _connected_components(water_mask)
    cell_count = int(water_mask.size)
    return {
        "sample_path": str(path),
        "height_mean": float(height.mean()),
        "height_std": float(height.std()),
        "height_min": float(height.min()),
        "height_max": float(height.max()),
        "water_mean": float(water.mean()),
        "water_percent": float(water_mask.mean() * 100.0),
        "water_depth_mean": float(water_depth.mean()),
        "water_body_count": water_body_count,
        "largest_water_body_percent": float(largest_water_body / max(cell_count, 1) * 100.0),
        "shoreline_length": _shoreline_length(water_mask),
    }


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "sample_path",
        "height_mean",
        "height_std",
        "height_min",
        "height_max",
        "water_mean",
        "water_percent",
        "water_depth_mean",
        "water_body_count",
        "largest_water_body_percent",
        "shoreline_length",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {"sample_count": len(rows), "metrics": {}}
    if not rows:
        return summary
    for key in (
        "height_mean",
        "height_std",
        "water_percent",
        "water_depth_mean",
        "water_body_count",
        "largest_water_body_percent",
        "shoreline_length",
    ):
        values = np.array([float(row[key]) for row in rows], dtype=np.float32)
        summary["metrics"][key] = {
            "mean": round(float(values.mean()), 6),
            "min": round(float(values.min()), 6),
            "max": round(float(values.max()), 6),
        }
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate generated terrain/water samples.")
    parser.add_argument("--samples-dir", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--summary-out", required=True, type=Path)
    parser.add_argument("--max-items", type=int)
    parser.add_argument("--water-threshold", default=0.5, type=float)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    paths = sorted(args.samples_dir.glob("*.generated.npz"))
    if args.max_items is not None:
        paths = paths[: args.max_items]
    rows = [evaluate_sample(path, args.water_threshold) for path in paths]
    _write_csv(args.out, rows)
    args.summary_out.parent.mkdir(parents=True, exist_ok=True)
    args.summary_out.write_text(json.dumps(_summary(rows), indent=2), encoding="utf-8")
    print(f"Evaluated {len(rows)} generated terrain sample(s)")
    print(f"Wrote terrain sample metrics to {args.out}")
    print(f"Wrote terrain sample summary to {args.summary_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
