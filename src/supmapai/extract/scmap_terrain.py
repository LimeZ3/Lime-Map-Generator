"""Decode first-pass terrain metrics from Supreme Commander .scmap files."""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import struct
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

CSV_COLUMNS = [
    "map_dir",
    "selected_map_dir",
    "scmap_path",
    "file_size_bytes",
    "decode_ms",
    "map_width",
    "map_height",
    "heightmap_width",
    "heightmap_height",
    "playable_area_source",
    "playable_x0",
    "playable_z0",
    "playable_x1",
    "playable_z1",
    "playable_width",
    "playable_height",
    "height_min",
    "height_max",
    "height_mean",
    "height_std",
    "water_level",
    "water_level_source",
    "water_percent",
    "shallow_water_percent",
    "medium_water_percent",
    "deep_water_percent",
    "water_depth_max",
    "water_depth_mean",
    "water_depth_p50",
    "water_depth_p95",
    "water_body_count",
    "largest_water_body_percent",
    "largest_water_body_depth_mean",
    "largest_water_body_depth_max",
    "water_bodies_json",
    "water_artifact_removed_cells",
    "water_artifact_removed_percent",
    "water_artifact_rule",
    "water_noise_removed_cells",
    "water_noise_removed_percent",
    "water_noise_rule",
    "land_percent",
    "buildable_percent",
    "non_buildable_slope_percent",
    "pathblocking_steep_percent",
    "land_unit_passable_percent",
    "land_unit_unpassable_percent",
    "land_unit_blocked_by_water_percent",
    "land_unit_blocked_by_steep_percent",
    "passable_land_component_count",
    "largest_passable_land_percent",
    "passable_land_components_json",
    "flat_height_mode_percent",
    "slope_mean",
    "slope_p95",
    "buildable_slope_threshold",
    "pathblocking_slope_threshold",
    "texture_pack",
    "texture_names_json",
    "preview_path",
    "water_depth_preview_path",
    "pathability_preview_path",
    "warnings",
]

DDS_MAGIC = b"DDS "
DDS_HEADER_SIZE = 128
HEIGHTMAP_PREFIX_BYTES = 16
TEXTURE_RE = re.compile(rb"(?P<path>/(?:env|textures)/[ -~]{1,220}\.dds)\x00", re.I)
NUMBER = r"[-+]?\d+(?:\.\d+)?"
RECTANGLE_RE = re.compile(
    rf"RECTANGLE\(\s*({NUMBER})\s*,\s*({NUMBER})\s*,\s*({NUMBER})\s*,\s*({NUMBER})\s*\)",
    re.I,
)
AREA_1_RE = re.compile(r"\['AREA_1'\]\s*=\s*{", re.I)
SIZE_RE = re.compile(r"\bsize\s*=\s*{\s*(\d+)\s*,\s*(\d+)\s*}", re.I)


@dataclass
class DDSHeader:
    offset: int
    width: int
    height: int
    mip_count: int
    fourcc: str
    rgb_bit_count: int


@dataclass
class ScmapTerrainHeader:
    version: int
    map_width: int
    map_height: int
    height_offset: int


def _read_i32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<i", data, offset)[0]


def _read_u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def _read_f32(data: bytes, offset: int) -> float:
    return struct.unpack_from("<f", data, offset)[0]


def _dds_header(data: bytes, offset: int) -> DDSHeader:
    if data[offset : offset + 4] != DDS_MAGIC:
        raise ValueError(f"DDS magic not found at offset {offset}")
    return DDSHeader(
        offset=offset,
        height=_read_u32(data, offset + 12),
        width=_read_u32(data, offset + 16),
        mip_count=max(_read_u32(data, offset + 28), 1),
        fourcc=data[offset + 84 : offset + 88].rstrip(b"\x00").decode("ascii", errors="ignore"),
        rgb_bit_count=_read_u32(data, offset + 88),
    )


def _mip_extent(value: int, level: int) -> int:
    return max(1, value >> level)


def _dds_data_size(header: DDSHeader) -> int:
    total = 0
    for level in range(header.mip_count):
        width = _mip_extent(header.width, level)
        height = _mip_extent(header.height, level)
        if header.fourcc:
            block_size = 8 if header.fourcc == "DXT1" else 16
            total += max(1, math.ceil(width / 4)) * max(1, math.ceil(height / 4)) * block_size
        else:
            bytes_per_pixel = max(header.rgb_bit_count // 8, 1)
            total += width * height * bytes_per_pixel
    return DDS_HEADER_SIZE + total


def _first_dds_offset(data: bytes) -> int:
    offset = data.find(DDS_MAGIC)
    if offset < 0:
        raise ValueError("No embedded DDS section found")
    return offset


def _heightmap_offset(data: bytes) -> tuple[int, DDSHeader]:
    preview_offset = _first_dds_offset(data)
    preview_header = _dds_header(data, preview_offset)
    return preview_offset + _dds_data_size(preview_header) + HEIGHTMAP_PREFIX_BYTES, preview_header


def _terrain_header(data: bytes) -> ScmapTerrainHeader:
    offset = 0
    offset += 4 * 4
    offset += 4 * 2
    offset += 4
    offset += 2

    preview_byte_count = _read_i32(data, offset)
    if preview_byte_count < DDS_HEADER_SIZE:
        raise ValueError(f"Invalid preview image byte count: {preview_byte_count}")
    offset += 4 + preview_byte_count

    version = _read_i32(data, offset)
    offset += 4
    map_width = _read_i32(data, offset)
    offset += 4
    map_height = _read_i32(data, offset)
    offset += 4
    offset += 4

    if version not in (52, 53, 56, 60):
        raise ValueError(f"Unsupported SCMAP terrain version: {version}")
    if map_width < 2 or map_height < 2 or map_width > 8192 or map_height > 8192:
        raise ValueError(f"Invalid SCMAP terrain size: {map_width}x{map_height}")

    return ScmapTerrainHeader(
        version=version,
        map_width=map_width,
        map_height=map_height,
        height_offset=offset,
    )


def _extract_textures(data: bytes) -> list[str]:
    textures = []
    seen = set()
    for match in TEXTURE_RE.finditer(data):
        texture = match.group("path").decode("ascii", errors="ignore")
        if texture not in seen:
            seen.add(texture)
            textures.append(texture)
    return textures


def _texture_pack(textures: list[str]) -> str:
    env_paths = [texture for texture in textures if texture.lower().startswith("/env/")]
    if not env_paths:
        return ""
    parts = env_paths[0].split("/")
    return parts[2] if len(parts) > 2 else ""


def _water_fraction_for_level(heights: np.ndarray, level: float) -> float:
    return float((heights <= level).mean()) if heights.size else 0.0


def _valid_water_level_candidate(heights: np.ndarray, value: float) -> bool:
    low = -100.0
    high = float(heights.max() + 5)
    if not math.isfinite(value) or value < low or value > high:
        return False
    return _water_fraction_for_level(heights, value) >= 0.001


def _flagged_waterramp_elevation_candidates(
    heights: np.ndarray,
    data: bytes,
    waterramp: int,
) -> list[float]:
    candidates = []
    seen = set()
    start = max(0, waterramp - 260)
    end = max(start, waterramp - 70)
    for offset in range(start, min(end, len(data) - 4)):
        if data[offset : offset + 3] != b"\x01\x00\x00":
            continue
        value = _read_f32(data, offset + 1)
        rounded = round(value, 5)
        if rounded in seen:
            continue
        if _valid_water_level_candidate(heights, value):
            seen.add(rounded)
            candidates.append(float(value))
    candidates.sort(key=lambda level: _water_fraction_for_level(heights, level))
    return candidates


def _water_level_from_waterramp_block(heights: np.ndarray, data: bytes) -> tuple[float | None, str]:
    waterramp = data.find(b"/textures/engine/waterramp.dds")
    if waterramp < 126:
        return None, ""

    # In FAF .scmap files tested so far, the water elevation lives in the
    # serialized water block 126 bytes before the waterramp texture path.
    value = _read_f32(data, waterramp - 126)
    if _valid_water_level_candidate(heights, value):
        return float(value), "waterramp_block_elevation"

    flagged_candidates = _flagged_waterramp_elevation_candidates(heights, data, waterramp)
    if flagged_candidates:
        return flagged_candidates[0], "waterramp_flagged_elevation"
    return None, ""


def _infer_water_level(heights: np.ndarray, data: bytes) -> tuple[float | None, str]:
    waterramp_level, waterramp_source = _water_level_from_waterramp_block(heights, data)
    if waterramp_level is not None:
        return waterramp_level, waterramp_source

    # Fallback: common FA water sits just under the first large land plateau.
    hist, edges = np.histogram(heights, bins=128)
    peak_index = int(hist.argmax())
    return float(edges[max(0, peak_index - 1)]), "height_histogram_fallback_uncertain"


def _water_depth_stats(
    heights: np.ndarray,
    water_level: float | None,
    water_mask: np.ndarray | None = None,
) -> dict[str, float | str]:
    if water_level is None:
        return {
            "water_percent": "",
            "land_percent": "",
            "shallow_water_percent": "",
            "medium_water_percent": "",
            "deep_water_percent": "",
            "water_depth_max": "",
            "water_depth_mean": "",
            "water_depth_p50": "",
            "water_depth_p95": "",
        }

    depth = water_level - heights
    if water_mask is None:
        water_mask = depth >= 0
    water_depths = depth[water_mask]
    return {
        "water_percent": float(water_mask.mean() * 100),
        "land_percent": float((~water_mask).mean() * 100),
        "shallow_water_percent": float((water_mask & (depth <= 2)).mean() * 100),
        "medium_water_percent": float((water_mask & (depth > 2) & (depth <= 8)).mean() * 100),
        "deep_water_percent": float((water_mask & (depth > 8)).mean() * 100),
        "water_depth_max": float(water_depths.max()) if water_depths.size else 0.0,
        "water_depth_mean": float(water_depths.mean()) if water_depths.size else 0.0,
        "water_depth_p50": float(np.percentile(water_depths, 50)) if water_depths.size else 0.0,
        "water_depth_p95": float(np.percentile(water_depths, 95)) if water_depths.size else 0.0,
    }


def _read_text(path: Path | None) -> str:
    if path is None:
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _block_end(text: str, open_brace_index: int) -> int:
    depth = 0
    in_string: str | None = None
    index = open_brace_index
    while index < len(text):
        char = text[index]
        if in_string:
            if char == "\\":
                index += 2
                continue
            if char == in_string:
                in_string = None
        elif char in ("'", '"'):
            in_string = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index + 1
        index += 1
    return len(text)


def _area_1_rectangle(save_lua_path: Path | None) -> tuple[float, float, float, float] | None:
    text = _read_text(save_lua_path)
    match = AREA_1_RE.search(text)
    if not match:
        return None
    open_index = text.find("{", match.end() - 1)
    if open_index < 0:
        return None
    block = text[open_index : _block_end(text, open_index)]
    rectangle_match = RECTANGLE_RE.search(block)
    if not rectangle_match:
        return None
    return tuple(float(value) for value in rectangle_match.groups())


def _scenario_size(scenario_lua_path: Path | None) -> tuple[int, int] | None:
    text = _read_text(scenario_lua_path)
    match = SIZE_RE.search(text)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def _playable_slice(
    shape: tuple[int, int],
    rectangle: tuple[float, float, float, float] | None,
) -> tuple[slice, slice, dict[str, Any]]:
    height, width = shape
    if rectangle is None:
        return (
            slice(0, height),
            slice(0, width),
            {
                "playable_area_source": "full_map",
                "playable_x0": 0,
                "playable_z0": 0,
                "playable_x1": width,
                "playable_z1": height,
                "playable_width": width,
                "playable_height": height,
            },
        )

    x0, z0, x1, z1 = rectangle
    left = max(0, min(width, int(math.ceil(x0))))
    top = max(0, min(height, int(math.ceil(z0))))
    right = max(0, min(width, int(math.floor(x1))))
    bottom = max(0, min(height, int(math.floor(z1))))
    if right - left < 2 or bottom - top < 2:
        return (
            slice(0, height),
            slice(0, width),
            {
                "playable_area_source": "invalid_save_lua_area_1_fallback_full_map",
                "playable_x0": 0,
                "playable_z0": 0,
                "playable_x1": width,
                "playable_z1": height,
                "playable_width": width,
                "playable_height": height,
            },
        )
    return (
        slice(top, bottom),
        slice(left, right),
        {
            "playable_area_source": "save_lua_area_1",
            "playable_x0": left,
            "playable_z0": top,
            "playable_x1": right,
            "playable_z1": bottom,
            "playable_width": right - left,
            "playable_height": bottom - top,
        },
    )


def _flat_height_mode_percent(heights: np.ndarray) -> float:
    rounded = np.round(heights * 2) / 2
    values, counts = np.unique(rounded, return_counts=True)
    if len(values) == 0:
        return 0.0
    return float(counts.max() / rounded.size * 100)


def _height_vertices_to_cells(heights: np.ndarray) -> np.ndarray:
    return (
        heights[:-1, :-1]
        + heights[1:, :-1]
        + heights[:-1, 1:]
        + heights[1:, 1:]
    ) * 0.25


def _remove_corner_water_artifacts(
    water_mask: np.ndarray,
    corner_size_cells: int,
) -> tuple[np.ndarray, int]:
    if corner_size_cells <= 0:
        return water_mask, 0

    height, width = water_mask.shape
    cleaned = water_mask.copy()
    seen = np.zeros_like(water_mask, dtype=bool)
    removed = 0

    edge_seeds = []
    for x in range(width):
        edge_seeds.append((0, x))
        edge_seeds.append((height - 1, x))
    for y in range(1, height - 1):
        edge_seeds.append((y, 0))
        edge_seeds.append((y, width - 1))

    for seed_y, seed_x in edge_seeds:
        if not cleaned[seed_y, seed_x] or seen[seed_y, seed_x]:
            continue

        stack = [(seed_y, seed_x)]
        seen[seed_y, seed_x] = True
        cells = []
        min_y = max_y = seed_y
        min_x = max_x = seed_x

        while stack:
            y, x = stack.pop()
            cells.append((y, x))
            min_y = min(min_y, y)
            max_y = max(max_y, y)
            min_x = min(min_x, x)
            max_x = max(max_x, x)

            for next_y, next_x in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                if (
                    0 <= next_y < height
                    and 0 <= next_x < width
                    and cleaned[next_y, next_x]
                    and not seen[next_y, next_x]
                ):
                    seen[next_y, next_x] = True
                    stack.append((next_y, next_x))

        in_left = max_x < corner_size_cells
        in_right = min_x >= width - corner_size_cells
        in_top = max_y < corner_size_cells
        in_bottom = min_y >= height - corner_size_cells
        if (in_left or in_right) and (in_top or in_bottom):
            for y, x in cells:
                cleaned[y, x] = False
            removed += len(cells)

    return cleaned, removed


def _remove_small_water_components(
    water_mask: np.ndarray,
    min_component_cells: int,
) -> tuple[np.ndarray, int]:
    if min_component_cells <= 1:
        return water_mask, 0

    height, width = water_mask.shape
    cleaned = water_mask.copy()
    seen = np.zeros_like(water_mask, dtype=bool)
    removed = 0

    for seed_y in range(height):
        for seed_x in range(width):
            if not cleaned[seed_y, seed_x] or seen[seed_y, seed_x]:
                continue

            stack = [(seed_y, seed_x)]
            seen[seed_y, seed_x] = True
            cells = []
            while stack:
                y, x = stack.pop()
                cells.append((y, x))
                for next_y, next_x in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                    if (
                        0 <= next_y < height
                        and 0 <= next_x < width
                        and cleaned[next_y, next_x]
                        and not seen[next_y, next_x]
                    ):
                        seen[next_y, next_x] = True
                        stack.append((next_y, next_x))

            if len(cells) < min_component_cells:
                for y, x in cells:
                    cleaned[y, x] = False
                removed += len(cells)

    return cleaned, removed


def _water_body_summaries(
    depth: np.ndarray,
    water_mask: np.ndarray | None,
    max_bodies: int = 12,
) -> dict[str, Any]:
    if water_mask is None or not water_mask.any():
        return {
            "water_body_count": 0,
            "largest_water_body_percent": 0.0,
            "largest_water_body_depth_mean": 0.0,
            "largest_water_body_depth_max": 0.0,
            "water_bodies": [],
        }

    height, width = water_mask.shape
    seen = np.zeros_like(water_mask, dtype=bool)
    bodies: list[dict[str, Any]] = []

    for seed_y in range(height):
        for seed_x in range(width):
            if not water_mask[seed_y, seed_x] or seen[seed_y, seed_x]:
                continue

            stack = [(seed_y, seed_x)]
            seen[seed_y, seed_x] = True
            xs = []
            ys = []
            while stack:
                y, x = stack.pop()
                ys.append(y)
                xs.append(x)
                for next_y, next_x in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                    if (
                        0 <= next_y < height
                        and 0 <= next_x < width
                        and water_mask[next_y, next_x]
                        and not seen[next_y, next_x]
                    ):
                        seen[next_y, next_x] = True
                        stack.append((next_y, next_x))

            body_depth = depth[ys, xs]
            area_cells = len(xs)
            bodies.append(
                {
                    "area_cells": area_cells,
                    "area_percent": round(float(area_cells / water_mask.size * 100), 6),
                    "bbox": [int(min(xs)), int(min(ys)), int(max(xs) + 1), int(max(ys) + 1)],
                    "depth_mean": round(float(body_depth.mean()), 4),
                    "depth_p50": round(float(np.percentile(body_depth, 50)), 4),
                    "depth_p95": round(float(np.percentile(body_depth, 95)), 4),
                    "depth_max": round(float(body_depth.max()), 4),
                }
            )

    bodies.sort(key=lambda body: body["area_cells"], reverse=True)
    largest = bodies[0] if bodies else {}
    return {
        "water_body_count": len(bodies),
        "largest_water_body_percent": largest.get("area_percent", 0.0),
        "largest_water_body_depth_mean": largest.get("depth_mean", 0.0),
        "largest_water_body_depth_max": largest.get("depth_max", 0.0),
        "water_bodies": bodies[:max_bodies],
    }


def _mask_component_summaries(
    mask: np.ndarray,
    max_components: int = 12,
) -> dict[str, Any]:
    if not mask.any():
        return {
            "component_count": 0,
            "largest_component_percent": 0.0,
            "components": [],
        }

    height, width = mask.shape
    seen = np.zeros_like(mask, dtype=bool)
    components: list[dict[str, Any]] = []

    for seed_y in range(height):
        for seed_x in range(width):
            if not mask[seed_y, seed_x] or seen[seed_y, seed_x]:
                continue

            stack = [(seed_y, seed_x)]
            seen[seed_y, seed_x] = True
            xs = []
            ys = []
            while stack:
                y, x = stack.pop()
                ys.append(y)
                xs.append(x)
                for next_y, next_x in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                    if (
                        0 <= next_y < height
                        and 0 <= next_x < width
                        and mask[next_y, next_x]
                        and not seen[next_y, next_x]
                    ):
                        seen[next_y, next_x] = True
                        stack.append((next_y, next_x))

            area_cells = len(xs)
            components.append(
                {
                    "area_cells": area_cells,
                    "area_percent": round(float(area_cells / mask.size * 100), 6),
                    "bbox": [int(min(xs)), int(min(ys)), int(max(xs) + 1), int(max(ys) + 1)],
                }
            )

    components.sort(key=lambda component: component["area_cells"], reverse=True)
    largest = components[0] if components else {}
    return {
        "component_count": len(components),
        "largest_component_percent": largest.get("area_percent", 0.0),
        "components": components[:max_components],
    }


def _write_preview(
    heights: np.ndarray,
    water_level: float | None,
    out_path: Path,
    water_mask: np.ndarray | None = None,
) -> None:
    normalized = (heights - heights.min()) / max(float(heights.max() - heights.min()), 1e-6)
    image = np.zeros((*heights.shape, 3), dtype=np.uint8)
    image[..., 0] = (normalized * 180 + 40).astype(np.uint8)
    image[..., 1] = (normalized * 180 + 40).astype(np.uint8)
    image[..., 2] = (normalized * 180 + 40).astype(np.uint8)
    if water_level is not None:
        if water_mask is None:
            water_mask = heights <= water_level
        image[water_mask, 0] = 35
        image[water_mask, 1] = 95
        image[water_mask, 2] = 170
    out_path.parent.mkdir(parents=True, exist_ok=True)
    max_size = 512
    height, width = image.shape[:2]
    scale = min(max_size / width, max_size / height, 1.0)
    out_size = (max(1, round(width * scale)), max(1, round(height * scale)))
    Image.fromarray(image).resize(out_size, Image.Resampling.BILINEAR).save(out_path)


def _write_water_depth_preview(
    depth: np.ndarray,
    water_mask: np.ndarray | None,
    out_path: Path,
) -> None:
    depth_image = np.zeros((*depth.shape, 3), dtype=np.uint8)
    if water_mask is not None and water_mask.any():
        water_depth = np.clip(depth, 0, None)
        max_depth = max(float(water_depth[water_mask].max()), 1e-6)
        normalized = np.zeros_like(water_depth, dtype=np.float32)
        normalized[water_mask] = water_depth[water_mask] / max_depth
        depth_image[water_mask, 0] = (20 + normalized[water_mask] * 20).astype(np.uint8)
        depth_image[water_mask, 1] = (95 + normalized[water_mask] * 80).astype(np.uint8)
        depth_image[water_mask, 2] = (150 + normalized[water_mask] * 105).astype(np.uint8)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    max_size = 512
    height, width = depth_image.shape[:2]
    scale = min(max_size / width, max_size / height, 1.0)
    out_size = (max(1, round(width * scale)), max(1, round(height * scale)))
    Image.fromarray(depth_image).resize(out_size, Image.Resampling.BILINEAR).save(out_path)


def _write_pathability_preview(
    passable_mask: np.ndarray,
    water_mask: np.ndarray | None,
    steep_mask: np.ndarray,
    out_path: Path,
) -> None:
    image = np.zeros((*passable_mask.shape, 3), dtype=np.uint8)
    image[passable_mask] = [70, 150, 75]
    image[steep_mask] = [180, 60, 55]
    if water_mask is not None:
        image[water_mask] = [35, 95, 170]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    max_size = 512
    height, width = image.shape[:2]
    scale = min(max_size / width, max_size / height, 1.0)
    out_size = (max(1, round(width * scale)), max(1, round(height * scale)))
    Image.fromarray(image).resize(out_size, Image.Resampling.NEAREST).save(out_path)


def _write_placeholder_preview(
    width: int,
    height: int,
    color: tuple[int, int, int],
    out_path: Path,
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    scale = min(512 / max(width, 1), 512 / max(height, 1), 1.0)
    out_size = (max(1, round(width * scale)), max(1, round(height * scale)))
    Image.new("RGB", out_size, color).save(out_path)


def _safe_warning(exc: Exception) -> str:
    message = str(exc).replace("|", ";").replace("\r", " ").replace("\n", " ")
    return f"scmap_terrain_decode_failed:{type(exc).__name__}:{message}"


def _failed_decode_row(
    scmap_path: Path,
    map_dir: str,
    selected_map_dir: str,
    scenario_lua_path: Path | None,
    preview_dir: Path | None,
    exc: Exception,
) -> dict[str, Any]:
    started = time.perf_counter()
    size = _scenario_size(scenario_lua_path)
    preview_size = size or (512, 512)
    map_width = preview_size[0]
    map_height = preview_size[1]
    playable_area_source = (
        "terrain_decode_failed_scenario_size" if size else "terrain_decode_failed_default_512"
    )
    playable_area = {
        "playable_area_source": playable_area_source,
        "playable_x0": 0,
        "playable_z0": 0,
        "playable_x1": map_width,
        "playable_z1": map_height,
        "playable_width": map_width,
        "playable_height": map_height,
    }

    preview_path = ""
    water_depth_preview_path = ""
    pathability_preview_path = ""
    if preview_dir is not None:
        preview_path_obj = preview_dir / f"{map_dir or scmap_path.stem}.terrain.png"
        water_depth_preview_path_obj = preview_dir / f"{map_dir or scmap_path.stem}.water_depth.png"
        pathability_preview_path_obj = preview_dir / f"{map_dir or scmap_path.stem}.pathability.png"
        _write_placeholder_preview(preview_size[0], preview_size[1], (55, 55, 55), preview_path_obj)
        _write_placeholder_preview(
            preview_size[0],
            preview_size[1],
            (0, 0, 0),
            water_depth_preview_path_obj,
        )
        _write_placeholder_preview(
            preview_size[0],
            preview_size[1],
            (28, 30, 34),
            pathability_preview_path_obj,
        )
        preview_path = str(preview_path_obj)
        water_depth_preview_path = str(water_depth_preview_path_obj)
        pathability_preview_path = str(pathability_preview_path_obj)

    row = {column: "" for column in CSV_COLUMNS}
    row.update(
        {
            "map_dir": map_dir,
            "selected_map_dir": selected_map_dir,
            "scmap_path": str(scmap_path),
            "file_size_bytes": scmap_path.stat().st_size if scmap_path.exists() else "",
            "decode_ms": round((time.perf_counter() - started) * 1000, 3),
            "map_width": map_width,
            "map_height": map_height,
            "heightmap_width": map_width + 1,
            "heightmap_height": map_height + 1,
            **playable_area,
            "water_bodies_json": "[]",
            "passable_land_components_json": "[]",
            "texture_names_json": "[]",
            "preview_path": preview_path,
            "water_depth_preview_path": water_depth_preview_path,
            "pathability_preview_path": pathability_preview_path,
            "warnings": _safe_warning(exc),
        }
    )
    return row


def decode_scmap(
    scmap_path: Path,
    map_dir: str = "",
    selected_map_dir: str = "",
    save_lua_path: Path | None = None,
    preview_dir: Path | None = None,
    buildable_slope_threshold: float = 0.1,
    pathblocking_slope_threshold: float = 0.7,
    corner_artifact_cells: int = 0,
    uncertain_water_min_component_cells: int = 64,
) -> dict[str, Any]:
    started = time.perf_counter()
    warnings: list[str] = []
    data = scmap_path.read_bytes()
    if data[:4] != b"Map\x1a":
        raise ValueError(f"Unrecognized .scmap header: {scmap_path}")

    terrain_header = _terrain_header(data)
    map_width = terrain_header.map_width
    map_height = terrain_header.map_height
    heightmap_width = map_width + 1
    heightmap_height = map_height + 1
    height_offset = terrain_header.height_offset
    height_count = heightmap_width * heightmap_height
    height_bytes = height_count * 2
    if height_offset + height_bytes > len(data):
        raise ValueError("Heightmap block exceeds file size")

    raw = np.frombuffer(
        data,
        dtype="<u2",
        count=height_count,
        offset=height_offset,
    ).reshape((heightmap_height, heightmap_width))
    vertex_heights = raw.astype(np.float32) / 128.0
    heights = _height_vertices_to_cells(vertex_heights)
    playable_z_slice, playable_x_slice, playable_area = _playable_slice(
        heights.shape,
        _area_1_rectangle(save_lua_path),
    )
    heights = heights[playable_z_slice, playable_x_slice]
    if min(heights.shape) < 2:
        warnings.append("playable_crop_too_small_fallback_full_map")
        playable_z_slice, playable_x_slice, playable_area = _playable_slice(
            (map_height, map_width),
            None,
        )
        heights = _height_vertices_to_cells(vertex_heights)[playable_z_slice, playable_x_slice]
    elif playable_area["playable_area_source"] == "invalid_save_lua_area_1_fallback_full_map":
        warnings.append("invalid_save_lua_area_1_fallback_full_map")
    water_level, water_source = _infer_water_level(heights, data)
    cell_x = map_width / max(heightmap_width - 1, 1)
    cell_z = map_height / max(heightmap_height - 1, 1)
    gradient_z, gradient_x = np.gradient(heights, cell_z, cell_x)
    slope = np.sqrt(gradient_x * gradient_x + gradient_z * gradient_z)
    land_mask = np.ones_like(heights, dtype=bool)
    water_mask = None
    water_artifact_removed_cells = 0
    water_noise_removed_cells = 0
    if water_level is not None:
        water_mask = (water_level - heights) >= 0
        water_mask, water_artifact_removed_cells = _remove_corner_water_artifacts(
            water_mask,
            corner_artifact_cells,
        )
        if water_source == "height_histogram_fallback_uncertain":
            water_mask, water_noise_removed_cells = _remove_small_water_components(
                water_mask,
                uncertain_water_min_component_cells,
            )
        land_mask = ~water_mask
    else:
        warnings.append("water_level_unknown")
    if water_source == "height_histogram_fallback_uncertain":
        warnings.append("water_level_inferred_from_height_histogram")
    if water_source == "waterramp_flagged_elevation":
        warnings.append("water_level_from_flagged_waterramp_field")
    if water_artifact_removed_cells:
        warnings.append("corner_water_artifacts_removed")
    if water_noise_removed_cells:
        warnings.append("uncertain_water_small_components_removed")
    depth = water_level - heights if water_level is not None else np.zeros_like(heights)
    water_stats = _water_depth_stats(heights, water_level, water_mask)
    water_bodies = _water_body_summaries(depth, water_mask)

    buildable_mask = land_mask & (slope <= buildable_slope_threshold)
    slope_mask = land_mask & (slope > buildable_slope_threshold) & (
        slope <= pathblocking_slope_threshold
    )
    steep_mask = land_mask & (slope > pathblocking_slope_threshold)
    passable_land_mask = land_mask & (slope <= pathblocking_slope_threshold)
    water_blocked_mask = water_mask if water_mask is not None else np.zeros_like(land_mask)
    land_unit_unpassable_mask = water_blocked_mask | steep_mask
    passable_land_components = _mask_component_summaries(passable_land_mask)
    textures = _extract_textures(data)
    preview_path = ""
    water_depth_preview_path = ""
    pathability_preview_path = ""
    if preview_dir is not None:
        preview_path_obj = preview_dir / f"{map_dir or scmap_path.stem}.terrain.png"
        _write_preview(heights, water_level, preview_path_obj, water_mask)
        preview_path = str(preview_path_obj)
        water_depth_preview_path_obj = preview_dir / (
            f"{map_dir or scmap_path.stem}.water_depth.png"
        )
        _write_water_depth_preview(depth, water_mask, water_depth_preview_path_obj)
        water_depth_preview_path = str(water_depth_preview_path_obj)
        pathability_preview_path_obj = preview_dir / (
            f"{map_dir or scmap_path.stem}.pathability.png"
        )
        _write_pathability_preview(
            passable_land_mask,
            water_mask,
            steep_mask,
            pathability_preview_path_obj,
        )
        pathability_preview_path = str(pathability_preview_path_obj)

    decoded_ms = (time.perf_counter() - started) * 1000
    return {
        "map_dir": map_dir,
        "selected_map_dir": selected_map_dir,
        "scmap_path": str(scmap_path),
        "file_size_bytes": len(data),
        "decode_ms": round(decoded_ms, 3),
        "map_width": map_width,
        "map_height": map_height,
        "heightmap_width": heightmap_width,
        "heightmap_height": heightmap_height,
        **playable_area,
        "height_min": round(float(heights.min()), 4),
        "height_max": round(float(heights.max()), 4),
        "height_mean": round(float(heights.mean()), 4),
        "height_std": round(float(heights.std()), 4),
        "water_level": round(water_level, 4) if water_level is not None else "",
        "water_level_source": water_source,
        "water_percent": round(water_stats["water_percent"], 4)
        if water_stats["water_percent"] != ""
        else "",
        "shallow_water_percent": round(water_stats["shallow_water_percent"], 4)
        if water_stats["shallow_water_percent"] != ""
        else "",
        "medium_water_percent": round(water_stats["medium_water_percent"], 4)
        if water_stats["medium_water_percent"] != ""
        else "",
        "deep_water_percent": round(water_stats["deep_water_percent"], 4)
        if water_stats["deep_water_percent"] != ""
        else "",
        "water_depth_max": round(water_stats["water_depth_max"], 4)
        if water_stats["water_depth_max"] != ""
        else "",
        "water_depth_mean": round(water_stats["water_depth_mean"], 4)
        if water_stats["water_depth_mean"] != ""
        else "",
        "water_depth_p50": round(water_stats["water_depth_p50"], 4)
        if water_stats["water_depth_p50"] != ""
        else "",
        "water_depth_p95": round(water_stats["water_depth_p95"], 4)
        if water_stats["water_depth_p95"] != ""
        else "",
        "water_body_count": water_bodies["water_body_count"],
        "largest_water_body_percent": water_bodies["largest_water_body_percent"],
        "largest_water_body_depth_mean": water_bodies["largest_water_body_depth_mean"],
        "largest_water_body_depth_max": water_bodies["largest_water_body_depth_max"],
        "water_bodies_json": json.dumps(water_bodies["water_bodies"], sort_keys=True),
        "water_artifact_removed_cells": water_artifact_removed_cells,
        "water_artifact_removed_percent": round(
            float(water_artifact_removed_cells / heights.size * 100),
            6,
        ),
        "water_artifact_rule": f"corner_components_within_{corner_artifact_cells}_cells",
        "water_noise_removed_cells": water_noise_removed_cells,
        "water_noise_removed_percent": round(
            float(water_noise_removed_cells / heights.size * 100),
            6,
        ),
        "water_noise_rule": (
            f"uncertain_water_components_below_{uncertain_water_min_component_cells}_cells"
        ),
        "land_percent": round(water_stats["land_percent"], 4)
        if water_stats["land_percent"] != ""
        else "",
        "buildable_percent": round(float(buildable_mask.mean() * 100), 4),
        "non_buildable_slope_percent": round(float(slope_mask.mean() * 100), 4),
        "pathblocking_steep_percent": round(float(steep_mask.mean() * 100), 4),
        "land_unit_passable_percent": round(float(passable_land_mask.mean() * 100), 4),
        "land_unit_unpassable_percent": round(float(land_unit_unpassable_mask.mean() * 100), 4),
        "land_unit_blocked_by_water_percent": round(float(water_blocked_mask.mean() * 100), 4),
        "land_unit_blocked_by_steep_percent": round(float(steep_mask.mean() * 100), 4),
        "passable_land_component_count": passable_land_components["component_count"],
        "largest_passable_land_percent": passable_land_components["largest_component_percent"],
        "passable_land_components_json": json.dumps(
            passable_land_components["components"],
            sort_keys=True,
        ),
        "flat_height_mode_percent": round(_flat_height_mode_percent(heights), 4),
        "slope_mean": round(float(slope.mean()), 6),
        "slope_p95": round(float(np.percentile(slope, 95)), 6),
        "buildable_slope_threshold": buildable_slope_threshold,
        "pathblocking_slope_threshold": pathblocking_slope_threshold,
        "texture_pack": _texture_pack(textures),
        "texture_names_json": json.dumps(textures, sort_keys=True),
        "preview_path": preview_path,
        "water_depth_preview_path": water_depth_preview_path,
        "pathability_preview_path": pathability_preview_path,
        "warnings": "|".join(warnings),
    }


def _file_entries(map_record: dict[str, Any], key: str) -> list[dict[str, Any]]:
    direct_entries = map_record.get(key)
    if direct_entries is not None:
        return direct_entries
    return map_record.get("files", {}).get(key, [])


def _first_scmap_path(map_record: dict[str, Any], maps_root: Path) -> Path | None:
    entries = _file_entries(map_record, "scmap")
    if not entries:
        return None
    return maps_root / Path(entries[0]["path"])


def _first_save_lua_path(map_record: dict[str, Any], maps_root: Path) -> Path | None:
    entries = _file_entries(map_record, "save_lua")
    if not entries:
        return None
    return maps_root / Path(entries[0]["path"])


def _first_scenario_lua_path(map_record: dict[str, Any], maps_root: Path) -> Path | None:
    entries = _file_entries(map_record, "scenario_lua")
    if not entries:
        return None
    return maps_root / Path(entries[0]["path"])


def decode_inventory(
    inventory: dict[str, Any],
    map_dir_filter: str | None,
    max_maps: int,
    preview_dir: Path | None,
    corner_artifact_cells: int,
    uncertain_water_min_component_cells: int,
) -> list[dict[str, Any]]:
    maps_root = Path(inventory["maps_root"])
    selected = []
    for map_record in inventory.get("maps", []):
        map_dir = map_record.get("top_level_dir") or map_record.get("map_dir") or ""
        if map_dir_filter and map_dir != map_dir_filter:
            continue
        selected.append(map_record)

    if len(selected) > max_maps:
        raise ValueError(
            f"Refusing to decode {len(selected)} maps with --max-maps {max_maps}. "
            "Pass a specific --map-dir or raise --max-maps deliberately."
        )

    rows = []
    for map_record in selected:
        scmap_path = _first_scmap_path(map_record, maps_root)
        if scmap_path is None:
            continue
        save_lua_path = _first_save_lua_path(map_record, maps_root)
        scenario_lua_path = _first_scenario_lua_path(map_record, maps_root)
        map_dir = map_record.get("top_level_dir") or map_record.get("map_dir") or ""
        try:
            rows.append(
                decode_scmap(
                    scmap_path=scmap_path,
                    map_dir=map_dir,
                    selected_map_dir=map_record.get("selected_map_dir", ""),
                    save_lua_path=save_lua_path,
                    preview_dir=preview_dir,
                    corner_artifact_cells=corner_artifact_cells,
                    uncertain_water_min_component_cells=uncertain_water_min_component_cells,
                )
            )
        except Exception as exc:
            rows.append(
                _failed_decode_row(
                    scmap_path=scmap_path,
                    map_dir=map_dir,
                    selected_map_dir=map_record.get("selected_map_dir", ""),
                    scenario_lua_path=scenario_lua_path,
                    preview_dir=preview_dir,
                    exc=exc,
                )
            )
    return rows


def write_csv(rows: list[dict[str, Any]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Decode first-pass terrain metrics from .scmap files."
    )
    parser.add_argument("--inventory", type=Path, help="Canonical inventory JSON.")
    parser.add_argument("--map-dir", help="Canonical top-level map folder to decode.")
    parser.add_argument("--scmap", type=Path, help="Direct .scmap path for one-off decoding.")
    parser.add_argument("--save-lua", type=Path, help="Optional _save.lua for playable AREA_1.")
    parser.add_argument("--out", required=True, type=Path, help="Output terrain metrics CSV.")
    parser.add_argument(
        "--preview-dir",
        type=Path,
        help="Optional output directory for PNG previews.",
    )
    parser.add_argument(
        "--max-maps",
        type=int,
        default=1,
        help="Safety limit. Defaults to 1 to avoid accidental large dataset runs.",
    )
    parser.add_argument(
        "--corner-artifact-cells",
        type=int,
        default=0,
        help=(
            "Remove water components fully confined to a map corner square of this size. "
            "Use 0 to disable."
        ),
    )
    parser.add_argument(
        "--uncertain-water-min-component-cells",
        type=int,
        default=64,
        help=(
            "For histogram-inferred water only, remove water components smaller than this. "
            "Use 0 to disable."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.scmap:
        rows = [
            decode_scmap(
                args.scmap,
                map_dir=args.scmap.parent.name,
                save_lua_path=args.save_lua,
                preview_dir=args.preview_dir,
                corner_artifact_cells=args.corner_artifact_cells,
                uncertain_water_min_component_cells=args.uncertain_water_min_component_cells,
            )
        ]
    elif args.inventory:
        inventory = json.loads(args.inventory.read_text(encoding="utf-8-sig"))
        rows = decode_inventory(
            inventory,
            args.map_dir,
            args.max_maps,
            args.preview_dir,
            args.corner_artifact_cells,
            args.uncertain_water_min_component_cells,
        )
    else:
        raise SystemExit("Provide either --scmap or --inventory.")

    write_csv(rows, args.out)
    print(f"Wrote {len(rows)} terrain row(s) to {args.out}")
    for row in rows:
        print(
            f"{row['map_dir']}: decoded {row['file_size_bytes']} bytes in "
            f"{row['decode_ms']} ms"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
