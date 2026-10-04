"""Extract higher-level terrain, path, water, and reclaim structure metrics."""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

import numpy as np

from supmapai.extract import scmap_terrain

STRUCTURE_COLUMNS = [
    "map_dir",
    "shoreline_length_cells",
    "shoreline_length_per_10k_area",
    "water_body_count",
    "water_body_sizes_json",
    "water_body_type_guess",
    "plateau_count",
    "plateau_sizes_json",
    "largest_plateau_percent",
    "engineer_hover_region_count",
    "largest_engineer_hover_region_percent",
    "transport_only_region_count",
    "transport_only_area_percent",
    "transport_only_regions_json",
    "water_separated_region_count",
    "water_separated_area_percent",
    "base_to_base_path_exists",
    "base_to_base_path_length",
    "base_to_base_direct_distance",
    "base_to_base_straightness",
    "base_to_base_min_width",
    "base_to_base_median_width",
    "base_to_base_choke_count",
    "base_to_base_pair_count",
    "early_reclaim_per_spawn_mean",
    "early_reclaim_per_spawn_min",
    "early_reclaim_per_spawn_max",
    "center_reclaim_percent",
    "contested_reclaim_percent",
    "reclaim_cluster_count",
    "reclaim_cluster_sizes_json",
    "reclaim_spread_label",
    "reclaim_fairness_score",
    "warnings",
]

RECLAIM_KINDS = {"reclaim", "tree", "rock", "boulder"}
NEIGHBORS_4 = ((-1, 0), (1, 0), (0, -1), (0, 1))
NEIGHBORS_8 = (
    (-1, 0),
    (1, 0),
    (0, -1),
    (0, 1),
    (-1, -1),
    (-1, 1),
    (1, -1),
    (1, 1),
)


def _read_csv_by_map(path: Path | None) -> dict[str, dict[str, str]]:
    if path is None or not path.exists():
        return {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return {row["map_dir"]: row for row in csv.DictReader(handle) if row.get("map_dir")}


def _read_markers(path: Path) -> dict[str, dict[str, list[dict[str, str]]]]:
    markers: dict[str, dict[str, list[dict[str, str]]]] = defaultdict(lambda: defaultdict(list))
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("in_playable_area") != "true":
                continue
            markers[row["map_dir"]][row["kind"]].append(row)
    return markers


def _read_reclaim_entities(path: Path) -> dict[str, list[tuple[float, float]]]:
    reclaim: dict[str, list[tuple[float, float]]] = defaultdict(list)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("in_playable_area") != "true" or row.get("kind") not in RECLAIM_KINDS:
                continue
            try:
                reclaim[row["map_dir"]].append((float(row["norm_x"]), float(row["norm_z"])))
            except ValueError:
                continue
    return reclaim


def _inventory_maps(inventory: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["top_level_dir"]: item for item in inventory.get("maps", [])}


def _first_file_path(inventory: dict[str, Any], item: dict[str, Any], key: str) -> Path | None:
    files = item.get("files", {}).get(key, [])
    if not files:
        return None
    return Path(inventory["maps_root"]) / files[0]["path"]


def _decode_masks(
    inventory: dict[str, Any],
    item: dict[str, Any],
    terrain_row: dict[str, str],
    buildable_slope_threshold: float,
    pathblocking_slope_threshold: float,
    analysis_max_size: int,
) -> dict[str, Any]:
    scmap_path = _first_file_path(inventory, item, "scmap")
    save_lua_path = _first_file_path(inventory, item, "save_lua")
    if scmap_path is None:
        raise FileNotFoundError("missing scmap in inventory")

    data = scmap_path.read_bytes()
    terrain_header = scmap_terrain._terrain_header(data)
    width = terrain_header.map_width
    height = terrain_header.map_height
    heightmap_width = width + 1
    heightmap_height = height + 1
    count = heightmap_width * heightmap_height
    raw = np.frombuffer(
        data,
        dtype="<u2",
        count=count,
        offset=terrain_header.height_offset,
    ).reshape((heightmap_height, heightmap_width))
    vertex_heights = raw.astype(np.float32) / 128.0
    cells = scmap_terrain._height_vertices_to_cells(vertex_heights)
    playable_z_slice, playable_x_slice, playable_area = scmap_terrain._playable_slice(
        cells.shape,
        scmap_terrain._area_1_rectangle(save_lua_path),
    )
    heights = cells[playable_z_slice, playable_x_slice]
    if min(heights.shape) < 2:
        heights = cells
        playable_area = {
            "playable_width": width,
            "playable_height": height,
            "playable_x0": 0,
            "playable_z0": 0,
        }

    cell_x = width / max(heightmap_width - 1, 1)
    cell_z = height / max(heightmap_height - 1, 1)
    gradient_z, gradient_x = np.gradient(heights, cell_z, cell_x)
    slope = np.sqrt(gradient_x * gradient_x + gradient_z * gradient_z)
    water_level = _float_or_none(terrain_row.get("water_level"))
    water_mask = heights <= water_level if water_level is not None else np.zeros_like(heights, bool)
    steep_mask = slope > pathblocking_slope_threshold
    buildable_mask = (slope <= buildable_slope_threshold) & ~water_mask
    normal_land_mask = ~water_mask & ~steep_mask
    engineer_hover_mask = ~steep_mask
    analysis = _analysis_masks(
        water_mask=water_mask,
        buildable_mask=buildable_mask,
        normal_land_mask=normal_land_mask,
        engineer_hover_mask=engineer_hover_mask,
        max_size=analysis_max_size,
    )

    return {
        "water_mask": analysis["water_mask"],
        "buildable_mask": analysis["buildable_mask"],
        "normal_land_mask": analysis["normal_land_mask"],
        "engineer_hover_mask": analysis["engineer_hover_mask"],
        "analysis_cell_scale": analysis["cell_scale"],
        "playable_width": float(playable_area["playable_width"]),
        "playable_height": float(playable_area["playable_height"]),
    }


def _analysis_masks(
    water_mask: np.ndarray,
    buildable_mask: np.ndarray,
    normal_land_mask: np.ndarray,
    engineer_hover_mask: np.ndarray,
    max_size: int,
) -> dict[str, Any]:
    step = max(1, math.ceil(max(water_mask.shape) / max_size))
    return {
        "water_mask": _pool_bool(water_mask, step, threshold=0.25),
        "buildable_mask": _pool_bool(buildable_mask, step, threshold=0.5),
        "normal_land_mask": _pool_bool(normal_land_mask, step, threshold=0.5),
        "engineer_hover_mask": _pool_bool(engineer_hover_mask, step, threshold=0.5),
        "cell_scale": float(step),
    }


def _pool_bool(mask: np.ndarray, step: int, threshold: float) -> np.ndarray:
    if step <= 1:
        return mask
    height, width = mask.shape
    pad_h = (-height) % step
    pad_w = (-width) % step
    padded = np.pad(mask, ((0, pad_h), (0, pad_w)), constant_values=False)
    pooled = padded.reshape(
        padded.shape[0] // step,
        step,
        padded.shape[1] // step,
        step,
    )
    return pooled.mean(axis=(1, 3)) >= threshold


def _float_or_none(value: Any) -> float | None:
    try:
        if value in ("", None):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _component_labels(
    mask: np.ndarray,
    neighbors: tuple[tuple[int, int], ...] = NEIGHBORS_4,
) -> tuple[np.ndarray, list[dict[str, Any]]]:
    labels = np.full(mask.shape, -1, dtype=np.int32)
    components: list[dict[str, Any]] = []
    height, width = mask.shape
    label = 0
    for seed_y in range(height):
        for seed_x in range(width):
            if not mask[seed_y, seed_x] or labels[seed_y, seed_x] != -1:
                continue
            stack = [(seed_y, seed_x)]
            labels[seed_y, seed_x] = label
            xs = []
            ys = []
            touches_edge = False
            while stack:
                y, x = stack.pop()
                ys.append(y)
                xs.append(x)
                touches_edge = touches_edge or y in (0, height - 1) or x in (0, width - 1)
                for dy, dx in neighbors:
                    ny = y + dy
                    nx = x + dx
                    if (
                        0 <= ny < height
                        and 0 <= nx < width
                        and mask[ny, nx]
                        and labels[ny, nx] == -1
                    ):
                        labels[ny, nx] = label
                        stack.append((ny, nx))
            area = len(xs)
            components.append(
                {
                    "label": label,
                    "area_cells": area,
                    "area_percent": round(float(area / mask.size * 100), 6),
                    "bbox": [int(min(xs)), int(min(ys)), int(max(xs) + 1), int(max(ys) + 1)],
                    "touches_edge": touches_edge,
                }
            )
            label += 1
    components.sort(key=lambda item: item["area_cells"], reverse=True)
    return labels, components


def _shoreline_length(water_mask: np.ndarray) -> int:
    if not water_mask.any():
        return 0
    vertical = np.count_nonzero(water_mask[1:, :] != water_mask[:-1, :])
    horizontal = np.count_nonzero(water_mask[:, 1:] != water_mask[:, :-1])
    return int(vertical + horizontal)


def _water_type(
    water_components: list[dict[str, Any]],
    water_percent: float,
    shoreline: int,
) -> str:
    if water_percent <= 0:
        return "none"
    largest = water_components[0] if water_components else {}
    count = len(water_components)
    edge = bool(largest.get("touches_edge"))
    if water_percent >= 45 and edge:
        return "coast_or_ocean"
    if count >= 4 and water_percent < 25:
        return "ponds"
    if count <= 2 and not edge:
        return "lake"
    if shoreline / max(water_percent, 1.0) > 60:
        return "channels"
    return "mixed"


def _downsample_mask(mask: np.ndarray, max_size: int = 256) -> tuple[np.ndarray, float, float]:
    height, width = mask.shape
    step = max(1, math.ceil(max(height, width) / max_size))
    return mask[::step, ::step], float(step), float(step)


def _norm_to_cell(point: tuple[float, float], shape: tuple[int, int]) -> tuple[int, int]:
    height, width = shape
    x = max(0, min(width - 1, int(round(point[0] * (width - 1)))))
    y = max(0, min(height - 1, int(round(point[1] * (height - 1)))))
    return y, x


def _nearest_passable(
    start: tuple[int, int],
    passable: np.ndarray,
    radius: int = 8,
) -> tuple[int, int] | None:
    y, x = start
    if passable[y, x]:
        return start
    height, width = passable.shape
    for distance in range(1, radius + 1):
        for dy in range(-distance, distance + 1):
            for dx in (-distance, distance):
                ny = y + dy
                nx = x + dx
                if 0 <= ny < height and 0 <= nx < width and passable[ny, nx]:
                    return ny, nx
        for dx in range(-distance + 1, distance):
            for dy in (-distance, distance):
                ny = y + dy
                nx = x + dx
                if 0 <= ny < height and 0 <= nx < width and passable[ny, nx]:
                    return ny, nx
    return None


def _shortest_path(
    passable: np.ndarray,
    start: tuple[int, int],
    goal: tuple[int, int],
) -> list[tuple[int, int]]:
    start = _nearest_passable(start, passable) or start
    goal = _nearest_passable(goal, passable) or goal
    if not passable[start] or not passable[goal]:
        return []
    queue = deque([start])
    parent: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
    height, width = passable.shape
    while queue:
        current = queue.popleft()
        if current == goal:
            break
        for dy, dx in NEIGHBORS_8:
            ny = current[0] + dy
            nx = current[1] + dx
            nxt = (ny, nx)
            if 0 <= ny < height and 0 <= nx < width and passable[ny, nx] and nxt not in parent:
                parent[nxt] = current
                queue.append(nxt)
    if goal not in parent:
        return []
    path = []
    current: tuple[int, int] | None = goal
    while current is not None:
        path.append(current)
        current = parent[current]
    path.reverse()
    return path


def _distance_to_blocked(passable: np.ndarray) -> np.ndarray:
    distance = np.full(passable.shape, -1, dtype=np.int32)
    queue: deque[tuple[int, int]] = deque()
    height, width = passable.shape
    for y in range(height):
        for x in range(width):
            if not passable[y, x] or y in (0, height - 1) or x in (0, width - 1):
                distance[y, x] = 0
                queue.append((y, x))
    while queue:
        y, x = queue.popleft()
        for dy, dx in NEIGHBORS_4:
            ny = y + dy
            nx = x + dx
            if 0 <= ny < height and 0 <= nx < width and distance[ny, nx] == -1:
                distance[ny, nx] = distance[y, x] + 1
                queue.append((ny, nx))
    return distance


def _path_metrics(
    mask: np.ndarray,
    spawns: list[tuple[float, float]],
    teams: list[list[int]],
) -> dict[str, Any]:
    if len(spawns) < 2:
        return {"exists": "", "pair_count": 0}
    small_mask, scale_y, scale_x = _downsample_mask(mask)
    width_map = _distance_to_blocked(small_mask)
    pairs = _spawn_pairs(spawns, teams)
    results = []
    for left, right in pairs[:80]:
        start = _norm_to_cell(spawns[left], small_mask.shape)
        goal = _norm_to_cell(spawns[right], small_mask.shape)
        path = _shortest_path(small_mask, start, goal)
        if not path:
            continue
        path_len = _path_length(path) * ((scale_x + scale_y) * 0.5)
        direct = math.hypot(
            (spawns[left][0] - spawns[right][0]) * max(small_mask.shape[1] - 1, 1) * scale_x,
            (spawns[left][1] - spawns[right][1]) * max(small_mask.shape[0] - 1, 1) * scale_y,
        )
        widths = np.array([width_map[y, x] for y, x in path if width_map[y, x] >= 0])
        width_cells = widths * ((scale_x + scale_y) * 0.5) * 2.0
        straightness = min(1.0, direct / path_len) if path_len else 0.0
        results.append(
            {
                "path_len": path_len,
                "direct": direct,
                "straightness": straightness,
                "min_width": float(width_cells.min()) if width_cells.size else 0.0,
                "median_width": float(np.median(width_cells)) if width_cells.size else 0.0,
                "chokes": _choke_count(width_cells),
            }
        )
    if not results:
        return {"exists": "false", "pair_count": len(pairs)}
    best = min(results, key=lambda item: item["path_len"])
    return {
        "exists": "true",
        "pair_count": len(pairs),
        "path_length": round(best["path_len"], 3),
        "direct_distance": round(best["direct"], 3),
        "straightness": round(best["straightness"], 6),
        "min_width": round(best["min_width"], 3),
        "median_width": round(best["median_width"], 3),
        "choke_count": best["chokes"],
    }


def _path_length(path: list[tuple[int, int]]) -> float:
    total = 0.0
    for left, right in zip(path, path[1:], strict=False):
        total += math.dist(left, right)
    return total


def _choke_count(widths: np.ndarray) -> int:
    if widths.size < 3:
        return 0
    threshold = max(4.0, float(np.percentile(widths, 20)))
    narrow = widths <= threshold
    count = 0
    in_run = False
    for value in narrow:
        if value and not in_run:
            count += 1
            in_run = True
        elif not value:
            in_run = False
    return count


def _spawn_pairs(
    spawns: list[tuple[float, float]],
    teams: list[list[int]],
) -> list[tuple[int, int]]:
    if len(teams) >= 2:
        pairs = []
        for left_team_index, left_team in enumerate(teams):
            for right_team in teams[left_team_index + 1 :]:
                for left in left_team:
                    for right in right_team:
                        if left < len(spawns) and right < len(spawns):
                            pairs.append((left, right))
        return pairs
    return [(left, right) for left in range(len(spawns)) for right in range(left + 1, len(spawns))]


def _team_layout(row: dict[str, str] | None) -> list[list[int]]:
    if not row:
        return []
    try:
        teams = json.loads(row.get("team_spawn_indices_json", "[]"))
    except json.JSONDecodeError:
        return []
    return teams if isinstance(teams, list) else []


def _point_from_marker(row: dict[str, str]) -> tuple[float, float] | None:
    try:
        return float(row["norm_x"]), float(row["norm_z"])
    except (KeyError, ValueError):
        return None


def _reclaim_metrics(
    points: list[tuple[float, float]],
    spawns: list[tuple[float, float]],
    teams: list[list[int]],
) -> dict[str, Any]:
    if not points:
        return {
            "early_mean": 0,
            "early_min": 0,
            "early_max": 0,
            "center_percent": 0,
            "contested_percent": 0,
            "cluster_count": 0,
            "clusters": [],
            "spread_label": "none",
            "fairness": 1,
        }
    early_radius = 0.12
    early_counts = []
    for spawn in spawns:
        early_counts.append(sum(1 for point in points if math.dist(point, spawn) <= early_radius))
    center_count = sum(1 for point in points if math.dist(point, (0.5, 0.5)) <= 0.22)
    contested_count = _contested_reclaim_count(points, spawns, teams)
    clusters = _point_clusters(points, radius=0.035)
    label = _reclaim_spread_label(points, clusters, center_count / len(points), early_counts)
    return {
        "early_mean": round(sum(early_counts) / len(early_counts), 3) if early_counts else 0,
        "early_min": min(early_counts) if early_counts else 0,
        "early_max": max(early_counts) if early_counts else 0,
        "center_percent": round(center_count / len(points) * 100, 4),
        "contested_percent": round(contested_count / len(points) * 100, 4),
        "cluster_count": len(clusters),
        "clusters": clusters[:30],
        "spread_label": label,
        "fairness": round(_fairness(early_counts), 6),
    }


def _contested_reclaim_count(
    points: list[tuple[float, float]],
    spawns: list[tuple[float, float]],
    teams: list[list[int]],
) -> int:
    if len(spawns) < 2:
        return 0
    if not teams or any(len(team) == 1 for team in teams):
        center = (0.5, 0.5)
        return sum(1 for point in points if math.dist(point, center) <= 0.24)
    team_centers = []
    for team in teams:
        team_points = [spawns[index] for index in team if index < len(spawns)]
        if team_points:
            team_centers.append(
                (
                    sum(point[0] for point in team_points) / len(team_points),
                    sum(point[1] for point in team_points) / len(team_points),
                )
            )
    if len(team_centers) < 2:
        return 0
    contested = 0
    for point in points:
        distances = sorted(math.dist(point, center) for center in team_centers)
        if len(distances) >= 2 and distances[1] - distances[0] <= 0.08:
            contested += 1
    return contested


def _point_clusters(points: list[tuple[float, float]], radius: float) -> list[dict[str, Any]]:
    if not points:
        return []
    cell_size = radius
    buckets: dict[tuple[int, int], list[int]] = defaultdict(list)
    for index, point in enumerate(points):
        buckets[(int(point[0] / cell_size), int(point[1] / cell_size))].append(index)
    seen = set()
    clusters = []
    for index in range(len(points)):
        if index in seen:
            continue
        stack = [index]
        seen.add(index)
        members = []
        while stack:
            current = stack.pop()
            members.append(current)
            point = points[current]
            bucket = (int(point[0] / cell_size), int(point[1] / cell_size))
            for bx in range(bucket[0] - 1, bucket[0] + 2):
                for by in range(bucket[1] - 1, bucket[1] + 2):
                    for other in buckets.get((bx, by), []):
                        if other not in seen and math.dist(point, points[other]) <= radius:
                            seen.add(other)
                            stack.append(other)
        xs = [points[item][0] for item in members]
        zs = [points[item][1] for item in members]
        clusters.append(
            {
                "size": len(members),
                "center_norm_x": round(sum(xs) / len(xs), 6),
                "center_norm_z": round(sum(zs) / len(zs), 6),
            }
        )
    clusters.sort(key=lambda item: item["size"], reverse=True)
    return clusters


def _reclaim_spread_label(
    points: list[tuple[float, float]],
    clusters: list[dict[str, Any]],
    center_fraction: float,
    early_counts: list[int],
) -> str:
    if center_fraction >= 0.35:
        return "center_heavy"
    if early_counts and sum(early_counts) / len(points) >= 0.45:
        return "base_heavy"
    largest_fraction = clusters[0]["size"] / len(points) if clusters else 0.0
    if largest_fraction >= 0.25 or len(clusters) <= max(3, len(points) // 200):
        return "batched"
    if largest_fraction <= 0.08 and len(clusters) >= 12:
        return "even_spread"
    return "mixed"


def _fairness(values: list[int]) -> float:
    if not values:
        return 1.0
    mean = sum(values) / len(values)
    if mean <= 0:
        return 1.0
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return max(0.0, 1.0 - math.sqrt(variance) / mean)


def _build_row(
    map_dir: str,
    masks: dict[str, Any],
    terrain_row: dict[str, str],
    marker_rows: dict[str, list[dict[str, str]]],
    reclaim_points: list[tuple[float, float]],
    team_row: dict[str, str] | None,
) -> dict[str, Any]:
    water_mask = masks["water_mask"]
    water_labels, water_components = _component_labels(water_mask)
    _ = water_labels
    buildable_labels, plateaus = _component_labels(masks["buildable_mask"])
    hover_labels, hover_components = _component_labels(masks["engineer_hover_mask"])
    normal_labels, normal_components = _component_labels(masks["normal_land_mask"])
    _ = normal_labels
    cell_scale = float(masks["analysis_cell_scale"])
    shoreline = int(round(_shoreline_length(water_mask) * cell_scale))
    estimated_area_cells = water_mask.size * cell_scale * cell_scale
    area_10k = estimated_area_cells / 10000
    water_percent = float(water_mask.mean() * 100)
    largest_hover_label = hover_components[0]["label"] if hover_components else -1
    transport_regions = [
        component for component in hover_components[1:] if component["area_percent"] >= 0.05
    ]
    water_separated = _water_separated_components(
        normal_components,
        hover_labels,
        largest_hover_label,
    )

    spawn_points = [
        point
        for point in (_point_from_marker(row) for row in marker_rows.get("spawn", []))
        if point is not None
    ]
    teams = _team_layout(team_row)
    path = _path_metrics(masks["normal_land_mask"], spawn_points, teams)
    reclaim = _reclaim_metrics(reclaim_points, spawn_points, teams)

    row = {column: "" for column in STRUCTURE_COLUMNS}
    row.update(
        {
            "map_dir": map_dir,
            "shoreline_length_cells": shoreline,
            "shoreline_length_per_10k_area": round(shoreline / area_10k, 6) if area_10k else "",
            "water_body_count": len(water_components),
            "water_body_sizes_json": json.dumps(
                [
                    {
                        key: component[key]
                        for key in ("area_cells", "area_percent", "bbox", "touches_edge")
                    }
                    for component in water_components[:20]
                ],
                sort_keys=True,
            ),
            "water_body_type_guess": _water_type(water_components, water_percent, shoreline),
            "plateau_count": len(plateaus),
            "plateau_sizes_json": json.dumps(plateaus[:30], sort_keys=True),
            "largest_plateau_percent": plateaus[0]["area_percent"] if plateaus else 0.0,
            "engineer_hover_region_count": len(hover_components),
            "largest_engineer_hover_region_percent": (
                hover_components[0]["area_percent"] if hover_components else 0.0
            ),
            "transport_only_region_count": len(transport_regions),
            "transport_only_area_percent": round(
                sum(component["area_percent"] for component in transport_regions),
                6,
            ),
            "transport_only_regions_json": json.dumps(transport_regions[:20], sort_keys=True),
            "water_separated_region_count": len(water_separated),
            "water_separated_area_percent": round(
                sum(component["area_percent"] for component in water_separated),
                6,
            ),
            "base_to_base_path_exists": path.get("exists", ""),
            "base_to_base_path_length": path.get("path_length", ""),
            "base_to_base_direct_distance": path.get("direct_distance", ""),
            "base_to_base_straightness": path.get("straightness", ""),
            "base_to_base_min_width": path.get("min_width", ""),
            "base_to_base_median_width": path.get("median_width", ""),
            "base_to_base_choke_count": path.get("choke_count", ""),
            "base_to_base_pair_count": path.get("pair_count", 0),
            "early_reclaim_per_spawn_mean": reclaim["early_mean"],
            "early_reclaim_per_spawn_min": reclaim["early_min"],
            "early_reclaim_per_spawn_max": reclaim["early_max"],
            "center_reclaim_percent": reclaim["center_percent"],
            "contested_reclaim_percent": reclaim["contested_percent"],
            "reclaim_cluster_count": reclaim["cluster_count"],
            "reclaim_cluster_sizes_json": json.dumps(reclaim["clusters"], sort_keys=True),
            "reclaim_spread_label": reclaim["spread_label"],
            "reclaim_fairness_score": reclaim["fairness"],
            "warnings": _structure_warnings(terrain_row),
        }
    )
    _ = buildable_labels
    return row


def _water_separated_components(
    normal_components: list[dict[str, Any]],
    hover_labels: np.ndarray,
    largest_hover_label: int,
) -> list[dict[str, Any]]:
    separated = []
    for component in normal_components:
        x0, y0, x1, y1 = component["bbox"]
        labels = hover_labels[y0:y1, x0:x1]
        unique = set(int(label) for label in np.unique(labels) if label >= 0)
        if largest_hover_label in unique and component["label"] != normal_components[0]["label"]:
            separated.append(component)
    return separated


def _structure_warnings(terrain_row: dict[str, str]) -> str:
    warnings = []
    if terrain_row.get("water_level_source") == "height_histogram_fallback_uncertain":
        warnings.append("water_level_uncertain")
    if terrain_row.get("warnings"):
        warnings.append(str(terrain_row["warnings"]))
    return "|".join(warnings)


def build_structure_rows(
    inventory: dict[str, Any],
    terrain_csv: Path,
    markers_csv: Path,
    entities_csv: Path,
    team_layout_csv: Path | None,
    max_maps: int,
    analysis_max_size: int = 256,
) -> list[dict[str, Any]]:
    terrain_by_map = _read_csv_by_map(terrain_csv)
    markers_by_map = _read_markers(markers_csv)
    reclaim_by_map = _read_reclaim_entities(entities_csv)
    team_by_map = _read_csv_by_map(team_layout_csv)
    inventory_by_map = _inventory_maps(inventory)
    rows = []
    for index, map_dir in enumerate(sorted(terrain_by_map)):
        if index >= max_maps:
            break
        item = inventory_by_map.get(map_dir)
        if item is None:
            continue
        terrain_row = terrain_by_map[map_dir]
        try:
            masks = _decode_masks(
                inventory,
                item,
                terrain_row,
                buildable_slope_threshold=0.1,
                pathblocking_slope_threshold=0.7,
                analysis_max_size=analysis_max_size,
            )
            row = _build_row(
                map_dir,
                masks,
                terrain_row,
                markers_by_map.get(map_dir, {}),
                reclaim_by_map.get(map_dir, []),
                team_by_map.get(map_dir),
            )
        except Exception as exc:
            row = {column: "" for column in STRUCTURE_COLUMNS}
            row["map_dir"] = map_dir
            row["warnings"] = f"structure_metrics_failed:{type(exc).__name__}:{exc}"
        rows.append(row)
    return rows


def write_csv(rows: list[dict[str, Any]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=STRUCTURE_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract Structure Metrics V1.")
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--terrain", required=True, type=Path)
    parser.add_argument("--markers", required=True, type=Path)
    parser.add_argument("--entities", required=True, type=Path)
    parser.add_argument("--team-layout", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--max-maps", default=250, type=int)
    parser.add_argument("--analysis-max-size", default=256, type=int)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    inventory = json.loads(args.inventory.read_text(encoding="utf-8-sig"))
    rows = build_structure_rows(
        inventory=inventory,
        terrain_csv=args.terrain,
        markers_csv=args.markers,
        entities_csv=args.entities,
        team_layout_csv=args.team_layout,
        max_maps=args.max_maps,
        analysis_max_size=args.analysis_max_size,
    )
    write_csv(rows, args.out)
    print(f"Wrote {len(rows)} structure metric row(s) to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
