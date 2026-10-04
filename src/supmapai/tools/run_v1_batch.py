"""Run the V1 processing pipeline for one inventory chunk."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from supmapai.extract import (
    features_v1,
    lua_entities,
    metadata_from_inventory,
    name_families,
    resource_balance,
    scmap_props,
    scmap_terrain,
    structure_metrics,
    team_layout,
)
from supmapai.tools import entity_layers, marker_layers


def _stage(name: str, started: float) -> None:
    elapsed = time.perf_counter() - started
    print(f"[{elapsed:8.1f}s] {name}")


def run_batch(
    inventory_path: Path,
    out_dir: Path,
    preview_dir: Path,
    batch_name: str,
    max_maps: int,
) -> dict[str, Path]:
    started = time.perf_counter()
    inventory = json.loads(inventory_path.read_text(encoding="utf-8-sig"))
    map_count = int(inventory.get("map_count", len(inventory.get("maps", []))))
    if map_count > max_maps:
        raise ValueError(f"Refusing to run {map_count} maps with --max-maps {max_maps}")

    out_dir.mkdir(parents=True, exist_ok=True)
    preview_dir.mkdir(parents=True, exist_ok=True)

    paths = {
        "metadata": out_dir / f"{batch_name}_metadata.csv",
        "lua_entities": out_dir / f"{batch_name}_lua_entities.jsonl",
        "lua_summary": out_dir / f"{batch_name}_lua_entities_summary.csv",
        "terrain": out_dir / f"{batch_name}_terrain.csv",
        "scmap_props": out_dir / f"{batch_name}_scmap_props.jsonl",
        "scmap_props_summary": out_dir / f"{batch_name}_scmap_props_summary.csv",
        "name_families": out_dir / f"{batch_name}_name_families.csv",
        "name_families_summary": out_dir / f"{batch_name}_name_families_summary.json",
        "markers": out_dir / f"{batch_name}_markers.csv",
        "markers_summary": out_dir / f"{batch_name}_markers_summary.csv",
        "entities": out_dir / f"{batch_name}_entities.csv",
        "entities_summary": out_dir / f"{batch_name}_entities_summary.csv",
        "features": out_dir / f"{batch_name}_map_features_v1.csv",
        "survey_seed": out_dir / f"{batch_name}_maps.generated.json",
        "resource_balance": out_dir / f"{batch_name}_resource_balance.csv",
        "resource_balance_summary": out_dir / f"{batch_name}_resource_balance_summary.json",
        "team_layout": out_dir / f"{batch_name}_team_layout.csv",
        "team_layout_summary": out_dir / f"{batch_name}_team_layout_summary.json",
        "structure_metrics": out_dir / f"{batch_name}_structure_metrics.csv",
    }

    metadata_rows = metadata_from_inventory.extract_metadata(inventory)
    metadata_from_inventory.write_csv(metadata_rows, paths["metadata"])
    _stage("metadata", started)

    lua_records = lua_entities.extract_entities(inventory)
    lua_entities.write_jsonl(lua_records, paths["lua_entities"])
    lua_entities.write_summary_csv(lua_records, paths["lua_summary"])
    _stage("lua entities", started)

    terrain_rows = scmap_terrain.decode_inventory(
        inventory=inventory,
        map_dir_filter=None,
        max_maps=max_maps,
        preview_dir=preview_dir,
        corner_artifact_cells=0,
        uncertain_water_min_component_cells=64,
    )
    scmap_terrain.write_csv(terrain_rows, paths["terrain"])
    _stage("terrain + terrain/water/pathability PNGs", started)

    prop_records = scmap_props.extract_scmap_props(
        inventory=inventory,
        map_dir_filter=None,
        max_maps=max_maps,
    )
    scmap_props.write_jsonl(prop_records, paths["scmap_props"])
    scmap_props.write_summary_csv(prop_records, paths["scmap_props_summary"])
    _stage("scmap props", started)

    family_rows = name_families.build_name_families(
        name_families.read_metadata(paths["metadata"])
    )
    name_families.write_csv(family_rows, paths["name_families"])
    name_families.write_summary(family_rows, paths["name_families_summary"])
    _stage("name families", started)

    marker_layers.export_marker_layers(
        entities_jsonl=paths["lua_entities"],
        terrain_csv=paths["terrain"],
        out_csv=paths["markers"],
        summary_out=paths["markers_summary"],
        preview_dir=preview_dir,
    )
    _stage("marker layer + marker PNGs", started)

    entity_layers.export_entity_layers(
        entities_jsonl=paths["lua_entities"],
        terrain_csv=paths["terrain"],
        out_csv=paths["entities"],
        summary_out=paths["entities_summary"],
        preview_dir=preview_dir,
        scmap_props_jsonl=paths["scmap_props"],
    )
    _stage("entity/reclaim layer + entity PNGs", started)

    preliminary_feature_rows = features_v1.build_features(
        metadata_rows=features_v1._read_csv(paths["metadata"]),
        entities_by_map=features_v1._read_jsonl_by_map(paths["lua_entities"]),
        family_by_map=features_v1._name_families_by_map(paths["name_families"]),
        terrain_by_map=features_v1._csv_by_map(paths["terrain"]),
        scmap_props_by_map=features_v1._csv_by_map(paths["scmap_props_summary"]),
    )
    features_v1.write_features(preliminary_feature_rows, paths["features"])
    _stage("preliminary features", started)

    resource_rows = resource_balance.build_resource_balance_rows(
        features_csv=paths["features"],
        terrain_csv=paths["terrain"],
        markers_csv=paths["markers"],
        entities_csv=paths["entities"],
        entities_summary_csv=paths["entities_summary"],
        symmetry_tolerance=0.025,
        resource_cluster_radius=0.045,
        reclaim_grid_size=0.035,
    )
    resource_balance.write_csv(resource_rows, paths["resource_balance"])
    resource_balance.write_summary(resource_rows, paths["resource_balance_summary"])
    _stage("resource balance + symmetry", started)

    team_rows = team_layout.infer_team_layout_rows(
        markers_csv=paths["markers"],
        resource_balance_csv=paths["resource_balance"],
    )
    team_layout.write_csv(team_rows, paths["team_layout"])
    team_layout.write_summary(team_rows, paths["team_layout_summary"])
    _stage("team layout prediction", started)

    structure_rows = structure_metrics.build_structure_rows(
        inventory=inventory,
        terrain_csv=paths["terrain"],
        markers_csv=paths["markers"],
        entities_csv=paths["entities"],
        team_layout_csv=paths["team_layout"],
        max_maps=max_maps,
    )
    structure_metrics.write_csv(structure_rows, paths["structure_metrics"])
    _stage("structure metrics", started)

    feature_rows = features_v1.build_features(
        metadata_rows=features_v1._read_csv(paths["metadata"]),
        entities_by_map=features_v1._read_jsonl_by_map(paths["lua_entities"]),
        family_by_map=features_v1._name_families_by_map(paths["name_families"]),
        terrain_by_map=features_v1._csv_by_map(paths["terrain"]),
        scmap_props_by_map=features_v1._csv_by_map(paths["scmap_props_summary"]),
        team_layout_by_map=features_v1._csv_by_map(paths["team_layout"]),
        structure_metrics_by_map=features_v1._csv_by_map(paths["structure_metrics"]),
    )
    features_v1.write_features(feature_rows, paths["features"])
    features_v1.write_survey_seed(feature_rows, paths["survey_seed"])
    _stage("final features + survey seed", started)

    print(f"Finished {batch_name}: {map_count} map(s)")
    return paths


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run V1 processing for one inventory chunk.")
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--preview-dir", required=True, type=Path)
    parser.add_argument("--batch-name", required=True)
    parser.add_argument("--max-maps", default=250, type=int)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_batch(
        inventory_path=args.inventory,
        out_dir=args.out_dir,
        preview_dir=args.preview_dir,
        batch_name=args.batch_name,
        max_maps=args.max_maps,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
