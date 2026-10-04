"""Probe possible playable-area trimming by symmetry matching."""

from __future__ import annotations

import argparse
import csv
import json
import struct
from pathlib import Path
from typing import Any

import numpy as np

from supmapai.extract.scmap_terrain import _height_vertices_to_cells, _heightmap_offset


def _read_f32(data: bytes, offset: int) -> float:
    return struct.unpack_from("<f", data, offset)[0]


def load_cell_heights(scmap_path: Path) -> np.ndarray:
    data = scmap_path.read_bytes()
    map_width = int(_read_f32(data, 16))
    map_height = int(_read_f32(data, 20))
    height_count = (map_width + 1) * (map_height + 1)
    height_offset, _ = _heightmap_offset(data)
    vertices = np.frombuffer(
        data,
        dtype="<u2",
        count=height_count,
        offset=height_offset,
    ).reshape((map_height + 1, map_width + 1))
    return _height_vertices_to_cells(vertices.astype(np.float32) / 128.0)


def _mae(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.mean(np.abs(a - b)))


def _rmse(a: np.ndarray, b: np.ndarray) -> float:
    diff = a - b
    return float(np.sqrt(np.mean(diff * diff)))


def edge_column_scores(heights: np.ndarray, max_offset: int) -> list[dict[str, Any]]:
    rows = []
    for left in range(max_offset + 1):
        for right in range(max_offset + 1):
            a = heights[:, left]
            b = heights[::-1, heights.shape[1] - 1 - right]
            rows.append(
                {
                    "left_offset": left,
                    "right_offset": right,
                    "mae": _mae(a, b),
                    "rmse": _rmse(a, b),
                }
            )
    return sorted(rows, key=lambda row: row["mae"])


def edge_row_scores(heights: np.ndarray, max_offset: int) -> list[dict[str, Any]]:
    rows = []
    for top in range(max_offset + 1):
        for bottom in range(max_offset + 1):
            a = heights[top, :]
            b = heights[heights.shape[0] - 1 - bottom, ::-1]
            rows.append(
                {
                    "top_offset": top,
                    "bottom_offset": bottom,
                    "mae": _mae(a, b),
                    "rmse": _rmse(a, b),
                }
            )
    return sorted(rows, key=lambda row: row["mae"])


def crop_symmetry_scores(
    heights: np.ndarray,
    max_trim: int,
    stride: int,
) -> list[dict[str, Any]]:
    rows = []
    height, width = heights.shape
    for left in range(max_trim + 1):
        for right in range(max_trim + 1):
            for top in range(max_trim + 1):
                for bottom in range(max_trim + 1):
                    crop = heights[top : height - bottom, left : width - right]
                    if crop.size == 0:
                        continue
                    sampled = crop[::stride, ::stride]
                    rotated = sampled[::-1, ::-1]
                    rows.append(
                        {
                            "left": left,
                            "right": right,
                            "top": top,
                            "bottom": bottom,
                            "height": int(crop.shape[0]),
                            "width": int(crop.shape[1]),
                            "mae": _mae(sampled, rotated),
                            "rmse": _rmse(sampled, rotated),
                        }
                    )
    return sorted(rows, key=lambda row: row["mae"])


def probe_scmap(scmap_path: Path, max_offset: int, max_trim: int, stride: int) -> dict[str, Any]:
    heights = load_cell_heights(scmap_path)
    return {
        "scmap": str(scmap_path),
        "shape": list(heights.shape),
        "column_scores_top10": edge_column_scores(heights, max_offset)[:10],
        "row_scores_top10": edge_row_scores(heights, max_offset)[:10],
        "crop_180_scores_top20": crop_symmetry_scores(
            heights,
            max_trim,
            stride,
        )[:20],
    }


def _probe_csv_rows(
    terrain_csv: Path,
    map_dir: str | None,
    max_offset: int,
    max_trim: int,
    stride: int,
) -> list[dict[str, Any]]:
    rows = list(csv.DictReader(terrain_csv.open(encoding="utf-8-sig")))
    results = []
    for row in rows:
        if map_dir and row.get("map_dir") != map_dir:
            continue
        result = probe_scmap(Path(row["scmap_path"]), max_offset, max_trim, stride)
        result["map_dir"] = row.get("map_dir", "")
        results.append(result)
    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe map edge trims by symmetry matching.")
    parser.add_argument("--scmap", type=Path)
    parser.add_argument("--terrain-csv", type=Path)
    parser.add_argument("--map-dir")
    parser.add_argument("--max-offset", default=16, type=int)
    parser.add_argument("--max-trim", default=12, type=int)
    parser.add_argument("--stride", default=4, type=int)
    parser.add_argument("--out", type=Path, help="Optional JSON output path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.scmap:
        result: dict[str, Any] | list[dict[str, Any]] = probe_scmap(
            args.scmap,
            args.max_offset,
            args.max_trim,
            args.stride,
        )
    elif args.terrain_csv:
        result = _probe_csv_rows(
            args.terrain_csv,
            args.map_dir,
            args.max_offset,
            args.max_trim,
            args.stride,
        )
    else:
        raise SystemExit("Provide --scmap or --terrain-csv.")

    text = json.dumps(result, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
        print(f"Wrote trim probe to {args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
