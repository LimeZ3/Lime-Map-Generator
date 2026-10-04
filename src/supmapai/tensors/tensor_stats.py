"""Compute per-channel statistics for exported tensor manifests."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

import numpy as np

STATS_COLUMNS = [
    "channel",
    "count",
    "min",
    "max",
    "mean",
    "std",
    "zero_fraction",
    "nonzero_fraction",
]


def _read_manifest(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [row for row in csv.DictReader(handle) if row.get("tensor_path")]


def _init_accumulators(channel_count: int) -> dict[str, np.ndarray]:
    return {
        "count": np.zeros(channel_count, dtype=np.float64),
        "sum": np.zeros(channel_count, dtype=np.float64),
        "sum_sq": np.zeros(channel_count, dtype=np.float64),
        "min": np.full(channel_count, np.inf, dtype=np.float64),
        "max": np.full(channel_count, -np.inf, dtype=np.float64),
        "zero": np.zeros(channel_count, dtype=np.float64),
    }


def _update(acc: dict[str, np.ndarray], tensor: np.ndarray) -> None:
    flat = tensor.reshape(tensor.shape[0], -1).astype(np.float64)
    acc["count"] += flat.shape[1]
    acc["sum"] += flat.sum(axis=1)
    acc["sum_sq"] += (flat * flat).sum(axis=1)
    acc["min"] = np.minimum(acc["min"], flat.min(axis=1))
    acc["max"] = np.maximum(acc["max"], flat.max(axis=1))
    acc["zero"] += np.count_nonzero(flat == 0, axis=1)


def compute_stats(
    manifest: Path,
    max_maps: int | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = _read_manifest(manifest)
    if max_maps is not None:
        rows = rows[:max_maps]
    channels: list[str] | None = None
    acc: dict[str, np.ndarray] | None = None
    failures = []
    loaded = 0
    for row in rows:
        try:
            archive = np.load(row["tensor_path"])
            tensor = archive["tensor"]
            tensor_channels = [str(item) for item in archive["channels"]]
        except Exception as exc:
            failures.append(
                {
                    "tensor_path": row.get("tensor_path", ""),
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            continue
        if channels is None:
            channels = tensor_channels
            acc = _init_accumulators(len(channels))
        if tensor_channels != channels:
            failures.append(
                {
                    "tensor_path": row.get("tensor_path", ""),
                    "error": "channel_order_mismatch",
                }
            )
            continue
        assert acc is not None
        _update(acc, tensor)
        loaded += 1

    if channels is None or acc is None:
        return [], {"manifest": str(manifest), "loaded_count": 0, "failures": failures}

    stat_rows = []
    for index, channel in enumerate(channels):
        count = max(acc["count"][index], 1)
        mean = acc["sum"][index] / count
        variance = max(acc["sum_sq"][index] / count - mean * mean, 0.0)
        zero_fraction = acc["zero"][index] / count
        stat_rows.append(
            {
                "channel": channel,
                "count": int(acc["count"][index]),
                "min": round(float(acc["min"][index]), 8),
                "max": round(float(acc["max"][index]), 8),
                "mean": round(float(mean), 8),
                "std": round(float(np.sqrt(variance)), 8),
                "zero_fraction": round(float(zero_fraction), 8),
                "nonzero_fraction": round(float(1.0 - zero_fraction), 8),
            }
        )
    summary = {
        "manifest": str(manifest),
        "manifest_row_count": len(rows),
        "loaded_count": loaded,
        "failure_count": len(failures),
        "failures": failures[:100],
        "channels": channels,
    }
    return stat_rows, summary


def write_outputs(
    rows: list[dict[str, Any]],
    summary: dict[str, Any],
    out: Path,
    summary_out: Path,
) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=STATS_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    summary_out.parent.mkdir(parents=True, exist_ok=True)
    summary_out.write_text(json.dumps(summary, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compute per-channel tensor statistics.")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--summary-out", required=True, type=Path)
    parser.add_argument("--max-maps", type=int)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows, summary = compute_stats(args.manifest, args.max_maps)
    write_outputs(rows, summary, args.out, args.summary_out)
    print(f"Wrote tensor stats for {len(rows)} channel(s) to {args.out}")
    if summary["failure_count"]:
        print(f"Tensor stat failures: {summary['failure_count']}")
    return 1 if summary["failure_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
