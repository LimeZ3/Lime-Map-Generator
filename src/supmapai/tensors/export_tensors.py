"""Export V1 map structure tensors as compressed NumPy archives."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from supmapai.extract import scmap_terrain

CHANNELS = [
    "height_norm",
    "water_mask",
    "water_depth_norm",
    "land_mask",
    "land_passable_mask",
    "buildable_mask",
    "slope_norm",
    "spawn_heatmap",
    "mex_heatmap",
    "hydro_heatmap",
    "reclaim_density",
    "civilian_structure_density",
]

MANIFEST_COLUMNS = [
    "map_id",
    "map_dir",
    "tensor_path",
    "grid_size",
    "channel_count",
    "channels_json",
    "size_class",
    "player_slots",
    "spawn_count",
    "mex_count",
    "hydro_count",
    "audit_status",
    "duplicate_family_key",
    "predicted_team_setting",
    "water_percent",
    "buildable_percent",
    "height_min",
    "height_max",
    "water_level",
    "warnings",
]

RECLAIM_KINDS = {"reclaim", "tree", "rock", "boulder"}
CIVILIAN_STRUCTURE_KINDS = {"civilian_building"}


def _set_csv_field_limit() -> None:
    limit = sys.maxsize
    while True:
        try:
            csv.field_size_limit(limit)
            return
        except OverflowError:
            limit //= 10


def _read_csv_by_map(path: Path, key: str) -> dict[str, dict[str, str]]:
    _set_csv_field_limit()
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return {row[key]: row for row in csv.DictReader(handle) if row.get(key)}


def _read_points_by_map(
    path: Path,
    allowed_kinds: set[str],
) -> dict[str, list[tuple[float, float]]]:
    _set_csv_field_limit()
    points: dict[str, list[tuple[float, float]]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("in_playable_area") != "true" or row.get("kind") not in allowed_kinds:
                continue
            try:
                point = (float(row["norm_x"]), float(row["norm_z"]))
            except (KeyError, ValueError):
                continue
            points.setdefault(row["map_dir"], []).append(point)
    return points


def _read_marker_points(path: Path) -> dict[str, dict[str, list[tuple[float, float]]]]:
    _set_csv_field_limit()
    points: dict[str, dict[str, list[tuple[float, float]]]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("in_playable_area") != "true":
                continue
            kind = row.get("kind", "")
            if kind not in {"spawn", "mex", "hydro"}:
                continue
            try:
                point = (float(row["norm_x"]), float(row["norm_z"]))
            except (KeyError, ValueError):
                continue
            points.setdefault(row["map_dir"], {}).setdefault(kind, []).append(point)
    return points


def _inventory_maps(inventory: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["top_level_dir"]: item for item in inventory.get("maps", [])}


def _first_file_path(inventory: dict[str, Any], item: dict[str, Any], key: str) -> Path | None:
    files = item.get("files", {}).get(key, [])
    if not files:
        return None
    return Path(inventory["maps_root"]) / files[0]["path"]


def _float_or_none(value: Any) -> float | None:
    try:
        if value in ("", None):
            return None
        result = float(str(value))
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _int_or_zero(value: Any) -> int:
    numeric = _float_or_none(value)
    return int(numeric) if numeric is not None else 0


def _crop_slice(row: dict[str, str], shape: tuple[int, int]) -> tuple[slice, slice]:
    height, width = shape
    x0 = max(0, min(width - 1, _int_or_zero(row.get("playable_x0"))))
    z0 = max(0, min(height - 1, _int_or_zero(row.get("playable_z0"))))
    x1 = max(x0 + 1, min(width, _int_or_zero(row.get("playable_x1")) or width))
    z1 = max(z0 + 1, min(height, _int_or_zero(row.get("playable_z1")) or height))
    return slice(z0, z1), slice(x0, x1)


def _decode_height_cells(
    inventory: dict[str, Any],
    item: dict[str, Any],
    feature_row: dict[str, str],
) -> np.ndarray:
    scmap_path = _first_file_path(inventory, item, "scmap")
    if scmap_path is None:
        raise FileNotFoundError("missing scmap in inventory")
    data = scmap_path.read_bytes()
    terrain_header = scmap_terrain._terrain_header(data)
    heightmap_width = terrain_header.map_width + 1
    heightmap_height = terrain_header.map_height + 1
    count = heightmap_width * heightmap_height
    raw = np.frombuffer(
        data,
        dtype="<u2",
        count=count,
        offset=terrain_header.height_offset,
    ).reshape((heightmap_height, heightmap_width))
    vertex_heights = raw.astype(np.float32) / 128.0
    cells = scmap_terrain._height_vertices_to_cells(vertex_heights)
    z_slice, x_slice = _crop_slice(feature_row, cells.shape)
    return cells[z_slice, x_slice].astype(np.float32)


def _resize_float(array: np.ndarray, grid_size: int, resample: int) -> np.ndarray:
    image = Image.fromarray(array.astype(np.float32), mode="F")
    image = image.resize((grid_size, grid_size), resample=resample)
    return np.asarray(image, dtype=np.float32)


def _normalize(array: np.ndarray) -> tuple[np.ndarray, float, float]:
    minimum = float(np.nanmin(array))
    maximum = float(np.nanmax(array))
    if maximum <= minimum:
        return np.zeros_like(array, dtype=np.float32), minimum, maximum
    return ((array - minimum) / (maximum - minimum)).astype(np.float32), minimum, maximum


def _heatmap(
    points: list[tuple[float, float]],
    grid_size: int,
    sigma: float,
    peak: float = 1.0,
) -> np.ndarray:
    heat = np.zeros((grid_size, grid_size), dtype=np.float32)
    if not points:
        return heat
    radius = max(1, int(math.ceil(sigma * 3)))
    coords = np.arange(-radius, radius + 1, dtype=np.float32)
    yy, xx = np.meshgrid(coords, coords, indexing="ij")
    kernel = np.exp(-(xx * xx + yy * yy) / (2 * sigma * sigma)).astype(np.float32) * peak
    for norm_x, norm_z in points:
        x = int(round(norm_x * (grid_size - 1)))
        y = int(round(norm_z * (grid_size - 1)))
        x0 = max(0, x - radius)
        y0 = max(0, y - radius)
        x1 = min(grid_size, x + radius + 1)
        y1 = min(grid_size, y + radius + 1)
        kx0 = x0 - (x - radius)
        ky0 = y0 - (y - radius)
        heat[y0:y1, x0:x1] += kernel[ky0 : ky0 + (y1 - y0), kx0 : kx0 + (x1 - x0)]
    max_value = float(heat.max())
    if max_value > 0:
        heat /= max_value
    return heat


def _build_tensor(
    inventory: dict[str, Any],
    item: dict[str, Any],
    feature_row: dict[str, str],
    marker_points: dict[str, list[tuple[float, float]]],
    reclaim_points: list[tuple[float, float]],
    civilian_structure_points: list[tuple[float, float]],
    grid_size: int,
    buildable_slope_threshold: float,
    pathblocking_slope_threshold: float,
) -> tuple[np.ndarray, dict[str, Any]]:
    heights = _decode_height_cells(inventory, item, feature_row)
    if min(heights.shape) < 2:
        raise ValueError(f"playable height crop too small: {heights.shape}")

    gradient_z, gradient_x = np.gradient(heights)
    slope = np.sqrt(gradient_x * gradient_x + gradient_z * gradient_z).astype(np.float32)
    water_level = _float_or_none(feature_row.get("water_level"))
    water_mask = heights <= water_level if water_level is not None else np.zeros_like(heights, bool)
    water_depth = np.maximum((water_level or 0.0) - heights, 0.0).astype(np.float32)
    land_mask = ~water_mask
    passable_mask = land_mask & (slope <= pathblocking_slope_threshold)
    buildable_mask = land_mask & (slope <= buildable_slope_threshold)

    height_norm, height_min, height_max = _normalize(heights)
    slope_norm, _, slope_max = _normalize(slope)
    depth_norm, _, depth_max = _normalize(water_depth)

    channels = [
        _resize_float(height_norm, grid_size, Image.Resampling.BILINEAR),
        _resize_float(water_mask.astype(np.float32), grid_size, Image.Resampling.NEAREST),
        _resize_float(depth_norm, grid_size, Image.Resampling.BILINEAR),
        _resize_float(land_mask.astype(np.float32), grid_size, Image.Resampling.NEAREST),
        _resize_float(passable_mask.astype(np.float32), grid_size, Image.Resampling.NEAREST),
        _resize_float(buildable_mask.astype(np.float32), grid_size, Image.Resampling.NEAREST),
        _resize_float(slope_norm, grid_size, Image.Resampling.BILINEAR),
        _heatmap(marker_points.get("spawn", []), grid_size, sigma=2.5),
        _heatmap(marker_points.get("mex", []), grid_size, sigma=1.6),
        _heatmap(marker_points.get("hydro", []), grid_size, sigma=1.8),
        _heatmap(reclaim_points, grid_size, sigma=1.2),
        _heatmap(civilian_structure_points, grid_size, sigma=2.0),
    ]
    tensor = np.stack(channels).astype(np.float32)
    meta = {
        "height_min": height_min,
        "height_max": height_max,
        "water_depth_max": depth_max,
        "slope_max": slope_max,
    }
    return tensor, meta


def _manifest_row(
    feature_row: dict[str, str],
    audit_row: dict[str, str] | None,
    tensor_path: Path,
    grid_size: int,
    meta: dict[str, Any],
    warnings: list[str],
) -> dict[str, Any]:
    return {
        "map_id": feature_row.get("map_id", ""),
        "map_dir": feature_row.get("top_level_dir", ""),
        "tensor_path": str(tensor_path),
        "grid_size": grid_size,
        "channel_count": len(CHANNELS),
        "channels_json": json.dumps(CHANNELS),
        "size_class": feature_row.get("size_class", ""),
        "player_slots": feature_row.get("player_slots", ""),
        "spawn_count": feature_row.get("spawn_count", ""),
        "mex_count": feature_row.get("mex_count", ""),
        "hydro_count": feature_row.get("hydro_count", ""),
        "audit_status": (audit_row or {}).get("audit_status", ""),
        "duplicate_family_key": feature_row.get("duplicate_family_key", ""),
        "predicted_team_setting": feature_row.get("predicted_team_setting", ""),
        "water_percent": feature_row.get("water_percent", ""),
        "buildable_percent": feature_row.get("buildable_percent", ""),
        "height_min": round(float(meta.get("height_min", 0.0)), 6),
        "height_max": round(float(meta.get("height_max", 0.0)), 6),
        "water_level": feature_row.get("water_level", ""),
        "warnings": "|".join(warnings),
    }


def export_tensors(
    inventory: dict[str, Any],
    features_csv: Path,
    markers_csv: Path,
    entities_csv: Path,
    audit_maps_csv: Path | None,
    out_dir: Path,
    manifest_out: Path,
    grid_size: int,
    max_maps: int,
    audit_status_filter: set[str] | None,
    map_dir_filter: set[str] | None = None,
) -> list[dict[str, Any]]:
    features_by_map = _read_csv_by_map(features_csv, key="top_level_dir")
    audit_by_map = _read_csv_by_map(audit_maps_csv, key="map_dir") if audit_maps_csv else {}
    inventory_by_map = _inventory_maps(inventory)
    markers_by_map = _read_marker_points(markers_csv)
    reclaim_by_map = _read_points_by_map(entities_csv, RECLAIM_KINDS)
    civilian_structures_by_map = _read_points_by_map(entities_csv, CIVILIAN_STRUCTURE_KINDS)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_rows = []

    selected = sorted(features_by_map)
    if map_dir_filter:
        selected = [map_dir for map_dir in selected if map_dir in map_dir_filter]
    if audit_status_filter is not None:
        selected = [
            map_dir
            for map_dir in selected
            if audit_by_map.get(map_dir, {}).get("audit_status") in audit_status_filter
        ]
    for map_dir in selected[:max_maps]:
        feature_row = features_by_map[map_dir]
        audit_row = audit_by_map.get(map_dir)
        item = inventory_by_map.get(map_dir)
        if item is None:
            continue
        warnings = []
        tensor_path = out_dir / f"{feature_row.get('map_id') or map_dir}.npz"
        try:
            tensor, meta = _build_tensor(
                inventory=inventory,
                item=item,
                feature_row=feature_row,
                marker_points=markers_by_map.get(map_dir, {}),
                reclaim_points=reclaim_by_map.get(map_dir, []),
                civilian_structure_points=civilian_structures_by_map.get(map_dir, []),
                grid_size=grid_size,
                buildable_slope_threshold=0.1,
                pathblocking_slope_threshold=0.7,
            )
            np.savez_compressed(
                tensor_path,
                tensor=tensor,
                channels=np.array(CHANNELS),
                map_id=np.array(feature_row.get("map_id", "")),
                map_dir=np.array(map_dir),
            )
        except Exception as exc:
            meta = {}
            warnings.append(f"tensor_export_failed:{type(exc).__name__}:{exc}")
            tensor_path = Path("")
        manifest_rows.append(
            _manifest_row(
                feature_row,
                audit_row,
                tensor_path,
                grid_size,
                meta,
                warnings,
            )
        )

    manifest_out.parent.mkdir(parents=True, exist_ok=True)
    with manifest_out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANIFEST_COLUMNS)
        writer.writeheader()
        writer.writerows(manifest_rows)
    return manifest_rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export ML-ready V1 tensor .npz files.")
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--features", required=True, type=Path)
    parser.add_argument("--markers", required=True, type=Path)
    parser.add_argument("--entities", required=True, type=Path)
    parser.add_argument("--audit-maps", type=Path)
    parser.add_argument(
        "--audit-status",
        action="append",
        help="Export only maps with this audit status. Repeat for multiple statuses.",
    )
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--manifest-out", required=True, type=Path)
    parser.add_argument("--grid-size", default=256, type=int)
    parser.add_argument("--max-maps", default=10, type=int)
    parser.add_argument("--map-dir", action="append", default=[])
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    inventory = json.loads(args.inventory.read_text(encoding="utf-8-sig"))
    rows = export_tensors(
        inventory=inventory,
        features_csv=args.features,
        markers_csv=args.markers,
        entities_csv=args.entities,
        audit_maps_csv=args.audit_maps,
        out_dir=args.out_dir,
        manifest_out=args.manifest_out,
        grid_size=args.grid_size,
        max_maps=args.max_maps,
        audit_status_filter=set(args.audit_status) if args.audit_status else None,
        map_dir_filter=set(args.map_dir) if args.map_dir else None,
    )
    failures = sum(1 for row in rows if row["warnings"])
    print(f"Wrote {len(rows)} tensor manifest row(s) to {args.manifest_out}")
    if failures:
        print(f"Tensor export failures: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
