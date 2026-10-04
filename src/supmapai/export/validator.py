"""Basic generated-map structure validator.

V1 scope is deliberately practical: keep the generated design, but repair points
that would obviously fail in game, such as markers in water, resources on steep
terrain, exact duplicates, and reclaim placed on invalid terrain.
"""

from __future__ import annotations

import argparse
import json
import math
from copy import deepcopy
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw

from supmapai.extract import scmap_terrain
from supmapai.export import scmap_writer

POINT_LAYERS = ("spawns", "mexes", "hydros")


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


def _erode_bool(mask: np.ndarray, radius: int) -> np.ndarray:
    if radius <= 0:
        return mask.copy()
    eroded = mask.copy()
    height, width = mask.shape
    padded = np.pad(mask, radius, mode="constant", constant_values=False)
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if dx * dx + dy * dy > radius * radius:
                continue
            y0 = radius + dy
            x0 = radius + dx
            eroded &= padded[y0 : y0 + height, x0 : x0 + width]
    return eroded


def _final_written_layers(
    tensor: np.ndarray,
    channels: list[str],
    template_scmap: Path,
    grid_size: int,
) -> tuple[np.ndarray, np.ndarray, str, float]:
    data = template_scmap.read_bytes()
    header = scmap_terrain._terrain_header(data)
    water_level, water_source = scmap_writer.template_water_level(template_scmap)
    vertices, _vertex_water = scmap_writer.terrain_tensor_to_vertices(
        tensor=tensor,
        channels=channels,
        heightmap_width=header.map_width + 1,
        heightmap_height=header.map_height + 1,
        water_level=water_level,
        land_clearance=0.35,
        land_height_range=30.0,
        water_clearance=0.25,
        water_depth_range=10.0,
    )
    cell_heights = scmap_terrain._height_vertices_to_cells(vertices)
    resized_heights = _resize_float(cell_heights, grid_size, grid_size, Image.Resampling.BILINEAR)
    water = resized_heights <= water_level
    return resized_heights, water, water_source, water_level


def _valid_masks(
    tensor: np.ndarray,
    channels: list[str],
    water_threshold: float,
    buildable_quantile: float,
    passable_quantile: float,
    template_scmap: Path | None,
    dry_margin_cells: int,
) -> dict[str, np.ndarray]:
    terrain_source = "generated_tensor"
    water_level = None
    water_source = ""
    if template_scmap is not None:
        height, water_bool, water_source, water_level = _final_written_layers(
            tensor,
            channels,
            template_scmap,
            int(tensor.shape[-1]),
        )
        dry = ~water_bool
        terrain_source = "final_scmap_heightmap_model"
    else:
        height = _channel(tensor, channels, "height_norm", 0)
        water = _channel(tensor, channels, "water_mask", 1)
        dry = water < water_threshold
    gy, gx = np.gradient(height)
    slope = np.hypot(gx, gy).astype(np.float32)
    dry_slopes = slope[dry]
    if dry_slopes.size:
        buildable_cutoff = max(float(np.quantile(dry_slopes, buildable_quantile)), 0.012)
        passable_cutoff = max(float(np.quantile(dry_slopes, passable_quantile)), buildable_cutoff)
    else:
        buildable_cutoff = 0.012
        passable_cutoff = 0.02
    buildable_dry = _erode_bool(dry, dry_margin_cells)
    passable_dry = _erode_bool(dry, max(1, dry_margin_cells // 2))
    buildable = buildable_dry & (slope <= buildable_cutoff)
    passable = passable_dry & (slope <= passable_cutoff)
    return {
        "dry": dry,
        "buildable": buildable,
        "passable": passable,
        "slope": slope,
        "terrain_source": terrain_source,
        "water_level": water_level,
        "water_level_source": water_source,
        "buildable_cutoff": buildable_cutoff,
        "passable_cutoff": passable_cutoff,
        "dry_margin_cells": dry_margin_cells,
    }


def _point_from_xy(x: int, y: int, grid_size: int, original: dict[str, Any]) -> dict[str, Any]:
    point = dict(original)
    point["x"] = int(x)
    point["y"] = int(y)
    point["norm_x"] = round(float(x / max(grid_size - 1, 1)), 6)
    point["norm_z"] = round(float(y / max(grid_size - 1, 1)), 6)
    return point


def _distance_sq_xy(point: dict[str, Any], other: dict[str, Any]) -> float:
    return (float(point["x"]) - float(other["x"])) ** 2 + (
        float(point["y"]) - float(other["y"])
    ) ** 2


def _min_distance_ok(
    candidate: dict[str, Any],
    placed: list[dict[str, Any]],
    min_distance: float,
) -> bool:
    return all(_distance_sq_xy(candidate, other) >= min_distance * min_distance for other in placed)


def _nearest_valid_point(
    point: dict[str, Any],
    valid_mask: np.ndarray,
    placed: list[dict[str, Any]],
    min_distance: float,
    max_search_radius: int,
) -> tuple[dict[str, Any] | None, float]:
    height, width = valid_mask.shape
    grid_size = max(width, height)
    original_x = float(point["x"])
    original_y = float(point["y"])
    cx = int(np.clip(round(original_x), 0, width - 1))
    cy = int(np.clip(round(original_y), 0, height - 1))
    best: dict[str, Any] | None = None
    best_dist = float("inf")
    for radius in range(0, max_search_radius + 1):
        x0 = max(0, cx - radius)
        x1 = min(width - 1, cx + radius)
        y0 = max(0, cy - radius)
        y1 = min(height - 1, cy + radius)
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                if radius and abs(x - cx) < radius and abs(y - cy) < radius:
                    continue
                if not valid_mask[y, x]:
                    continue
                candidate = _point_from_xy(x, y, grid_size, point)
                if not _min_distance_ok(candidate, placed, min_distance):
                    continue
                dist = (x - original_x) ** 2 + (y - original_y) ** 2
                if dist < best_dist:
                    best = candidate
                    best_dist = dist
        if best is not None:
            return best, math.sqrt(best_dist)
    return None, 0.0


def _validate_layer(
    points: list[dict[str, Any]],
    valid_mask: np.ndarray,
    min_distance: float,
    max_search_radius: int,
    blockers: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    placed: list[dict[str, Any]] = []
    fixed_blockers = blockers or []
    moved = 0
    dropped = 0
    invalid_before = 0
    max_move = 0.0
    for point in points:
        try:
            x = int(round(float(point["x"])))
            y = int(round(float(point["y"])))
        except (KeyError, TypeError, ValueError):
            dropped += 1
            continue
        in_bounds = 0 <= y < valid_mask.shape[0] and 0 <= x < valid_mask.shape[1]
        if not in_bounds or not valid_mask[y, x]:
            invalid_before += 1
        repaired, distance = _nearest_valid_point(
            point,
            valid_mask,
            [*fixed_blockers, *placed],
            min_distance,
            max_search_radius,
        )
        if repaired is None:
            dropped += 1
            continue
        if distance > 0.0:
            moved += 1
            max_move = max(max_move, distance)
        placed.append(repaired)
    return placed, {
        "input_count": len(points),
        "output_count": len(placed),
        "invalid_before": invalid_before,
        "moved": moved,
        "dropped": dropped,
        "min_distance": min_distance,
        "max_move_cells": round(max_move, 4),
    }


def _validate_reclaim(
    points: list[dict[str, Any]],
    valid_mask: np.ndarray,
    blockers: list[dict[str, Any]],
    min_distance: float,
    max_search_radius: int,
    max_points: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    placed: list[dict[str, Any]] = []
    moved = 0
    dropped = 0
    invalid_before = 0
    max_move = 0.0
    for point in points[:max_points]:
        try:
            x = int(round(float(point["x"])))
            y = int(round(float(point["y"])))
        except (KeyError, TypeError, ValueError):
            dropped += 1
            continue
        in_bounds = 0 <= y < valid_mask.shape[0] and 0 <= x < valid_mask.shape[1]
        if not in_bounds or not valid_mask[y, x]:
            invalid_before += 1
        repaired, distance = _nearest_valid_point(
            point,
            valid_mask,
            [*blockers, *placed],
            min_distance,
            max_search_radius,
        )
        if repaired is None:
            dropped += 1
            continue
        if distance > 0.0:
            moved += 1
            max_move = max(max_move, distance)
        placed.append(repaired)
    return placed, {
        "input_count": len(points),
        "considered_count": min(len(points), max_points),
        "output_count": len(placed),
        "invalid_before": invalid_before,
        "moved": moved,
        "dropped": dropped,
        "min_distance": min_distance,
        "max_move_cells": round(max_move, 4),
    }


def _draw_preview(
    tensor: np.ndarray,
    channels: list[str],
    points: dict[str, list[dict[str, Any]]],
    reclaim_points: list[dict[str, Any]],
    out_path: Path,
) -> None:
    height = _channel(tensor, channels, "height_norm", 0)
    water = _channel(tensor, channels, "water_mask", 1) >= 0.5
    normalized = np.clip(height, 0, 1)
    image = np.stack([(normalized * 190 + 35).astype(np.uint8)] * 3, axis=-1)
    image[water] = (40, 105, 180)
    image = Image.fromarray(image).resize((512, 512), Image.Resampling.NEAREST)
    draw = ImageDraw.Draw(image)
    colors = {
        "spawns": (255, 70, 70),
        "mexes": (255, 220, 70),
        "hydros": (70, 220, 255),
        "reclaim": (70, 220, 120),
    }
    for point in reclaim_points:
        x = int(float(point["norm_x"]) * 512)
        y = int(float(point["norm_z"]) * 512)
        draw.ellipse((x - 2, y - 2, x + 2, y + 2), fill=colors["reclaim"])
    for layer, radius in (("mexes", 3), ("hydros", 4), ("spawns", 5)):
        for point in points.get(layer, []):
            x = int(float(point["norm_x"]) * 512)
            y = int(float(point["norm_z"]) * 512)
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=colors[layer])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(out_path)


def validate_structure(
    generated_tensor: Path,
    point_metadata: dict[str, Any],
    reclaim_metadata: dict[str, Any],
    players: int,
    max_reclaim_points: int,
    water_threshold: float = 0.5,
    max_search_radius: int = 64,
    buildable_quantile: float = 0.62,
    passable_quantile: float = 0.82,
    template_scmap: Path | None = None,
    dry_margin_cells: int = 3,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], tuple[np.ndarray, list[str]]]:
    tensor, channels = _load_tensor(generated_tensor)
    masks = _valid_masks(
        tensor,
        channels,
        water_threshold,
        buildable_quantile,
        passable_quantile,
        template_scmap,
        dry_margin_cells,
    )

    repaired_points = deepcopy(point_metadata)
    input_layers = point_metadata.get("points", {})
    layer_reports: dict[str, Any] = {}
    spawns, layer_reports["spawns"] = _validate_layer(
        list(input_layers.get("spawns", []))[:players],
        masks["buildable"],
        min_distance=28.0,
        max_search_radius=max_search_radius,
    )
    mexes, layer_reports["mexes"] = _validate_layer(
        list(input_layers.get("mexes", [])),
        masks["buildable"],
        min_distance=7.0,
        max_search_radius=max_search_radius,
        blockers=spawns,
    )
    hydros, layer_reports["hydros"] = _validate_layer(
        list(input_layers.get("hydros", [])),
        masks["buildable"],
        min_distance=12.0,
        max_search_radius=max_search_radius,
        blockers=[*spawns, *mexes],
    )
    repaired_points["points"] = {
        "spawns": spawns,
        "mexes": mexes,
        "hydros": hydros,
    }

    resource_blockers = [*spawns, *mexes, *hydros]
    repaired_reclaim = deepcopy(reclaim_metadata)
    reclaim_points, reclaim_report = _validate_reclaim(
        list(reclaim_metadata.get("points", [])),
        masks["passable"],
        resource_blockers,
        min_distance=3.0,
        max_search_radius=max_search_radius,
        max_points=max_reclaim_points,
    )
    repaired_reclaim["points"] = reclaim_points
    repaired_reclaim["reclaim_point_count"] = len(reclaim_points)

    report = {
        "schema": "mapgen_basic_validator_v1",
        "source_tensor": str(generated_tensor),
        "template_scmap": str(template_scmap) if template_scmap is not None else "",
        "terrain_source": masks["terrain_source"],
        "water_level": masks["water_level"],
        "water_level_source": masks["water_level_source"],
        "water_threshold": water_threshold,
        "max_search_radius": max_search_radius,
        "dry_margin_cells": masks["dry_margin_cells"],
        "buildable_slope_cutoff": round(float(masks["buildable_cutoff"]), 8),
        "passable_slope_cutoff": round(float(masks["passable_cutoff"]), 8),
        "buildable_percent": round(float(masks["buildable"].mean() * 100.0), 6),
        "passable_percent": round(float(masks["passable"].mean() * 100.0), 6),
        "layers": layer_reports,
        "reclaim": reclaim_report,
        "warnings": [],
    }
    if len(spawns) < players:
        report["warnings"].append(f"spawn_count_below_players:{len(spawns)}<{players}")
    if not mexes:
        report["warnings"].append("no_mexes_after_validation")
    if not hydros:
        report["warnings"].append("no_hydros_after_validation")
    return repaired_points, repaired_reclaim, report, (tensor, channels)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate generated map points against terrain.")
    parser.add_argument("--generated-tensor", required=True, type=Path)
    parser.add_argument("--point-metadata", required=True, type=Path)
    parser.add_argument("--reclaim-metadata", required=True, type=Path)
    parser.add_argument("--points-out", required=True, type=Path)
    parser.add_argument("--reclaim-out", required=True, type=Path)
    parser.add_argument("--report-out", required=True, type=Path)
    parser.add_argument("--preview-out", type=Path)
    parser.add_argument("--template-scmap", type=Path)
    parser.add_argument("--players", default=4, type=int)
    parser.add_argument("--max-reclaim-points", default=70, type=int)
    parser.add_argument("--dry-margin-cells", default=3, type=int)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    point_metadata = json.loads(args.point_metadata.read_text(encoding="utf-8"))
    reclaim_metadata = json.loads(args.reclaim_metadata.read_text(encoding="utf-8"))
    points, reclaim, report, tensor_info = validate_structure(
        generated_tensor=args.generated_tensor,
        point_metadata=point_metadata,
        reclaim_metadata=reclaim_metadata,
        players=args.players,
        max_reclaim_points=args.max_reclaim_points,
        template_scmap=args.template_scmap,
        dry_margin_cells=args.dry_margin_cells,
    )
    args.points_out.parent.mkdir(parents=True, exist_ok=True)
    args.reclaim_out.parent.mkdir(parents=True, exist_ok=True)
    args.report_out.parent.mkdir(parents=True, exist_ok=True)
    args.points_out.write_text(json.dumps(points, indent=2), encoding="utf-8")
    args.reclaim_out.write_text(json.dumps(reclaim, indent=2), encoding="utf-8")
    args.report_out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    if args.preview_out:
        tensor, channels = tensor_info
        _draw_preview(tensor, channels, points["points"], reclaim["points"], args.preview_out)
    print(f"Wrote validated points to {args.points_out}")
    print(f"Wrote validated reclaim to {args.reclaim_out}")
    print(f"Wrote validator report to {args.report_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
