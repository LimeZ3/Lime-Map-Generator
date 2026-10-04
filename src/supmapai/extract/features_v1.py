"""Build the V1 flat feature table and survey seed from extracted map data."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Any

FEATURE_COLUMNS = [
    "map_id",
    "top_level_dir",
    "selected_map_dir",
    "scenario_name",
    "map_version",
    "name_signals",
    "duplicate_family_key",
    "candidate_count",
    "backup_candidate_count",
    "has_scmap",
    "has_scenario_lua",
    "has_save_lua",
    "has_preview_image",
    "parse_warnings",
    "source_quality",
    "size_x",
    "size_z",
    "size_class",
    "player_slots",
    "spawn_count",
    "spawn_positions_json",
    "slots_match_spawns",
    "team_count_declared",
    "team_layout_label",
    "predicted_team_setting",
    "predicted_team_layout",
    "predicted_team_count",
    "predicted_team_size",
    "predicted_team_confidence",
    "predicted_team_strategy",
    "predicted_team_balance_score",
    "compatible_team_settings_json",
    "spawn_geometry_label",
    "mex_count",
    "hydro_count",
    "mex_positions_json",
    "hydro_positions_json",
    "mex_per_player",
    "hydro_per_player",
    "reclaim_mass_total_declared",
    "reclaim_energy_total_declared",
    "reclaim_entity_count",
    "scmap_prop_count",
    "tree_prop_count",
    "rock_prop_count",
    "boulder_prop_count",
    "scmap_reclaim_prop_count",
    "total_reclaim_entity_count",
    "reclaim_entity_positions_json",
    "reclaim_entity_type_counts_json",
    "reclaim_mass_per_player",
    "reclaim_energy_per_player",
    "civilian_unit_count",
    "civilian_unit_positions_json",
    "civilian_building_count",
    "civilian_building_positions_json",
    "enemy_civilian_unit_count",
    "civilian_type_counts_json",
    "has_civilian_base",
    "height_min",
    "height_max",
    "height_mean",
    "height_std",
    "playable_area_source",
    "playable_x0",
    "playable_z0",
    "playable_x1",
    "playable_z1",
    "playable_width",
    "playable_height",
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
    "shoreline_length_cells",
    "shoreline_length_per_10k_area",
    "structural_water_body_count",
    "structural_water_body_sizes_json",
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
    "structure_warnings",
    "flat_height_mode_percent",
    "slope_mean",
    "slope_p95",
    "symmetry_detected",
    "symmetry_order",
    "symmetry_label",
    "symmetry_score",
    "symmetry_basis",
    "texture_pack",
    "texture_names_json",
    "biome_guess",
]


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _read_jsonl_by_map(path: Path) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            records[record["map_dir"]] = record
    return records


def _name_families_by_map(path: Path | None) -> dict[str, str]:
    if path is None or not path.exists():
        return {}
    rows = _read_csv(path)
    return {row["map_dir"]: row["family_key"] for row in rows}


def _csv_by_map(path: Path | None) -> dict[str, dict[str, str]]:
    if path is None or not path.exists():
        return {}
    return {row["map_dir"]: row for row in _read_csv(path)}


def _stable_id(top_level_dir: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", top_level_dir.lower()).strip("-")
    digest = hashlib.sha1(top_level_dir.encode("utf-8")).hexdigest()[:10]
    return f"{slug[:60]}-{digest}" if slug else digest


def _int_or_none(value: Any) -> int | None:
    try:
        if value == "":
            return None
        return int(float(str(value)))
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> float | None:
    try:
        if value == "":
            return None
        return float(str(value))
    except (TypeError, ValueError):
        return None


def _ratio(numerator: int | float | None, denominator: int | float | None) -> str:
    if numerator is None or denominator in (None, 0):
        return ""
    return f"{numerator / denominator:.4f}"


def _size_class(size_x: int | None) -> str:
    return {
        64: "1.25km",
        128: "2.5km",
        256: "5km",
        512: "10km",
        1024: "20km",
        2048: "40km",
        4096: "80km",
    }.get(size_x or 0, "unknown")


def _team_layout_label(team_count: int | None) -> str:
    if team_count is None:
        return "unknown"
    if team_count <= 1:
        return "ffa"
    if team_count == 2:
        return "two_teams"
    return "three_plus_teams"


def _source_quality(warnings: str) -> str:
    missing_tokens = ("missing_scmap", "missing_scenario_lua", "missing_save_lua")
    if any(token in warnings for token in missing_tokens):
        return "broken"
    if warnings:
        return "partial"
    return "complete"


def _bool_text(value: bool | None) -> str:
    if value is None:
        return ""
    return str(value).lower()


def _json_or_default(value: str, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _build_feature_row(
    metadata: dict[str, str],
    entity: dict[str, Any] | None,
    family_key: str,
    terrain: dict[str, str] | None = None,
    scmap_props: dict[str, str] | None = None,
    team_layout: dict[str, str] | None = None,
    structure_metrics: dict[str, str] | None = None,
) -> dict[str, Any]:
    top_level_dir = metadata["map_dir"]
    player_slots = _int_or_none(metadata.get("player_slots"))
    spawn_count = (
        _int_or_none(entity.get("spawn_positions") and len(entity["spawn_positions"]))
        if entity
        else None
    )
    mex_count = _int_or_none(entity.get("marker_type_counts", {}).get("Mass")) if entity else None
    hydro_count = (
        _int_or_none(entity.get("marker_type_counts", {}).get("Hydrocarbon"))
        if entity
        else None
    )
    reclaim_mass = _float_or_none(metadata.get("reclaim_mass"))
    reclaim_energy = _float_or_none(metadata.get("reclaim_energy"))
    lua_reclaim_count = _int_or_none(entity.get("reclaim_entity_count")) if entity else None
    scmap_reclaim_count = (
        _int_or_none(scmap_props.get("reclaim_prop_count")) if scmap_props else None
    )
    team_count = _int_or_none(entity.get("team_count_declared")) if entity else None
    entity_warnings = "|".join(entity.get("warnings", [])) if entity else ""
    warnings = "|".join(filter(None, [metadata.get("warnings", ""), entity_warnings]))
    size_x = _int_or_none(metadata.get("scenario_size_x") or metadata.get("scmap_width"))
    size_z = _int_or_none(metadata.get("scenario_size_z") or metadata.get("scmap_height"))

    row = {column: "" for column in FEATURE_COLUMNS}
    row.update(
        {
            "map_id": _stable_id(top_level_dir),
            "top_level_dir": top_level_dir,
            "selected_map_dir": metadata.get("selected_map_dir", ""),
            "scenario_name": metadata.get("scenario_name", ""),
            "map_version": metadata.get("map_version", ""),
            "name_signals": metadata.get("name_signals", ""),
            "duplicate_family_key": family_key,
            "candidate_count": metadata.get("candidate_count", ""),
            "backup_candidate_count": metadata.get("backup_candidate_count", ""),
            "has_scmap": _bool_text(bool(metadata.get("scmap_size_bytes"))),
            "has_scenario_lua": _bool_text("missing_scenario_lua" not in warnings),
            "has_save_lua": _bool_text("missing_save_lua" not in warnings),
            "has_preview_image": "",
            "parse_warnings": warnings,
            "source_quality": _source_quality(warnings),
            "size_x": size_x or "",
            "size_z": size_z or "",
            "size_class": _size_class(size_x),
            "player_slots": player_slots or "",
            "spawn_count": spawn_count or "",
            "spawn_positions_json": json.dumps(
                entity.get("spawn_positions", []) if entity else [],
                sort_keys=True,
            ),
            "slots_match_spawns": _bool_text(
                player_slots == spawn_count
                if player_slots is not None and spawn_count is not None
                else None
            ),
            "team_count_declared": team_count or "",
            "team_layout_label": _team_layout_label(team_count),
            "predicted_team_setting": (
                team_layout.get("predicted_team_setting", "") if team_layout else ""
            ),
            "predicted_team_layout": (
                team_layout.get("predicted_layout", "") if team_layout else ""
            ),
            "predicted_team_count": (
                team_layout.get("predicted_team_count", "") if team_layout else ""
            ),
            "predicted_team_size": (
                team_layout.get("predicted_team_size", "") if team_layout else ""
            ),
            "predicted_team_confidence": (
                team_layout.get("prediction_confidence", "") if team_layout else ""
            ),
            "predicted_team_strategy": (
                team_layout.get("prediction_strategy", "") if team_layout else ""
            ),
            "predicted_team_balance_score": (
                team_layout.get("predicted_resource_fairness", "") if team_layout else ""
            ),
            "compatible_team_settings_json": (
                team_layout.get("compatible_team_settings_json", "[]")
                if team_layout
                else "[]"
            ),
            "spawn_geometry_label": "unknown",
            "mex_count": mex_count or 0,
            "hydro_count": hydro_count or 0,
            "mex_positions_json": json.dumps(
                entity.get("mex_positions", []) if entity else [],
                sort_keys=True,
            ),
            "hydro_positions_json": json.dumps(
                entity.get("hydro_positions", []) if entity else [],
                sort_keys=True,
            ),
            "mex_per_player": _ratio(mex_count, player_slots),
            "hydro_per_player": _ratio(hydro_count, player_slots),
            "reclaim_mass_total_declared": reclaim_mass if reclaim_mass is not None else "",
            "reclaim_energy_total_declared": reclaim_energy if reclaim_energy is not None else "",
            "reclaim_entity_count": lua_reclaim_count if lua_reclaim_count is not None else "",
            "scmap_prop_count": scmap_props.get("prop_count", "") if scmap_props else "",
            "tree_prop_count": scmap_props.get("tree_prop_count", "") if scmap_props else "",
            "rock_prop_count": scmap_props.get("rock_prop_count", "") if scmap_props else "",
            "boulder_prop_count": scmap_props.get("boulder_prop_count", "") if scmap_props else "",
            "scmap_reclaim_prop_count": (
                scmap_reclaim_count if scmap_reclaim_count is not None else ""
            ),
            "total_reclaim_entity_count": (
                (lua_reclaim_count or 0) + (scmap_reclaim_count or 0)
                if lua_reclaim_count is not None or scmap_reclaim_count is not None
                else ""
            ),
            "reclaim_entity_positions_json": json.dumps(
                entity.get("reclaim_entity_positions", []) if entity else [],
                sort_keys=True,
            ),
            "reclaim_entity_type_counts_json": json.dumps(
                entity.get("reclaim_entity_type_counts", {}) if entity else {},
                sort_keys=True,
            ),
            "reclaim_mass_per_player": _ratio(reclaim_mass, player_slots),
            "reclaim_energy_per_player": _ratio(reclaim_energy, player_slots),
            "civilian_unit_count": entity.get("civilian_unit_count", 0) if entity else 0,
            "civilian_unit_positions_json": json.dumps(
                entity.get("civilian_unit_positions", []) if entity else [],
                sort_keys=True,
            ),
            "civilian_building_count": entity.get("civilian_building_count", 0) if entity else 0,
            "civilian_building_positions_json": json.dumps(
                entity.get("civilian_building_positions", []) if entity else [],
                sort_keys=True,
            ),
            "enemy_civilian_unit_count": "",
            "civilian_type_counts_json": json.dumps(
                entity.get("civilian_type_counts", {}) if entity else {},
                sort_keys=True,
            ),
            "has_civilian_base": _bool_text(
                (entity.get("civilian_building_count", 0) if entity else 0) >= 3
            ),
            "height_min": terrain.get("height_min", "") if terrain else "",
            "height_max": terrain.get("height_max", "") if terrain else "",
            "height_mean": terrain.get("height_mean", "") if terrain else "",
            "height_std": terrain.get("height_std", "") if terrain else "",
            "playable_area_source": terrain.get("playable_area_source", "") if terrain else "",
            "playable_x0": terrain.get("playable_x0", "") if terrain else "",
            "playable_z0": terrain.get("playable_z0", "") if terrain else "",
            "playable_x1": terrain.get("playable_x1", "") if terrain else "",
            "playable_z1": terrain.get("playable_z1", "") if terrain else "",
            "playable_width": terrain.get("playable_width", "") if terrain else "",
            "playable_height": terrain.get("playable_height", "") if terrain else "",
            "water_level": terrain.get("water_level", "") if terrain else "",
            "water_level_source": terrain.get("water_level_source", "") if terrain else "",
            "water_percent": terrain.get("water_percent", "") if terrain else "",
            "shallow_water_percent": terrain.get("shallow_water_percent", "")
            if terrain
            else "",
            "medium_water_percent": terrain.get("medium_water_percent", "")
            if terrain
            else "",
            "deep_water_percent": terrain.get("deep_water_percent", "") if terrain else "",
            "water_depth_max": terrain.get("water_depth_max", "") if terrain else "",
            "water_depth_mean": terrain.get("water_depth_mean", "") if terrain else "",
            "water_depth_p50": terrain.get("water_depth_p50", "") if terrain else "",
            "water_depth_p95": terrain.get("water_depth_p95", "") if terrain else "",
            "water_body_count": terrain.get("water_body_count", "") if terrain else "",
            "largest_water_body_percent": terrain.get("largest_water_body_percent", "")
            if terrain
            else "",
            "largest_water_body_depth_mean": terrain.get("largest_water_body_depth_mean", "")
            if terrain
            else "",
            "largest_water_body_depth_max": terrain.get("largest_water_body_depth_max", "")
            if terrain
            else "",
            "water_bodies_json": terrain.get("water_bodies_json", "[]") if terrain else "[]",
            "water_artifact_removed_cells": terrain.get("water_artifact_removed_cells", "")
            if terrain
            else "",
            "water_artifact_removed_percent": terrain.get("water_artifact_removed_percent", "")
            if terrain
            else "",
            "water_artifact_rule": terrain.get("water_artifact_rule", "") if terrain else "",
            "water_noise_removed_cells": terrain.get("water_noise_removed_cells", "")
            if terrain
            else "",
            "water_noise_removed_percent": terrain.get("water_noise_removed_percent", "")
            if terrain
            else "",
            "water_noise_rule": terrain.get("water_noise_rule", "") if terrain else "",
            "land_percent": terrain.get("land_percent", "") if terrain else "",
            "buildable_percent": terrain.get("buildable_percent", "") if terrain else "",
            "non_buildable_slope_percent": (
                terrain.get("non_buildable_slope_percent", "") if terrain else ""
            ),
            "pathblocking_steep_percent": (
                terrain.get("pathblocking_steep_percent", "") if terrain else ""
            ),
            "land_unit_passable_percent": (
                terrain.get("land_unit_passable_percent", "") if terrain else ""
            ),
            "land_unit_unpassable_percent": (
                terrain.get("land_unit_unpassable_percent", "") if terrain else ""
            ),
            "land_unit_blocked_by_water_percent": (
                terrain.get("land_unit_blocked_by_water_percent", "") if terrain else ""
            ),
            "land_unit_blocked_by_steep_percent": (
                terrain.get("land_unit_blocked_by_steep_percent", "") if terrain else ""
            ),
            "passable_land_component_count": (
                terrain.get("passable_land_component_count", "") if terrain else ""
            ),
            "largest_passable_land_percent": (
                terrain.get("largest_passable_land_percent", "") if terrain else ""
            ),
            "passable_land_components_json": (
                terrain.get("passable_land_components_json", "[]") if terrain else "[]"
            ),
            "shoreline_length_cells": (
                structure_metrics.get("shoreline_length_cells", "")
                if structure_metrics
                else ""
            ),
            "shoreline_length_per_10k_area": (
                structure_metrics.get("shoreline_length_per_10k_area", "")
                if structure_metrics
                else ""
            ),
            "structural_water_body_count": (
                structure_metrics.get("water_body_count", "") if structure_metrics else ""
            ),
            "structural_water_body_sizes_json": (
                structure_metrics.get("water_body_sizes_json", "[]")
                if structure_metrics
                else "[]"
            ),
            "water_body_type_guess": (
                structure_metrics.get("water_body_type_guess", "")
                if structure_metrics
                else ""
            ),
            "plateau_count": (
                structure_metrics.get("plateau_count", "") if structure_metrics else ""
            ),
            "plateau_sizes_json": (
                structure_metrics.get("plateau_sizes_json", "[]") if structure_metrics else "[]"
            ),
            "largest_plateau_percent": (
                structure_metrics.get("largest_plateau_percent", "")
                if structure_metrics
                else ""
            ),
            "engineer_hover_region_count": (
                structure_metrics.get("engineer_hover_region_count", "")
                if structure_metrics
                else ""
            ),
            "largest_engineer_hover_region_percent": (
                structure_metrics.get("largest_engineer_hover_region_percent", "")
                if structure_metrics
                else ""
            ),
            "transport_only_region_count": (
                structure_metrics.get("transport_only_region_count", "")
                if structure_metrics
                else ""
            ),
            "transport_only_area_percent": (
                structure_metrics.get("transport_only_area_percent", "")
                if structure_metrics
                else ""
            ),
            "transport_only_regions_json": (
                structure_metrics.get("transport_only_regions_json", "[]")
                if structure_metrics
                else "[]"
            ),
            "water_separated_region_count": (
                structure_metrics.get("water_separated_region_count", "")
                if structure_metrics
                else ""
            ),
            "water_separated_area_percent": (
                structure_metrics.get("water_separated_area_percent", "")
                if structure_metrics
                else ""
            ),
            "base_to_base_path_exists": (
                structure_metrics.get("base_to_base_path_exists", "")
                if structure_metrics
                else ""
            ),
            "base_to_base_path_length": (
                structure_metrics.get("base_to_base_path_length", "")
                if structure_metrics
                else ""
            ),
            "base_to_base_direct_distance": (
                structure_metrics.get("base_to_base_direct_distance", "")
                if structure_metrics
                else ""
            ),
            "base_to_base_straightness": (
                structure_metrics.get("base_to_base_straightness", "")
                if structure_metrics
                else ""
            ),
            "base_to_base_min_width": (
                structure_metrics.get("base_to_base_min_width", "")
                if structure_metrics
                else ""
            ),
            "base_to_base_median_width": (
                structure_metrics.get("base_to_base_median_width", "")
                if structure_metrics
                else ""
            ),
            "base_to_base_choke_count": (
                structure_metrics.get("base_to_base_choke_count", "")
                if structure_metrics
                else ""
            ),
            "base_to_base_pair_count": (
                structure_metrics.get("base_to_base_pair_count", "")
                if structure_metrics
                else ""
            ),
            "early_reclaim_per_spawn_mean": (
                structure_metrics.get("early_reclaim_per_spawn_mean", "")
                if structure_metrics
                else ""
            ),
            "early_reclaim_per_spawn_min": (
                structure_metrics.get("early_reclaim_per_spawn_min", "")
                if structure_metrics
                else ""
            ),
            "early_reclaim_per_spawn_max": (
                structure_metrics.get("early_reclaim_per_spawn_max", "")
                if structure_metrics
                else ""
            ),
            "center_reclaim_percent": (
                structure_metrics.get("center_reclaim_percent", "")
                if structure_metrics
                else ""
            ),
            "contested_reclaim_percent": (
                structure_metrics.get("contested_reclaim_percent", "")
                if structure_metrics
                else ""
            ),
            "reclaim_cluster_count": (
                structure_metrics.get("reclaim_cluster_count", "")
                if structure_metrics
                else ""
            ),
            "reclaim_cluster_sizes_json": (
                structure_metrics.get("reclaim_cluster_sizes_json", "[]")
                if structure_metrics
                else "[]"
            ),
            "reclaim_spread_label": (
                structure_metrics.get("reclaim_spread_label", "")
                if structure_metrics
                else ""
            ),
            "reclaim_fairness_score": (
                structure_metrics.get("reclaim_fairness_score", "")
                if structure_metrics
                else ""
            ),
            "structure_warnings": (
                structure_metrics.get("warnings", "") if structure_metrics else ""
            ),
            "flat_height_mode_percent": (
                terrain.get("flat_height_mode_percent", "") if terrain else ""
            ),
            "slope_mean": terrain.get("slope_mean", "") if terrain else "",
            "slope_p95": terrain.get("slope_p95", "") if terrain else "",
            "symmetry_detected": "",
            "symmetry_label": "unknown",
            "symmetry_basis": "",
            "texture_pack": terrain.get("texture_pack", "") if terrain else "",
            "texture_names_json": terrain.get("texture_names_json", "[]") if terrain else "[]",
        }
    )
    return row


def build_features(
    metadata_rows: list[dict[str, str]],
    entities_by_map: dict[str, dict[str, Any]],
    family_by_map: dict[str, str],
    terrain_by_map: dict[str, dict[str, str]] | None = None,
    scmap_props_by_map: dict[str, dict[str, str]] | None = None,
    team_layout_by_map: dict[str, dict[str, str]] | None = None,
    structure_metrics_by_map: dict[str, dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    terrain_by_map = terrain_by_map or {}
    scmap_props_by_map = scmap_props_by_map or {}
    team_layout_by_map = team_layout_by_map or {}
    structure_metrics_by_map = structure_metrics_by_map or {}
    rows = [
        _build_feature_row(
            metadata,
            entities_by_map.get(metadata["map_dir"]),
            family_by_map.get(metadata["map_dir"], ""),
            terrain_by_map.get(metadata["map_dir"]),
            scmap_props_by_map.get(metadata["map_dir"]),
            team_layout_by_map.get(metadata["map_dir"]),
            structure_metrics_by_map.get(metadata["map_dir"]),
        )
        for metadata in metadata_rows
    ]
    rows.sort(key=lambda row: row["top_level_dir"].lower())
    return rows


def write_features(rows: list[dict[str, Any]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FEATURE_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def write_survey_seed(rows: list[dict[str, Any]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = []
    for row in rows:
        payload.append(
            {
                "id": row["map_id"],
                "displayName": row["scenario_name"] or row["top_level_dir"],
                "folderName": row["top_level_dir"],
                "sizeClass": row["size_class"],
                "playerSlots": row["player_slots"] or None,
                "spawnPositions": json.loads(row["spawn_positions_json"]),
                "mexCount": row["mex_count"],
                "hydroCount": row["hydro_count"],
                "mexPositions": json.loads(row["mex_positions_json"]),
                "hydroPositions": json.loads(row["hydro_positions_json"]),
                "reclaimMass": row["reclaim_mass_total_declared"] or None,
                "reclaimEntityCount": row["total_reclaim_entity_count"]
                or row["reclaim_entity_count"]
                or None,
                "treePropCount": row["tree_prop_count"] or None,
                "rockPropCount": row["rock_prop_count"] or None,
                "boulderPropCount": row["boulder_prop_count"] or None,
                "civilianUnitCount": row["civilian_unit_count"] or None,
                "civilianBuildingCount": row["civilian_building_count"] or None,
                "waterLevelSource": row["water_level_source"] or None,
                "waterPercent": row["water_percent"] or None,
                "shallowWaterPercent": row["shallow_water_percent"] or None,
                "mediumWaterPercent": row["medium_water_percent"] or None,
                "deepWaterPercent": row["deep_water_percent"] or None,
                "waterDepthMax": row["water_depth_max"] or None,
                "waterDepthMean": row["water_depth_mean"] or None,
                "waterDepthP95": row["water_depth_p95"] or None,
                "waterBodyCount": row["water_body_count"] or None,
                "largestWaterBodyPercent": row["largest_water_body_percent"] or None,
                "largestWaterBodyDepthMax": row["largest_water_body_depth_max"] or None,
                "waterArtifactRemovedCells": row["water_artifact_removed_cells"] or None,
                "waterArtifactRemovedPercent": row["water_artifact_removed_percent"] or None,
                "waterNoiseRemovedCells": row["water_noise_removed_cells"] or None,
                "waterNoiseRemovedPercent": row["water_noise_removed_percent"] or None,
                "playableAreaSource": row["playable_area_source"] or None,
                "playableWidth": row["playable_width"] or None,
                "playableHeight": row["playable_height"] or None,
                "buildablePercent": row["buildable_percent"] or None,
                "pathblockingSteepPercent": row["pathblocking_steep_percent"] or None,
                "landUnitPassablePercent": row["land_unit_passable_percent"] or None,
                "landUnitUnpassablePercent": row["land_unit_unpassable_percent"] or None,
                "passableLandComponentCount": row["passable_land_component_count"] or None,
                "largestPassableLandPercent": row["largest_passable_land_percent"] or None,
                "shorelineLengthCells": row["shoreline_length_cells"] or None,
                "waterBodyTypeGuess": row["water_body_type_guess"] or None,
                "plateauCount": row["plateau_count"] or None,
                "largestPlateauPercent": row["largest_plateau_percent"] or None,
                "engineerHoverRegionCount": row["engineer_hover_region_count"] or None,
                "transportOnlyRegionCount": row["transport_only_region_count"] or None,
                "transportOnlyAreaPercent": row["transport_only_area_percent"] or None,
                "waterSeparatedRegionCount": row["water_separated_region_count"] or None,
                "waterSeparatedAreaPercent": row["water_separated_area_percent"] or None,
                "baseToBasePathExists": row["base_to_base_path_exists"] or None,
                "baseToBaseStraightness": row["base_to_base_straightness"] or None,
                "baseToBaseMinWidth": row["base_to_base_min_width"] or None,
                "baseToBaseMedianWidth": row["base_to_base_median_width"] or None,
                "baseToBaseChokeCount": row["base_to_base_choke_count"] or None,
                "earlyReclaimPerSpawnMean": row["early_reclaim_per_spawn_mean"] or None,
                "centerReclaimPercent": row["center_reclaim_percent"] or None,
                "contestedReclaimPercent": row["contested_reclaim_percent"] or None,
                "reclaimClusterCount": row["reclaim_cluster_count"] or None,
                "reclaimSpreadLabel": row["reclaim_spread_label"] or None,
                "reclaimFairnessScore": row["reclaim_fairness_score"] or None,
                "symmetryLabel": row["symmetry_label"],
                "teamLayoutLabel": row["team_layout_label"],
                "predictedTeamSetting": row["predicted_team_setting"] or None,
                "predictedTeamLayout": row["predicted_team_layout"] or None,
                "predictedTeamConfidence": row["predicted_team_confidence"] or None,
                "compatibleTeamSettings": _json_or_default(
                    row["compatible_team_settings_json"],
                    [],
                ),
                "spawnGeometryLabel": row["spawn_geometry_label"],
                "nameSignals": row["name_signals"].split("|") if row["name_signals"] else [],
                "duplicateFamilyKey": row["duplicate_family_key"] or None,
            }
        )
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build V1 map feature table from metadata, Lua entities, and name families."
    )
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument("--entities", required=True, type=Path)
    parser.add_argument("--name-families", type=Path)
    parser.add_argument("--terrain", type=Path)
    parser.add_argument("--scmap-props-summary", type=Path)
    parser.add_argument("--team-layout", type=Path)
    parser.add_argument("--structure-metrics", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--survey-out", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows = build_features(
        _read_csv(args.metadata),
        _read_jsonl_by_map(args.entities),
        _name_families_by_map(args.name_families),
        _csv_by_map(args.terrain),
        _csv_by_map(args.scmap_props_summary),
        _csv_by_map(args.team_layout),
        _csv_by_map(args.structure_metrics),
    )
    write_features(rows, args.out)
    if args.survey_out:
        write_survey_seed(rows, args.survey_out)
    print(f"Wrote {len(rows)} V1 feature row(s) to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
