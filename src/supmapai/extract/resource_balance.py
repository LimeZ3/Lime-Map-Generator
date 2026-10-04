"""Extract symmetry, resource grouping, and spawn-distance metrics."""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

RESOURCE_COLUMNS = [
    "map_dir",
    "playable_width",
    "playable_height",
    "playable_area",
    "player_slots",
    "spawn_count",
    "mex_count",
    "hydro_count",
    "symmetry_detected",
    "symmetry_label",
    "symmetry_order",
    "symmetry_planes",
    "symmetry_basis",
    "symmetry_score",
    "symmetry_match_fraction",
    "symmetry_mean_error",
    "symmetry_vertical_score",
    "symmetry_horizontal_score",
    "symmetry_rotation_180_score",
    "symmetry_diagonal_score",
    "symmetry_anti_diagonal_score",
    "mex_per_spawn",
    "mex_per_10k_area",
    "mex_group_count",
    "mex_group_density_per_10k_area",
    "mex_group_mean_size",
    "mex_group_max_size",
    "mex_nearest_spawn_dist_mean",
    "mex_nearest_spawn_dist_p95",
    "mex_within_5pct_spawn",
    "mex_within_10pct_spawn",
    "mex_within_20pct_spawn",
    "mex_assigned_spawn_min",
    "mex_assigned_spawn_max",
    "mex_assigned_spawn_mean",
    "mex_assigned_spawn_cv",
    "mex_assigned_spawn_fairness_score",
    "mex_assigned_spawn_counts_json",
    "mex_groups_json",
    "hydro_per_spawn",
    "hydro_per_10k_area",
    "hydro_group_count",
    "hydro_group_density_per_10k_area",
    "hydro_group_mean_size",
    "hydro_group_max_size",
    "hydro_nearest_spawn_dist_mean",
    "hydro_nearest_spawn_dist_p95",
    "hydro_within_5pct_spawn",
    "hydro_within_10pct_spawn",
    "hydro_within_20pct_spawn",
    "hydro_assigned_spawn_min",
    "hydro_assigned_spawn_max",
    "hydro_assigned_spawn_mean",
    "hydro_assigned_spawn_cv",
    "hydro_assigned_spawn_fairness_score",
    "hydro_assigned_spawn_counts_json",
    "hydro_groups_json",
    "total_reclaim_entity_count",
    "reclaim_points_streamed",
    "reclaim_points_per_spawn",
    "reclaim_points_per_10k_area",
    "reclaim_group_count",
    "reclaim_group_density_per_10k_area",
    "reclaim_group_mean_size",
    "reclaim_group_max_size",
    "reclaim_nearest_spawn_dist_mean",
    "reclaim_nearest_spawn_dist_p95",
    "reclaim_within_5pct_spawn",
    "reclaim_within_10pct_spawn",
    "reclaim_within_20pct_spawn",
    "reclaim_assigned_spawn_min",
    "reclaim_assigned_spawn_max",
    "reclaim_assigned_spawn_mean",
    "reclaim_assigned_spawn_cv",
    "reclaim_assigned_spawn_fairness_score",
    "reclaim_assigned_spawn_counts_json",
    "reclaim_kind_counts_json",
    "reclaim_groups_json",
    "civilian_unit_count",
    "civilian_building_count",
    "civilian_buildings_per_spawn",
    "civilian_buildings_per_10k_area",
    "warnings",
]

Point = tuple[float, float]
Transform = Callable[[Point], Point]

SYMMETRY_TRANSFORMS: dict[str, Transform] = {
    "vertical": lambda point: (1.0 - point[0], point[1]),
    "horizontal": lambda point: (point[0], 1.0 - point[1]),
    "rotation_180": lambda point: (1.0 - point[0], 1.0 - point[1]),
    "diagonal": lambda point: (point[1], point[0]),
    "anti_diagonal": lambda point: (1.0 - point[1], 1.0 - point[0]),
}

RECLAIM_KINDS = {"reclaim", "tree", "rock", "boulder"}
DISTANCE_BINS = (0.05, 0.10, 0.20)


def _set_csv_field_limit() -> None:
    limit = 2**31 - 1
    while True:
        try:
            csv.field_size_limit(limit)
            return
        except OverflowError:
            limit //= 10


@dataclass
class DistanceStats:
    values: list[float] = field(default_factory=list)
    within_counts: Counter[str] = field(default_factory=Counter)

    def add(self, distance: float) -> None:
        self.values.append(distance)
        for radius in DISTANCE_BINS:
            if distance <= radius:
                self.within_counts[f"{radius:.2f}"] += 1


@dataclass
class ReclaimAccumulator:
    count: int = 0
    kind_counts: Counter[str] = field(default_factory=Counter)
    cells: dict[tuple[int, int], int] = field(default_factory=dict)
    cell_sum_x: dict[tuple[int, int], float] = field(default_factory=dict)
    cell_sum_z: dict[tuple[int, int], float] = field(default_factory=dict)
    distance_stats: DistanceStats = field(default_factory=DistanceStats)
    assigned_spawn_counts: Counter[int] = field(default_factory=Counter)


def _read_csv_by_map(path: Path, key: str = "map_dir") -> dict[str, dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = {}
        for row in csv.DictReader(handle):
            row_key = row.get(key) or row.get("map_dir") or row.get("top_level_dir")
            if row_key:
                rows[row_key] = row
        return rows


def _read_marker_points(path: Path) -> dict[str, dict[str, list[Point]]]:
    points: dict[str, dict[str, list[Point]]] = defaultdict(lambda: defaultdict(list))
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("in_playable_area") != "true":
                continue
            point = _point_from_row(row)
            if point is None:
                continue
            points[row["map_dir"]][row["kind"]].append(point)
    return points


def _point_from_row(row: dict[str, str]) -> Point | None:
    try:
        return float(row["norm_x"]), float(row["norm_z"])
    except (KeyError, ValueError):
        return None


def _float_or_zero(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _int_or_zero(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _nearest_index_distance(point: Point, points: list[Point]) -> tuple[int, float] | None:
    if not points:
        return None
    return min(
        ((index, math.dist(point, other)) for index, other in enumerate(points)),
        key=lambda item: item[1],
    )


def _nearest_distance(point: Point, points: list[Point]) -> float | None:
    nearest = _nearest_index_distance(point, points)
    return nearest[1] if nearest is not None else None


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    index = (len(values) - 1) * pct
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return values[lower]
    return values[lower] + (values[upper] - values[lower]) * (index - lower)


def _symmetry_score(
    points: list[Point],
    transform: Transform,
    tolerance: float,
) -> dict[str, float]:
    if len(points) < 2:
        return {"score": 0.0, "match_fraction": 0.0, "mean_error": 1.0}

    distances = []
    for point in points:
        mirrored = transform(point)
        nearest = _nearest_distance(mirrored, points)
        if nearest is not None:
            distances.append(nearest)

    if not distances:
        return {"score": 0.0, "match_fraction": 0.0, "mean_error": 1.0}

    matched = [distance for distance in distances if distance <= tolerance]
    match_fraction = len(matched) / len(distances)
    mean_error = sum(distances) / len(distances)
    error_penalty = min(mean_error / tolerance, 1.0)
    score = max(0.0, match_fraction * (1.0 - 0.35 * error_penalty))
    return {
        "score": score,
        "match_fraction": match_fraction,
        "mean_error": mean_error,
    }


def _best_symmetry(marker_points: dict[str, list[Point]], tolerance: float) -> dict[str, Any]:
    bases = {
        "mex": marker_points.get("mex", []),
        "spawn": marker_points.get("spawn", []),
        "hydro": marker_points.get("hydro", []),
        "mex_hydro": marker_points.get("mex", []) + marker_points.get("hydro", []),
        "all_markers": (
            marker_points.get("spawn", [])
            + marker_points.get("mex", [])
            + marker_points.get("hydro", [])
        ),
    }
    candidates = []
    for basis, points in bases.items():
        if len(points) < 2:
            continue
        scores = {
            name: _symmetry_score(points, transform, tolerance)
            for name, transform in SYMMETRY_TRANSFORMS.items()
        }
        best_name, best = max(scores.items(), key=lambda item: item[1]["score"])
        planes = [
            name
            for name, result in scores.items()
            if result["score"] >= 0.85 and result["match_fraction"] >= 0.9
        ]
        candidates.append((best["score"], basis, best_name, best, scores, planes))

    if not candidates:
        return _empty_symmetry()

    _, basis, best_name, best, scores, planes = max(candidates, key=lambda item: item[0])
    detected = best["score"] >= 0.85 and best["match_fraction"] >= 0.9
    strong_planes = [plane for plane in planes if plane != "rotation_180"]
    if detected and {"vertical", "horizontal"}.issubset(set(planes)):
        label = "four_way_mirror"
        order = 4
    elif detected and {"diagonal", "anti_diagonal"}.issubset(set(planes)):
        label = "four_way_diagonal"
        order = 4
    elif detected and best_name == "rotation_180":
        label = "rotational_180"
        order = 2
    elif detected:
        label = f"{best_name}_mirror"
        order = 2
    else:
        label = "asymmetric_or_uncertain"
        order = 1

    return {
        "symmetry_detected": str(detected).lower(),
        "symmetry_label": label,
        "symmetry_order": order,
        "symmetry_planes": "|".join(strong_planes or ([best_name] if detected else [])),
        "symmetry_basis": basis,
        "symmetry_score": round(best["score"], 6),
        "symmetry_match_fraction": round(best["match_fraction"], 6),
        "symmetry_mean_error": round(best["mean_error"], 6),
        "symmetry_vertical_score": round(scores["vertical"]["score"], 6),
        "symmetry_horizontal_score": round(scores["horizontal"]["score"], 6),
        "symmetry_rotation_180_score": round(scores["rotation_180"]["score"], 6),
        "symmetry_diagonal_score": round(scores["diagonal"]["score"], 6),
        "symmetry_anti_diagonal_score": round(scores["anti_diagonal"]["score"], 6),
    }


def _empty_symmetry() -> dict[str, Any]:
    return {
        "symmetry_detected": "false",
        "symmetry_label": "insufficient_points",
        "symmetry_order": 1,
        "symmetry_planes": "",
        "symmetry_basis": "",
        "symmetry_score": 0.0,
        "symmetry_match_fraction": 0.0,
        "symmetry_mean_error": 1.0,
        "symmetry_vertical_score": 0.0,
        "symmetry_horizontal_score": 0.0,
        "symmetry_rotation_180_score": 0.0,
        "symmetry_diagonal_score": 0.0,
        "symmetry_anti_diagonal_score": 0.0,
    }


def _cluster_points(points: list[Point], radius: float) -> list[dict[str, Any]]:
    if not points:
        return []

    parent = list(range(len(points)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for left_index, left in enumerate(points):
        for right_index in range(left_index + 1, len(points)):
            if math.dist(left, points[right_index]) <= radius:
                union(left_index, right_index)

    grouped: dict[int, list[Point]] = defaultdict(list)
    for index, point in enumerate(points):
        grouped[find(index)].append(point)

    clusters = []
    for cluster_points in grouped.values():
        size = len(cluster_points)
        center_x = sum(point[0] for point in cluster_points) / size
        center_z = sum(point[1] for point in cluster_points) / size
        clusters.append(
            {
                "size": size,
                "center_norm_x": round(center_x, 6),
                "center_norm_z": round(center_z, 6),
            }
        )
    clusters.sort(
        key=lambda item: (-int(item["size"]), item["center_norm_x"], item["center_norm_z"])
    )
    return clusters


def _resource_distance_stats(points: list[Point], spawns: list[Point]) -> DistanceStats:
    stats = DistanceStats()
    for point in points:
        distance = _nearest_distance(point, spawns)
        if distance is not None:
            stats.add(distance)
    return stats


def _assignment_counts(points: list[Point], spawns: list[Point]) -> Counter[int]:
    counts: Counter[int] = Counter()
    for point in points:
        nearest = _nearest_index_distance(point, spawns)
        if nearest is not None:
            counts[nearest[0]] += 1
    return counts


def _assignment_metrics(
    prefix: str,
    counts: Counter[int],
    spawn_count: int,
) -> dict[str, Any]:
    if spawn_count <= 0:
        return {
            f"{prefix}_assigned_spawn_min": "",
            f"{prefix}_assigned_spawn_max": "",
            f"{prefix}_assigned_spawn_mean": "",
            f"{prefix}_assigned_spawn_cv": "",
            f"{prefix}_assigned_spawn_fairness_score": "",
            f"{prefix}_assigned_spawn_counts_json": "[]",
        }

    values = [counts.get(index, 0) for index in range(spawn_count)]
    mean = sum(values) / spawn_count
    variance = sum((value - mean) ** 2 for value in values) / spawn_count
    std = math.sqrt(variance)
    cv = std / mean if mean else 0.0 if max(values, default=0) == 0 else 1.0
    fairness_score = max(0.0, min(1.0, 1.0 - cv))
    return {
        f"{prefix}_assigned_spawn_min": min(values),
        f"{prefix}_assigned_spawn_max": max(values),
        f"{prefix}_assigned_spawn_mean": round(mean, 6),
        f"{prefix}_assigned_spawn_cv": round(cv, 6),
        f"{prefix}_assigned_spawn_fairness_score": round(fairness_score, 6),
        f"{prefix}_assigned_spawn_counts_json": json.dumps(values),
    }


def _resource_metrics(
    prefix: str,
    points: list[Point],
    spawns: list[Point],
    area_10k: float,
    spawn_count: int,
    cluster_radius: float,
) -> dict[str, Any]:
    clusters = _cluster_points(points, cluster_radius)
    cluster_sizes = [int(cluster["size"]) for cluster in clusters]
    distances = _resource_distance_stats(points, spawns)
    count = len(points)
    return {
        f"{prefix}_per_spawn": round(count / spawn_count, 6) if spawn_count else "",
        f"{prefix}_per_10k_area": round(count / area_10k, 6) if area_10k else "",
        f"{prefix}_group_count": len(clusters),
        f"{prefix}_group_density_per_10k_area": round(len(clusters) / area_10k, 6)
        if area_10k
        else "",
        f"{prefix}_group_mean_size": round(sum(cluster_sizes) / len(cluster_sizes), 6)
        if cluster_sizes
        else 0,
        f"{prefix}_group_max_size": max(cluster_sizes) if cluster_sizes else 0,
        f"{prefix}_nearest_spawn_dist_mean": round(
            sum(distances.values) / len(distances.values),
            6,
        )
        if distances.values
        else "",
        f"{prefix}_nearest_spawn_dist_p95": round(_percentile(distances.values, 0.95), 6)
        if distances.values
        else "",
        f"{prefix}_within_5pct_spawn": distances.within_counts["0.05"],
        f"{prefix}_within_10pct_spawn": distances.within_counts["0.10"],
        f"{prefix}_within_20pct_spawn": distances.within_counts["0.20"],
        **_assignment_metrics(prefix, _assignment_counts(points, spawns), spawn_count),
        f"{prefix}_groups_json": json.dumps(clusters[:100], sort_keys=True),
    }


def _stream_reclaim(
    entities_csv: Path,
    marker_points: dict[str, dict[str, list[Point]]],
    grid_size: float,
) -> dict[str, ReclaimAccumulator]:
    accumulators: dict[str, ReclaimAccumulator] = defaultdict(ReclaimAccumulator)
    with entities_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            kind = row.get("kind", "")
            if kind not in RECLAIM_KINDS or row.get("in_playable_area") != "true":
                continue
            point = _point_from_row(row)
            if point is None:
                continue
            map_dir = row["map_dir"]
            accumulator = accumulators[map_dir]
            accumulator.count += 1
            accumulator.kind_counts[kind] += 1
            cell = (int(point[0] / grid_size), int(point[1] / grid_size))
            accumulator.cells[cell] = accumulator.cells.get(cell, 0) + 1
            accumulator.cell_sum_x[cell] = accumulator.cell_sum_x.get(cell, 0.0) + point[0]
            accumulator.cell_sum_z[cell] = accumulator.cell_sum_z.get(cell, 0.0) + point[1]
            nearest = _nearest_index_distance(
                point,
                marker_points.get(map_dir, {}).get("spawn", []),
            )
            if nearest is not None:
                spawn_index, distance = nearest
                accumulator.distance_stats.add(distance)
                accumulator.assigned_spawn_counts[spawn_index] += 1
    return accumulators


def _grid_components(accumulator: ReclaimAccumulator) -> list[dict[str, Any]]:
    cells = set(accumulator.cells)
    components = []
    while cells:
        start = cells.pop()
        stack = [start]
        component = [start]
        while stack:
            cell_x, cell_z = stack.pop()
            for dx in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    if dx == 0 and dz == 0:
                        continue
                    neighbor = (cell_x + dx, cell_z + dz)
                    if neighbor in cells:
                        cells.remove(neighbor)
                        stack.append(neighbor)
                        component.append(neighbor)

        total = sum(accumulator.cells[cell] for cell in component)
        center_x = sum(accumulator.cell_sum_x[cell] for cell in component) / total
        center_z = sum(accumulator.cell_sum_z[cell] for cell in component) / total
        components.append(
            {
                "size": total,
                "cell_count": len(component),
                "center_norm_x": round(center_x, 6),
                "center_norm_z": round(center_z, 6),
            }
        )

    components.sort(
        key=lambda item: (-int(item["size"]), item["center_norm_x"], item["center_norm_z"])
    )
    return components


def _reclaim_metrics(
    accumulator: ReclaimAccumulator | None,
    area_10k: float,
    spawn_count: int,
) -> dict[str, Any]:
    if accumulator is None:
        accumulator = ReclaimAccumulator()
    components = _grid_components(accumulator)
    component_sizes = [int(component["size"]) for component in components]
    distances = accumulator.distance_stats.values
    return {
        "reclaim_points_streamed": accumulator.count,
        "reclaim_points_per_spawn": round(accumulator.count / spawn_count, 6)
        if spawn_count
        else "",
        "reclaim_points_per_10k_area": round(accumulator.count / area_10k, 6)
        if area_10k
        else "",
        "reclaim_group_count": len(components),
        "reclaim_group_density_per_10k_area": round(len(components) / area_10k, 6)
        if area_10k
        else "",
        "reclaim_group_mean_size": round(sum(component_sizes) / len(component_sizes), 6)
        if component_sizes
        else 0,
        "reclaim_group_max_size": max(component_sizes) if component_sizes else 0,
        "reclaim_nearest_spawn_dist_mean": round(sum(distances) / len(distances), 6)
        if distances
        else "",
        "reclaim_nearest_spawn_dist_p95": round(_percentile(distances, 0.95), 6)
        if distances
        else "",
        "reclaim_within_5pct_spawn": accumulator.distance_stats.within_counts["0.05"],
        "reclaim_within_10pct_spawn": accumulator.distance_stats.within_counts["0.10"],
        "reclaim_within_20pct_spawn": accumulator.distance_stats.within_counts["0.20"],
        **_assignment_metrics("reclaim", accumulator.assigned_spawn_counts, spawn_count),
        "reclaim_kind_counts_json": json.dumps(dict(sorted(accumulator.kind_counts.items()))),
        "reclaim_groups_json": json.dumps(components[:100], sort_keys=True),
    }


def build_resource_balance_rows(
    features_csv: Path,
    terrain_csv: Path,
    markers_csv: Path,
    entities_csv: Path,
    entities_summary_csv: Path,
    symmetry_tolerance: float,
    resource_cluster_radius: float,
    reclaim_grid_size: float,
) -> list[dict[str, Any]]:
    _set_csv_field_limit()
    features = _read_csv_by_map(features_csv, key="top_level_dir")
    terrain = _read_csv_by_map(terrain_csv)
    entity_summary = _read_csv_by_map(entities_summary_csv)
    marker_points = _read_marker_points(markers_csv)
    reclaim = _stream_reclaim(entities_csv, marker_points, reclaim_grid_size)

    rows = []
    for map_dir, feature in sorted(features.items()):
        terrain_row = terrain.get(map_dir, {})
        entity_summary_row = entity_summary.get(map_dir, {})
        points = marker_points.get(map_dir, {})
        spawns = points.get("spawn", [])
        mexes = points.get("mex", [])
        hydros = points.get("hydro", [])
        spawn_count = len(spawns) or _int_or_zero(feature.get("spawn_count"))
        width = _float_or_zero(terrain_row.get("playable_width") or feature.get("playable_width"))
        height = _float_or_zero(
            terrain_row.get("playable_height") or feature.get("playable_height")
        )
        area = width * height
        area_10k = area / 10000 if area else 0.0

        row = {column: "" for column in RESOURCE_COLUMNS}
        row.update(
            {
                "map_dir": map_dir,
                "playable_width": round(width, 3) if width else "",
                "playable_height": round(height, 3) if height else "",
                "playable_area": round(area, 3) if area else "",
                "player_slots": feature.get("player_slots", ""),
                "spawn_count": spawn_count,
                "mex_count": len(mexes),
                "hydro_count": len(hydros),
                "total_reclaim_entity_count": entity_summary_row.get(
                    "total_reclaim_entity_count",
                    "",
                ),
                "civilian_unit_count": entity_summary_row.get("civilian_unit_count", ""),
                "civilian_building_count": entity_summary_row.get("civilian_building_count", ""),
                "civilian_buildings_per_spawn": round(
                    _int_or_zero(entity_summary_row.get("civilian_building_count")) / spawn_count,
                    6,
                )
                if spawn_count
                else "",
                "civilian_buildings_per_10k_area": round(
                    _int_or_zero(entity_summary_row.get("civilian_building_count")) / area_10k,
                    6,
                )
                if area_10k
                else "",
            }
        )
        row.update(_best_symmetry(points, symmetry_tolerance))
        row.update(
            _resource_metrics(
                "mex",
                mexes,
                spawns,
                area_10k,
                spawn_count,
                resource_cluster_radius,
            )
        )
        row.update(
            _resource_metrics(
                "hydro",
                hydros,
                spawns,
                area_10k,
                spawn_count,
                resource_cluster_radius,
            )
        )
        row.update(_reclaim_metrics(reclaim.get(map_dir), area_10k, spawn_count))

        warnings = []
        if not spawns:
            warnings.append("missing_spawns_for_distance_metrics")
        if not area:
            warnings.append("missing_playable_area_for_density_metrics")
        row["warnings"] = "|".join(warnings)
        rows.append(row)
    return rows


def write_csv(rows: list[dict[str, Any]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=RESOURCE_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def write_summary(rows: list[dict[str, Any]], out_path: Path) -> None:
    labels = Counter(str(row["symmetry_label"]) for row in rows)
    detected = sum(1 for row in rows if row["symmetry_detected"] == "true")
    summary = {
        "row_count": len(rows),
        "symmetry_detected_count": detected,
        "symmetry_label_counts": dict(sorted(labels.items())),
        "maps_missing_spawns": sum(
            1 for row in rows if "missing_spawns_for_distance_metrics" in row["warnings"]
        ),
        "maps_missing_playable_area": sum(
            1 for row in rows if "missing_playable_area_for_density_metrics" in row["warnings"]
        ),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract symmetry, spawn-distance, and resource grouping metrics."
    )
    parser.add_argument("--features", required=True, type=Path)
    parser.add_argument("--terrain", required=True, type=Path)
    parser.add_argument("--markers", required=True, type=Path)
    parser.add_argument("--entities", required=True, type=Path)
    parser.add_argument("--entities-summary", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--summary-out", type=Path)
    parser.add_argument("--symmetry-tolerance", default=0.025, type=float)
    parser.add_argument("--resource-cluster-radius", default=0.045, type=float)
    parser.add_argument("--reclaim-grid-size", default=0.035, type=float)
    return parser.parse_args()


def main() -> int:
    _set_csv_field_limit()
    args = parse_args()
    rows = build_resource_balance_rows(
        features_csv=args.features,
        terrain_csv=args.terrain,
        markers_csv=args.markers,
        entities_csv=args.entities,
        entities_summary_csv=args.entities_summary,
        symmetry_tolerance=args.symmetry_tolerance,
        resource_cluster_radius=args.resource_cluster_radius,
        reclaim_grid_size=args.reclaim_grid_size,
    )
    write_csv(rows, args.out)
    if args.summary_out:
        write_summary(rows, args.summary_out)
    print(f"Wrote {len(rows)} resource balance row(s) to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
