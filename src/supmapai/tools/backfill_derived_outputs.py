"""Backfill V1 derived outputs from completed terrain/entity batch files."""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from supmapai.extract import features_v1, resource_balance, structure_metrics, team_layout


def _set_csv_field_limit() -> None:
    limit = sys.maxsize
    while True:
        try:
            csv.field_size_limit(limit)
            return
        except OverflowError:
            limit //= 10


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


def _chunk_inventory_path(chunk: dict[str, Any], manifest_path: Path) -> Path:
    return manifest_path.parent / str(chunk["inventory_path"])


def _csv_data_row_count(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        try:
            next(reader)
        except StopIteration:
            return 0
        return sum(1 for _ in reader)


def _paths(out_dir: Path, batch_name: str) -> dict[str, Path]:
    return {
        "metadata": out_dir / f"{batch_name}_metadata.csv",
        "lua_entities": out_dir / f"{batch_name}_lua_entities.jsonl",
        "terrain": out_dir / f"{batch_name}_terrain.csv",
        "scmap_props_summary": out_dir / f"{batch_name}_scmap_props_summary.csv",
        "name_families": out_dir / f"{batch_name}_name_families.csv",
        "markers": out_dir / f"{batch_name}_markers.csv",
        "entities": out_dir / f"{batch_name}_entities.csv",
        "entities_summary": out_dir / f"{batch_name}_entities_summary.csv",
        "resource_balance": out_dir / f"{batch_name}_resource_balance.csv",
        "resource_balance_summary": out_dir / f"{batch_name}_resource_balance_summary.json",
        "team_layout": out_dir / f"{batch_name}_team_layout.csv",
        "team_layout_summary": out_dir / f"{batch_name}_team_layout_summary.json",
        "structure_metrics": out_dir / f"{batch_name}_structure_metrics.csv",
        "features": out_dir / f"{batch_name}_map_features_v1.csv",
        "survey_seed": out_dir / f"{batch_name}_maps.generated.json",
    }


def _require_prior_outputs(paths: dict[str, Path]) -> None:
    for key in (
        "metadata",
        "lua_entities",
        "terrain",
        "scmap_props_summary",
        "name_families",
        "markers",
        "entities",
        "entities_summary",
    ):
        if not paths[key].exists():
            raise FileNotFoundError(f"Missing required prior output: {paths[key]}")


def _outputs_complete(paths: dict[str, Path], map_count: int, include_structure: bool) -> bool:
    expected = [
        "resource_balance",
        "team_layout",
        "features",
    ]
    if include_structure:
        expected.append("structure_metrics")
    return all(_csv_data_row_count(paths[key]) == map_count for key in expected)


def _write_features(
    paths: dict[str, Path],
    include_team_layout: bool,
    include_structure: bool,
) -> None:
    feature_rows = features_v1.build_features(
        metadata_rows=features_v1._read_csv(paths["metadata"]),
        entities_by_map=features_v1._read_jsonl_by_map(paths["lua_entities"]),
        family_by_map=features_v1._name_families_by_map(paths["name_families"]),
        terrain_by_map=features_v1._csv_by_map(paths["terrain"]),
        scmap_props_by_map=features_v1._csv_by_map(paths["scmap_props_summary"]),
        team_layout_by_map=features_v1._csv_by_map(paths["team_layout"])
        if include_team_layout
        else {},
        structure_metrics_by_map=features_v1._csv_by_map(paths["structure_metrics"])
        if include_structure
        else {},
    )
    features_v1.write_features(feature_rows, paths["features"])
    features_v1.write_survey_seed(feature_rows, paths["survey_seed"])


def backfill_batch(
    inventory_path: Path,
    out_dir: Path,
    batch_name: str,
    max_maps: int,
    analysis_max_size: int,
    include_structure: bool,
    log_path: Path,
) -> None:
    started = time.perf_counter()
    inventory = json.loads(inventory_path.read_text(encoding="utf-8-sig"))
    map_count = int(inventory.get("map_count", len(inventory.get("maps", []))))
    if map_count > max_maps:
        raise ValueError(f"Refusing to run {map_count} maps with --max-maps {max_maps}")

    paths = _paths(out_dir, batch_name)
    _require_prior_outputs(paths)

    _append_log(log_path, f"[{batch_name}] preliminary features start")
    _write_features(paths, include_team_layout=False, include_structure=False)
    _append_log(
        log_path,
        f"[{batch_name}] preliminary features done at {time.perf_counter() - started:.1f}s",
    )

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
    _append_log(log_path, f"[{batch_name}] resource balance done")

    team_rows = team_layout.infer_team_layout_rows(
        markers_csv=paths["markers"],
        resource_balance_csv=paths["resource_balance"],
    )
    team_layout.write_csv(team_rows, paths["team_layout"])
    team_layout.write_summary(team_rows, paths["team_layout_summary"])
    _append_log(log_path, f"[{batch_name}] team layout done")

    if include_structure:
        structure_rows = structure_metrics.build_structure_rows(
            inventory=inventory,
            terrain_csv=paths["terrain"],
            markers_csv=paths["markers"],
            entities_csv=paths["entities"],
            team_layout_csv=paths["team_layout"],
            max_maps=max_maps,
            analysis_max_size=analysis_max_size,
        )
        structure_metrics.write_csv(structure_rows, paths["structure_metrics"])
        _append_log(log_path, f"[{batch_name}] structure metrics done")

    _write_features(
        paths,
        include_team_layout=True,
        include_structure=include_structure,
    )
    _append_log(
        log_path,
        f"[{batch_name}] final features done at {time.perf_counter() - started:.1f}s",
    )


def backfill_batches(
    manifest_path: Path,
    out_root: Path,
    logs_dir: Path,
    start: int,
    end_exclusive: int | None,
    exclude: set[int],
    max_maps: int,
    analysis_max_size: int,
    include_structure: bool,
    force: bool,
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
    status_path = logs_dir / "derived_backfill_status.json"
    status: dict[str, Any] = {
        "started_at": _utc_now(),
        "finished_at": None,
        "manifest_path": str(manifest_path),
        "selected_batch_count": len(chunks),
        "include_structure": include_structure,
        "analysis_max_size": analysis_max_size,
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
        paths = _paths(out_dir, batch_name)
        map_count = int(chunk["map_count"])
        log_path = logs_dir / f"{batch_name}_derived_backfill.log"
        started = time.perf_counter()
        batch_status: dict[str, Any] = {
            "batch_name": batch_name,
            "chunk_index": index,
            "map_count": map_count,
            "started_at": _utc_now(),
            "finished_at": None,
            "elapsed_seconds": None,
            "status": "running",
            "log_path": str(log_path),
        }
        status["batches"].append(batch_status)
        _write_json(status_path, status)

        if not force and _outputs_complete(paths, map_count, include_structure):
            batch_status["status"] = "skipped_complete"
            batch_status["finished_at"] = _utc_now()
            batch_status["elapsed_seconds"] = round(time.perf_counter() - started, 3)
            _write_json(status_path, status)
            continue

        try:
            backfill_batch(
                inventory_path=_chunk_inventory_path(chunk, manifest_path),
                out_dir=out_dir,
                batch_name=batch_name,
                max_maps=max_maps,
                analysis_max_size=analysis_max_size,
                include_structure=include_structure,
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
    parser = argparse.ArgumentParser(description="Backfill derived V1 outputs for batches.")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--out-root", default=Path("data/interim/batches"), type=Path)
    parser.add_argument(
        "--logs-dir",
        default=Path("data/interim/batch_logs/derived_backfill"),
        type=Path,
    )
    parser.add_argument("--start", default=0, type=int)
    parser.add_argument("--end-exclusive", type=int)
    parser.add_argument("--exclude", nargs="*", default=[], type=int)
    parser.add_argument("--max-maps", default=250, type=int)
    parser.add_argument("--analysis-max-size", default=256, type=int)
    parser.add_argument("--skip-structure", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--continue-on-failure", action="store_true")
    return parser.parse_args()


def main() -> int:
    _set_csv_field_limit()
    args = parse_args()
    return backfill_batches(
        manifest_path=args.manifest,
        out_root=args.out_root,
        logs_dir=args.logs_dir,
        start=args.start,
        end_exclusive=args.end_exclusive,
        exclude=set(args.exclude),
        max_maps=args.max_maps,
        analysis_max_size=args.analysis_max_size,
        include_structure=not args.skip_structure,
        force=args.force,
        continue_on_failure=args.continue_on_failure,
    )


if __name__ == "__main__":
    raise SystemExit(main())
