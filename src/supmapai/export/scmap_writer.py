"""Patch generated terrain into an existing Supreme Commander .scmap file.

This V1 writer deliberately keeps the template .scmap layout, textures, decals,
props, water shader data, and preview data intact. It only replaces the raw
heightmap vertex block. That is the lowest-risk path to making generated terrain
show up in game while we are still learning the full .scmap format.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from supmapai.extract import scmap_terrain


@dataclass
class TerrainPatchSummary:
    template_scmap: str
    out_scmap: str
    map_width: int
    map_height: int
    heightmap_width: int
    heightmap_height: int
    height_offset: int
    water_level: float
    water_level_source: str
    generated_water_percent: float
    written_water_percent: float
    height_min: float
    height_max: float
    land_clearance: float
    land_height_range: float
    water_clearance: float
    water_depth_range: float
    shore_blur_iterations: int


def _load_tensor(path: Path) -> tuple[np.ndarray, list[str]]:
    archive = np.load(path)
    tensor = archive["tensor"].astype(np.float32)
    channels = (
        [str(item) for item in archive["channels"]]
        if "channels" in archive.files
        else [f"channel_{index:02d}" for index in range(tensor.shape[0])]
    )
    return tensor, channels


def _channel(tensor: np.ndarray, channels: list[str], name: str, fallback: int) -> np.ndarray:
    lookup = {channel_name: index for index, channel_name in enumerate(channels)}
    index = lookup.get(name, min(fallback, tensor.shape[0] - 1))
    return tensor[index].astype(np.float32)


def _resize_float(layer: np.ndarray, width: int, height: int, resample: int) -> np.ndarray:
    image = Image.fromarray(layer.astype(np.float32), mode="F")
    return np.asarray(image.resize((width, height), resample=resample), dtype=np.float32)


def _normalize_01(layer: np.ndarray) -> np.ndarray:
    finite = np.nan_to_num(layer.astype(np.float32), nan=0.0, posinf=0.0, neginf=0.0)
    return np.clip(finite, 0.0, 1.0)


def _smooth_float(layer: np.ndarray, iterations: int) -> np.ndarray:
    smoothed = layer.astype(np.float32)
    for _ in range(max(0, iterations)):
        padded = np.pad(smoothed, 1, mode="edge")
        smoothed = (
            padded[:-2, :-2]
            + padded[:-2, 1:-1]
            + padded[:-2, 2:]
            + padded[1:-1, :-2]
            + padded[1:-1, 1:-1]
            + padded[1:-1, 2:]
            + padded[2:, :-2]
            + padded[2:, 1:-1]
            + padded[2:, 2:]
        ) / 9.0
    return smoothed.astype(np.float32)


def _template_water_level(data: bytes) -> tuple[float, str]:
    header = scmap_terrain._terrain_header(data)
    count = (header.map_width + 1) * (header.map_height + 1)
    raw = np.frombuffer(data, dtype="<u2", count=count, offset=header.height_offset)
    heights = raw.astype(np.float32).reshape((header.map_height + 1, header.map_width + 1)) / 128.0
    water_level, source = scmap_terrain._infer_water_level(heights, data)
    if water_level is None:
        return 0.0, "default_zero"
    return float(water_level), source


def template_water_level(template_scmap: Path) -> tuple[float, str]:
    return _template_water_level(template_scmap.read_bytes())


def terrain_tensor_to_vertices(
    tensor: np.ndarray,
    channels: list[str],
    heightmap_width: int,
    heightmap_height: int,
    water_level: float,
    land_clearance: float,
    land_height_range: float,
    water_clearance: float,
    water_depth_range: float,
    shore_blur_iterations: int = 8,
) -> tuple[np.ndarray, np.ndarray]:
    height_norm = _normalize_01(_channel(tensor, channels, "height_norm", 0))
    water_mask = _channel(tensor, channels, "water_mask", 1) >= 0.5
    water_depth_norm = _normalize_01(_channel(tensor, channels, "water_depth_norm", 2))

    vertex_height_norm = _resize_float(
        height_norm,
        heightmap_width,
        heightmap_height,
        Image.Resampling.BICUBIC,
    )
    vertex_depth_norm = _resize_float(
        water_depth_norm,
        heightmap_width,
        heightmap_height,
        Image.Resampling.BICUBIC,
    )
    vertex_water_hard = (
        _resize_float(
            water_mask.astype(np.float32),
            heightmap_width,
            heightmap_height,
            Image.Resampling.NEAREST,
        )
        >= 0.5
    )
    vertex_water_soft = _smooth_float(vertex_water_hard.astype(np.float32), shore_blur_iterations)

    vertex_height_norm = _normalize_01(vertex_height_norm)
    vertex_depth_norm = _normalize_01(vertex_depth_norm)
    land_interior = np.clip((0.5 - vertex_water_soft) / 0.5, 0.0, 1.0)
    water_interior = np.clip((vertex_water_soft - 0.5) / 0.5, 0.0, 1.0)
    water_depth = water_clearance + water_interior * (
        water_depth_range * (0.35 + vertex_depth_norm * 0.65)
    )
    land_height = water_level + land_clearance + land_interior * vertex_height_norm * land_height_range
    water_height = water_level - water_depth
    vertices = np.where(vertex_water_hard, water_height, land_height).astype(np.float32)
    return vertices, vertex_water_hard


def patch_scmap_heightmap(
    template_scmap: Path,
    generated_tensor: Path,
    out_scmap: Path,
    land_clearance: float = 0.35,
    land_height_range: float = 30.0,
    water_clearance: float = 0.25,
    water_depth_range: float = 10.0,
    shore_blur_iterations: int = 8,
) -> TerrainPatchSummary:
    data = bytearray(template_scmap.read_bytes())
    header = scmap_terrain._terrain_header(data)
    heightmap_width = header.map_width + 1
    heightmap_height = header.map_height + 1
    count = heightmap_width * heightmap_height
    height_byte_count = count * 2
    if header.height_offset + height_byte_count > len(data):
        raise ValueError("Template .scmap height block exceeds file size")

    water_level, water_source = _template_water_level(data)
    tensor, channels = _load_tensor(generated_tensor)
    vertices, _vertex_water = terrain_tensor_to_vertices(
        tensor=tensor,
        channels=channels,
        heightmap_width=heightmap_width,
        heightmap_height=heightmap_height,
        water_level=water_level,
        land_clearance=land_clearance,
        land_height_range=land_height_range,
        water_clearance=water_clearance,
        water_depth_range=water_depth_range,
        shore_blur_iterations=shore_blur_iterations,
    )

    raw_heights = np.clip(np.rint(vertices * 128.0), 0, 65535).astype("<u2")
    data[header.height_offset : header.height_offset + height_byte_count] = raw_heights.tobytes()
    out_scmap.parent.mkdir(parents=True, exist_ok=True)
    out_scmap.write_bytes(data)

    generated_water = _channel(tensor, channels, "water_mask", 1) >= 0.5
    written_heights = raw_heights.astype(np.float32) / 128.0
    return TerrainPatchSummary(
        template_scmap=str(template_scmap),
        out_scmap=str(out_scmap),
        map_width=header.map_width,
        map_height=header.map_height,
        heightmap_width=heightmap_width,
        heightmap_height=heightmap_height,
        height_offset=header.height_offset,
        water_level=round(float(water_level), 6),
        water_level_source=water_source,
        generated_water_percent=round(float(generated_water.mean() * 100.0), 6),
        written_water_percent=round(float((written_heights <= water_level).mean() * 100.0), 6),
        height_min=round(float(written_heights.min()), 6),
        height_max=round(float(written_heights.max()), 6),
        land_clearance=land_clearance,
        land_height_range=land_height_range,
        water_clearance=water_clearance,
        water_depth_range=water_depth_range,
        shore_blur_iterations=shore_blur_iterations,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Patch a generated terrain tensor into .scmap.")
    parser.add_argument("--template-scmap", required=True, type=Path)
    parser.add_argument("--generated-tensor", required=True, type=Path)
    parser.add_argument("--out-scmap", required=True, type=Path)
    parser.add_argument("--summary-out", type=Path)
    parser.add_argument("--land-clearance", default=0.35, type=float)
    parser.add_argument("--land-height-range", default=30.0, type=float)
    parser.add_argument("--water-clearance", default=0.25, type=float)
    parser.add_argument("--water-depth-range", default=10.0, type=float)
    parser.add_argument("--shore-blur-iterations", default=8, type=int)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary = patch_scmap_heightmap(
        template_scmap=args.template_scmap,
        generated_tensor=args.generated_tensor,
        out_scmap=args.out_scmap,
        land_clearance=args.land_clearance,
        land_height_range=args.land_height_range,
        water_clearance=args.water_clearance,
        water_depth_range=args.water_depth_range,
        shore_blur_iterations=args.shore_blur_iterations,
    )
    payload = asdict(summary)
    if args.summary_out:
        args.summary_out.parent.mkdir(parents=True, exist_ok=True)
        args.summary_out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
