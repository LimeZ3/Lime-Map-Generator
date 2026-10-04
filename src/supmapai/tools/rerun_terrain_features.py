"""Rerun terrain-derived outputs for existing V1 batches."""

from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from supmapai.extract import features_v1, scmap_terrain, structure_metrics
from supmapai.tools import entity_layers, marker_layers


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _batch_name(index: int) -> str:
    return f"batch_{index:04d}"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _append_log(path: Path, message: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(message.rstrip() + "\n")


def _chunk_inventory_path(
    manifest: dict[str, Any],
    chunk: dict[str, Any],
    manifest_path: Path,
) -> Path:
    return manifest_path.parent / str(chunk["inventory_path"])


def rerun_batch(
    inventory_path: Path,
    out_dir: Path,
    preview_dir: Path,
    batch_name: str,
    max_maps: int,
    log_path: Path,
) -> None:
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
        "terrain": out_dir / f"{batch_name}_terrain.csv",
        "scmap_props": out_dir / f"{batch_name}_scmap_props.jsonl",
        "scmap_props_summary": out_dir / f"{batch_name}_scmap_props_summary.csv",
        "name_families": out_dir / f"{batch_name}_name_families.csv",
        "markers": out_dir / f"{batch_name}_markers.csv",
        "markers_summary": out_dir / f"{batch_name}_markers_summary.csv",
        "entities": out_dir / f"{batch_name}_entities.csv",
        "entities_summary": out_dir / f"{batch_name}_entities_summary.csv",
        "team_layout": out_dir / f"{batch_name}_team_layout.csv",
        "structure_metrics": out_dir / f"{batch_name}_structure_metrics.csv",
        "features": out_dir / f"{batch_name}_map_features_v1.csv",
        "survey_seed": out_dir / f"{batch_name}_maps.generated.json",
    }

    for required in (
        "metadata",
        "lua_entities",
        "scmap_props_summary",
        "name_families",
        "markers",
        "entities",
        "entities_summary",
    ):
        if not paths[required].exists():
            raise FileNotFoundError(f"Missing required prior output: {paths[required]}")

    _append_log(log_path, f"[{batch_name}] terrain start")
    terrain_rows = scmap_terrain.decode_inventory(
        inventory=inventory,
        map_dir_filter=None,
        max_maps=max_maps,
        preview_dir=preview_dir,
        corner_artifact_cells=0,
        uncertain_water_min_component_cells=64,
    )
    scmap_terrain.write_csv(terrain_rows, paths["terrain"])
    _append_log(log_path, f"[{batch_name}] terrain done at {time.perf_counter() - started:.1f}s")

    marker_layers.export_marker_layers(
        entities_jsonl=paths["lua_entities"],
        terrain_csv=paths["terrain"],
        out_csv=paths["markers"],
        summary_out=paths["markers_summary"],
        preview_dir=preview_dir,
    )
    _append_log(log_path, f"[{batch_name}] marker layers done")

    entity_layers.export_entity_layers(
        entities_jsonl=paths["lua_entities"],
        terrain_csv=paths["terrain"],
        out_csv=paths["entities"],
        summary_out=paths["entities_summary"],
        preview_dir=preview_dir,
        scmap_props_jsonl=paths["scmap_props"] if paths["scmap_props"].exists() else None,
    )
    _append_log(log_path, f"[{batch_name}] entity layers done")

    structure_rows = structure_metrics.build_structure_rows(
        inventory=inventory,
        terrain_csv=paths["terrain"],
        markers_csv=paths["markers"],
        entities_csv=paths["entities"],
        team_layout_csv=paths["team_layout"] if paths["team_layout"].exists() else None,
        max_maps=max_maps,
    )
    structure_metrics.write_csv(structure_rows, paths["structure_metrics"])
    _append_log(log_path, f"[{batch_name}] structure metrics done")

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
    _append_log(log_path, f"[{batch_name}] features done")


def rerun_batches(
    manifest_path: Path,
    out_root: Path,
    preview_root: Path,
    logs_dir: Path,
    start: int,
    end_exclusive: int | None,
    exclude: set[int],
    max_maps: int,
    continue_on_failure: bool,
) -> int:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    chunks = [
        chunk
        for chunk in manifest.get("chunks", [])
        if int(chunk["chunk_index"]) >= start
        and (end_exclusive is None or int(chunk["chunk_index"]) < end_exclusive)
        and int(chunk["chunk_index"]) not in exclude
    ]
    status_path = logs_dir / "terrain_feature_rerun_status.json"
    status: dict[str, Any] = {
        "started_at": _utc_now(),
        "finished_at": None,
        "manifest_path": str(manifest_path),
        "selected_batch_count": len(chunks),
        "exclude": sorted(exclude),
        "batches": [],
        "return_code": None,
    }
    _write_json(status_path, status)

    overall_return_code = 0
    for chunk in chunks:
        index = int(chunk["chunk_index"])
        batch_name = _batch_name(index)
        out_dir = out_root / batch_name
        preview_dir = preview_root / batch_name
        log_path = logs_dir / f"{batch_name}_terrain_feature_rerun.log"
        batch_status: dict[str, Any] = {
            "batch_name": batch_name,
            "chunk_index": index,
            "map_count": int(chunk["map_count"]),
            "started_at": _utc_now(),
            "finished_at": None,
            "elapsed_seconds": None,
            "status": "running",
            "log_path": str(log_path),
        }
        status["batches"].append(batch_status)
        _write_json(status_path, status)

        started = time.perf_counter()
        try:
            rerun_batch(
                inventory_path=_chunk_inventory_path(manifest, chunk, manifest_path),
                out_dir=out_dir,
                preview_dir=preview_dir,
                batch_name=batch_name,
                max_maps=max_maps,
                log_path=log_path,
            )
        except Exception as exc:
            batch_status["status"] = "failed"
            batch_status["error"] = f"{type(exc).__name__}: {exc}"
            overall_return_code = 1
            _append_log(log_path, f"[{batch_name}] failed: {type(exc).__name__}: {exc}")
            if not continue_on_failure:
                batch_status["finished_at"] = _utc_now()
                batch_status["elapsed_seconds"] = round(time.perf_counter() - started, 3)
                _write_json(status_path, status)
                break
        else:
            batch_status["status"] = "success"
        batch_status["finished_at"] = _utc_now()
        batch_status["elapsed_seconds"] = round(time.perf_counter() - started, 3)
        _write_json(status_path, status)

    status["finished_at"] = _utc_now()
    status["return_code"] = overall_return_code
    _write_json(status_path, status)
    return overall_return_code


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rerun terrain-derived outputs for batches.")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--out-root", default=Path("data/interim/batches"), type=Path)
    parser.add_argument("--preview-root", default=Path("data/exports/previews"), type=Path)
    parser.add_argument(
        "--logs-dir",
        default=Path("data/interim/batch_logs/water_fix_rerun"),
        type=Path,
    )
    parser.add_argument("--start", default=0, type=int)
    parser.add_argument("--end-exclusive", type=int)
    parser.add_argument("--exclude", nargs="*", default=[], type=int)
    parser.add_argument("--max-maps", default=250, type=int)
    parser.add_argument("--continue-on-failure", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return rerun_batches(
        manifest_path=args.manifest,
        out_root=args.out_root,
        preview_root=args.preview_root,
        logs_dir=args.logs_dir,
        start=args.start,
        end_exclusive=args.end_exclusive,
        exclude=set(args.exclude),
        max_maps=args.max_maps,
        continue_on_failure=args.continue_on_failure,
    )


if __name__ == "__main__":
    raise SystemExit(main())
