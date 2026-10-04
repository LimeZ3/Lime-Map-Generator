"""Run the V1 processing pipeline across chunked inventory batches."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

EXPECTED_PREVIEWS_PER_MAP = 5


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


def _png_count(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for item in path.glob("*.png") if item.is_file())


def _batch_name(chunk_index: int) -> str:
    return f"batch_{chunk_index:04d}"


def _batch_complete(out_dir: Path, preview_dir: Path, batch_name: str, map_count: int) -> bool:
    expected_csvs = [
        out_dir / f"{batch_name}_terrain.csv",
        out_dir / f"{batch_name}_scmap_props_summary.csv",
        out_dir / f"{batch_name}_entities_summary.csv",
        out_dir / f"{batch_name}_map_features_v1.csv",
        out_dir / f"{batch_name}_resource_balance.csv",
        out_dir / f"{batch_name}_team_layout.csv",
        out_dir / f"{batch_name}_structure_metrics.csv",
    ]
    if any(_csv_data_row_count(path) != map_count for path in expected_csvs):
        return False

    return _png_count(preview_dir) >= map_count * EXPECTED_PREVIEWS_PER_MAP


def _write_status(path: Path, status: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(status, indent=2), encoding="utf-8")


def _resolve_inventory_path(
    manifest_path: Path,
    chunk: dict[str, Any],
    inventory_dir: Path | None,
) -> Path:
    base_dir = inventory_dir if inventory_dir is not None else manifest_path.parent
    return base_dir / str(chunk["inventory_path"])


def _run_one_batch(
    inventory_path: Path,
    out_dir: Path,
    preview_dir: Path,
    log_path: Path,
    batch_name: str,
    max_maps: int,
) -> int:
    command = [
        sys.executable,
        "-m",
        "supmapai.tools.run_v1_batch",
        "--inventory",
        str(inventory_path),
        "--out-dir",
        str(out_dir),
        "--preview-dir",
        str(preview_dir),
        "--batch-name",
        batch_name,
        "--max-maps",
        str(max_maps),
    ]

    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as log_file:
        log_file.write(f"started_at={_utc_now()}\n")
        log_file.write(f"command={' '.join(command)}\n\n")
        log_file.flush()

        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert process.stdout is not None
        for line in process.stdout:
            print(line, end="", flush=True)
            log_file.write(line)
            log_file.flush()

        return_code = process.wait()
        log_file.write(f"\nfinished_at={_utc_now()}\n")
        log_file.write(f"return_code={return_code}\n")
        return return_code


def run_batches(
    manifest_path: Path,
    inventory_dir: Path | None,
    out_root: Path,
    preview_root: Path,
    logs_dir: Path,
    start: int,
    end_exclusive: int | None,
    max_maps: int,
    force: bool,
    stop_on_failure: bool,
) -> int:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    chunks = manifest.get("chunks", [])
    selected = [
        chunk
        for chunk in chunks
        if int(chunk["chunk_index"]) >= start
        and (end_exclusive is None or int(chunk["chunk_index"]) < end_exclusive)
    ]

    run_status_path = logs_dir / "run_status.json"
    status: dict[str, Any] = {
        "started_at": _utc_now(),
        "finished_at": None,
        "manifest_path": str(manifest_path),
        "out_root": str(out_root),
        "preview_root": str(preview_root),
        "logs_dir": str(logs_dir),
        "selected_batch_count": len(selected),
        "batches": [],
    }
    _write_status(run_status_path, status)

    overall_return_code = 0
    for chunk in selected:
        chunk_index = int(chunk["chunk_index"])
        map_count = int(chunk["map_count"])
        batch_name = _batch_name(chunk_index)
        inventory_path = _resolve_inventory_path(manifest_path, chunk, inventory_dir)
        out_dir = out_root / batch_name
        preview_dir = preview_root / batch_name
        log_path = logs_dir / f"{batch_name}.log"
        started = time.perf_counter()

        batch_status: dict[str, Any] = {
            "batch_name": batch_name,
            "chunk_index": chunk_index,
            "map_count": map_count,
            "inventory_path": str(inventory_path),
            "out_dir": str(out_dir),
            "preview_dir": str(preview_dir),
            "log_path": str(log_path),
            "started_at": _utc_now(),
            "finished_at": None,
            "elapsed_seconds": None,
            "status": "running",
            "return_code": None,
        }
        status["batches"].append(batch_status)
        _write_status(run_status_path, status)

        if not force and _batch_complete(out_dir, preview_dir, batch_name, map_count):
            batch_status["status"] = "skipped_complete"
            batch_status["finished_at"] = _utc_now()
            batch_status["elapsed_seconds"] = round(time.perf_counter() - started, 3)
            print(f"[{batch_name}] skipped: existing outputs look complete", flush=True)
            _write_status(run_status_path, status)
            continue

        print(f"[{batch_name}] starting {map_count} map(s)", flush=True)
        return_code = _run_one_batch(
            inventory_path=inventory_path,
            out_dir=out_dir,
            preview_dir=preview_dir,
            log_path=log_path,
            batch_name=batch_name,
            max_maps=max_maps,
        )

        batch_status["return_code"] = return_code
        batch_status["finished_at"] = _utc_now()
        batch_status["elapsed_seconds"] = round(time.perf_counter() - started, 3)

        if return_code == 0 and _batch_complete(out_dir, preview_dir, batch_name, map_count):
            batch_status["status"] = "success"
            print(f"[{batch_name}] success", flush=True)
        else:
            batch_status["status"] = "failed"
            overall_return_code = return_code or 1
            print(f"[{batch_name}] failed; see {log_path}", flush=True)
            _write_status(run_status_path, status)
            if stop_on_failure:
                break

        _write_status(run_status_path, status)

    status["finished_at"] = _utc_now()
    status["return_code"] = overall_return_code
    _write_status(run_status_path, status)
    print(f"Batch run status written to {run_status_path}", flush=True)
    return overall_return_code


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run V1 processing for chunked inventories.")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--inventory-dir", type=Path)
    parser.add_argument("--out-root", default=Path("data/interim/batches"), type=Path)
    parser.add_argument("--preview-root", default=Path("data/exports/previews"), type=Path)
    parser.add_argument("--logs-dir", default=Path("data/interim/batch_logs"), type=Path)
    parser.add_argument("--start", default=0, type=int, help="First batch index to consider.")
    parser.add_argument(
        "--end-exclusive",
        type=int,
        help="Stop before this batch index. Omit to run through the manifest end.",
    )
    parser.add_argument("--max-maps", default=250, type=int)
    parser.add_argument("--force", action="store_true", help="Rerun batches even if complete.")
    parser.add_argument(
        "--continue-on-failure",
        action="store_true",
        help="Keep processing later batches after a hard failure.",
    )
    return parser.parse_args()


def main() -> int:
    _set_csv_field_limit()
    args = parse_args()
    return run_batches(
        manifest_path=args.manifest,
        inventory_dir=args.inventory_dir,
        out_root=args.out_root,
        preview_root=args.preview_root,
        logs_dir=args.logs_dir,
        start=args.start,
        end_exclusive=args.end_exclusive,
        max_maps=args.max_maps,
        force=args.force,
        stop_on_failure=not args.continue_on_failure,
    )


if __name__ == "__main__":
    raise SystemExit(main())
