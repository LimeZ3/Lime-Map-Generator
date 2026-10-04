"""Export V1 tensor files for all inventory batches."""

from __future__ import annotations

import argparse
import csv
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from supmapai.tensors import export_tensors


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _batch_name(index: int) -> str:
    return f"batch_{index:04d}"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _read_manifest_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_combined_manifest(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=export_tensors.MANIFEST_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def _chunk_inventory_path(manifest_path: Path, chunk: dict[str, Any]) -> Path:
    return manifest_path.parent / str(chunk["inventory_path"])


def _paths(out_root: Path, batch_name: str) -> dict[str, Path]:
    batch_dir = Path("data/interim/batches") / batch_name
    return {
        "features": batch_dir / f"{batch_name}_map_features_v1.csv",
        "markers": batch_dir / f"{batch_name}_markers.csv",
        "entities": batch_dir / f"{batch_name}_entities.csv",
        "tensor_dir": out_root / batch_name,
        "manifest": out_root / f"{batch_name}_tensor_manifest.csv",
    }


def export_batches(
    batch_manifest_path: Path,
    audit_maps: Path,
    out_root: Path,
    combined_manifest: Path,
    logs_dir: Path,
    start: int,
    end_exclusive: int | None,
    max_maps_per_batch: int,
    grid_size: int,
    statuses: set[str],
    force: bool,
    continue_on_failure: bool,
) -> int:
    batch_manifest = json.loads(batch_manifest_path.read_text(encoding="utf-8-sig"))
    chunks = [
        chunk
        for chunk in batch_manifest.get("chunks", [])
        if int(chunk["chunk_index"]) >= start
        and (end_exclusive is None or int(chunk["chunk_index"]) < end_exclusive)
    ]
    status_path = logs_dir / "tensor_export_status.json"
    status: dict[str, Any] = {
        "started_at": _utc_now(),
        "finished_at": None,
        "batch_manifest_path": str(batch_manifest_path),
        "audit_maps": str(audit_maps),
        "out_root": str(out_root),
        "combined_manifest": str(combined_manifest),
        "grid_size": grid_size,
        "statuses": sorted(statuses),
        "selected_batch_count": len(chunks),
        "batches": [],
        "return_code": None,
    }
    _write_json(status_path, status)

    all_rows: list[dict[str, Any]] = []
    overall_return_code = 0
    for chunk in chunks:
        index = int(chunk["chunk_index"])
        batch_name = _batch_name(index)
        paths = _paths(out_root, batch_name)
        started = time.perf_counter()
        batch_status: dict[str, Any] = {
            "batch_name": batch_name,
            "chunk_index": index,
            "started_at": _utc_now(),
            "finished_at": None,
            "elapsed_seconds": None,
            "status": "running",
            "manifest": str(paths["manifest"]),
            "exported_count": None,
            "failure_count": None,
        }
        status["batches"].append(batch_status)
        _write_json(status_path, status)

        existing_rows = _read_manifest_rows(paths["manifest"])
        if existing_rows and not force:
            all_rows.extend(existing_rows)
            batch_status["status"] = "skipped_complete"
            batch_status["exported_count"] = len(existing_rows)
            batch_status["failure_count"] = sum(1 for row in existing_rows if row.get("warnings"))
            batch_status["finished_at"] = _utc_now()
            batch_status["elapsed_seconds"] = round(time.perf_counter() - started, 3)
            _write_json(status_path, status)
            continue

        try:
            inventory = json.loads(
                _chunk_inventory_path(batch_manifest_path, chunk).read_text(encoding="utf-8-sig")
            )
            rows = export_tensors.export_tensors(
                inventory=inventory,
                features_csv=paths["features"],
                markers_csv=paths["markers"],
                entities_csv=paths["entities"],
                audit_maps_csv=audit_maps,
                out_dir=paths["tensor_dir"],
                manifest_out=paths["manifest"],
                grid_size=grid_size,
                max_maps=max_maps_per_batch,
                audit_status_filter=statuses,
            )
        except Exception as exc:
            batch_status["status"] = "failed"
            batch_status["error"] = f"{type(exc).__name__}: {exc}"
            overall_return_code = 1
            if not continue_on_failure:
                batch_status["finished_at"] = _utc_now()
                batch_status["elapsed_seconds"] = round(time.perf_counter() - started, 3)
                _write_json(status_path, status)
                break
            rows = []
        else:
            batch_status["status"] = "success"

        all_rows.extend(rows)
        batch_status["exported_count"] = len(rows)
        batch_status["failure_count"] = sum(1 for row in rows if row.get("warnings"))
        batch_status["finished_at"] = _utc_now()
        batch_status["elapsed_seconds"] = round(time.perf_counter() - started, 3)
        _write_json(status_path, status)

    _write_combined_manifest(combined_manifest, all_rows)
    status["finished_at"] = _utc_now()
    status["return_code"] = overall_return_code
    status["combined_row_count"] = len(all_rows)
    _write_json(status_path, status)
    return overall_return_code


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export V1 tensors for batch manifests.")
    parser.add_argument("--batch-manifest", required=True, type=Path)
    parser.add_argument("--audit-maps", required=True, type=Path)
    parser.add_argument("--out-root", default=Path("data/tensors/v1"), type=Path)
    parser.add_argument(
        "--combined-manifest",
        default=Path("data/tensors/v1/tensor_manifest.csv"),
        type=Path,
    )
    parser.add_argument("--logs-dir", default=Path("data/tensors/v1/logs"), type=Path)
    parser.add_argument("--start", default=0, type=int)
    parser.add_argument("--end-exclusive", type=int)
    parser.add_argument("--max-maps-per-batch", default=250, type=int)
    parser.add_argument("--grid-size", default=256, type=int)
    parser.add_argument("--status", action="append", help="Audit status to export.")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--continue-on-failure", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return export_batches(
        batch_manifest_path=args.batch_manifest,
        audit_maps=args.audit_maps,
        out_root=args.out_root,
        combined_manifest=args.combined_manifest,
        logs_dir=args.logs_dir,
        start=args.start,
        end_exclusive=args.end_exclusive,
        max_maps_per_batch=args.max_maps_per_batch,
        grid_size=args.grid_size,
        statuses=set(args.status or ["ready", "review"]),
        force=args.force,
        continue_on_failure=args.continue_on_failure,
    )


if __name__ == "__main__":
    raise SystemExit(main())
