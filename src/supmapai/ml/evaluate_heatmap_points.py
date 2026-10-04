"""Evaluate decoded spawn/mex/hydro heatmap predictions against target points."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from supmapai.ml.decode_heatmap_points import DEFAULT_COUNTS, _local_maxima

POINT_LAYERS = ("spawn_heatmap", "mex_heatmap", "hydro_heatmap")
COUNT_COLUMNS = {
    "spawn_heatmap": "spawn_count",
    "mex_heatmap": "mex_count",
    "hydro_heatmap": "hydro_count",
}


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _load_count_lookup(tensor_manifest: Path | None) -> dict[str, dict[str, int]]:
    if tensor_manifest is None:
        return {}
    lookup: dict[str, dict[str, int]] = {}
    for row in _read_csv(tensor_manifest):
        map_id = row.get("map_id", "")
        if not map_id:
            continue
        counts = {}
        for layer, column in COUNT_COLUMNS.items():
            raw_value = row.get(column, "")
            try:
                counts[layer] = int(float(raw_value))
            except ValueError:
                counts[layer] = DEFAULT_COUNTS[layer]
        lookup[map_id] = counts
    return lookup


def _scalar_string(value: Any) -> str:
    if isinstance(value, np.ndarray):
        return str(value.tolist())
    return str(value)


def _decode_array(
    tensor: np.ndarray,
    channels: list[str],
    counts: dict[str, int],
    min_distance: int,
    threshold: float,
) -> dict[str, list[dict[str, Any]]]:
    decoded: dict[str, list[dict[str, Any]]] = {}
    for layer in POINT_LAYERS:
        if layer not in channels:
            continue
        count = counts.get(layer, DEFAULT_COUNTS[layer])
        index = channels.index(layer)
        decoded[layer] = _local_maxima(
            tensor[index],
            count=count,
            min_distance=min_distance,
            threshold=threshold,
        )
    return decoded


def _distance(a: dict[str, Any], b: dict[str, Any]) -> float:
    return math.dist((float(a["x"]), float(a["y"])), (float(b["x"]), float(b["y"])))


def _match_points(
    target: list[dict[str, Any]],
    predicted: list[dict[str, Any]],
    match_radius: float,
) -> dict[str, Any]:
    remaining = set(range(len(predicted)))
    distances = []
    for target_point in target:
        best_index = None
        best_distance = match_radius + 1.0
        for pred_index in remaining:
            distance = _distance(target_point, predicted[pred_index])
            if distance <= match_radius and distance < best_distance:
                best_index = pred_index
                best_distance = distance
        if best_index is not None:
            remaining.remove(best_index)
            distances.append(best_distance)

    matched = len(distances)
    precision = matched / len(predicted) if predicted else 0.0
    recall = matched / len(target) if target else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "target_count": len(target),
        "predicted_count": len(predicted),
        "matched_count": matched,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "mean_match_distance": float(np.mean(distances)) if distances else None,
        "median_match_distance": float(np.median(distances)) if distances else None,
    }


def evaluate_prediction_file(
    prediction_path: Path,
    count_lookup: dict[str, dict[str, int]],
    default_counts: dict[str, int],
    min_distance: int,
    target_threshold: float,
    prediction_threshold: float,
    match_radius: float,
) -> list[dict[str, Any]]:
    archive = np.load(prediction_path)
    target = archive["original"].astype(np.float32)
    prediction = archive["reconstruction"].astype(np.float32)
    channels = (
        [str(item) for item in archive["channels"]]
        if "channels" in archive.files
        else [f"channel_{index:02d}" for index in range(target.shape[0])]
    )
    map_id = (
        _scalar_string(archive["map_id"])
        if "map_id" in archive.files
        else prediction_path.stem
    )
    map_dir = _scalar_string(archive["map_dir"]) if "map_dir" in archive.files else ""
    counts = {**default_counts, **count_lookup.get(map_id, {})}
    target_points = _decode_array(target, channels, counts, min_distance, target_threshold)
    predicted_points = _decode_array(
        prediction,
        channels,
        counts,
        min_distance,
        prediction_threshold,
    )

    rows = []
    for layer in POINT_LAYERS:
        if layer not in target_points:
            continue
        metrics = _match_points(target_points[layer], predicted_points.get(layer, []), match_radius)
        rows.append(
            {
                "map_id": map_id,
                "map_dir": map_dir,
                "prediction_path": str(prediction_path),
                "layer": layer,
                **metrics,
            }
        )
    return rows


def _write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "map_id",
        "map_dir",
        "prediction_path",
        "layer",
        "target_count",
        "predicted_count",
        "matched_count",
        "precision",
        "recall",
        "f1",
        "mean_match_distance",
        "median_match_distance",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "map_count": len({row["map_id"] for row in rows}),
        "row_count": len(rows),
        "layers": {},
    }
    for layer in POINT_LAYERS:
        layer_rows = [row for row in rows if row["layer"] == layer]
        if not layer_rows:
            continue
        target_total = sum(int(row["target_count"]) for row in layer_rows)
        predicted_total = sum(int(row["predicted_count"]) for row in layer_rows)
        matched_total = sum(int(row["matched_count"]) for row in layer_rows)
        precision = matched_total / predicted_total if predicted_total else 0.0
        recall = matched_total / target_total if target_total else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        distances = [
            float(row["mean_match_distance"])
            for row in layer_rows
            if row["mean_match_distance"] is not None
        ]
        summary["layers"][layer] = {
            "map_count": len(layer_rows),
            "target_total": target_total,
            "predicted_total": predicted_total,
            "matched_total": matched_total,
            "precision": round(precision, 6),
            "recall": round(recall, 6),
            "f1": round(f1, 6),
            "mean_match_distance": round(float(np.mean(distances)), 6) if distances else None,
        }
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate decoded point heatmap predictions.")
    parser.add_argument("--predictions-dir", required=True, type=Path)
    parser.add_argument("--tensor-manifest", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--summary-out", required=True, type=Path)
    parser.add_argument("--max-items", type=int)
    parser.add_argument("--min-distance", default=8, type=int)
    parser.add_argument("--target-threshold", default=0.05, type=float)
    parser.add_argument("--prediction-threshold", default=0.05, type=float)
    parser.add_argument("--match-radius", default=10.0, type=float)
    parser.add_argument("--spawn-count", default=DEFAULT_COUNTS["spawn_heatmap"], type=int)
    parser.add_argument("--mex-count", default=DEFAULT_COUNTS["mex_heatmap"], type=int)
    parser.add_argument("--hydro-count", default=DEFAULT_COUNTS["hydro_heatmap"], type=int)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    prediction_paths = sorted(args.predictions_dir.glob("*.prediction.npz"))
    if args.max_items is not None:
        prediction_paths = prediction_paths[: args.max_items]
    count_lookup = _load_count_lookup(args.tensor_manifest)
    default_counts = {
        "spawn_heatmap": args.spawn_count,
        "mex_heatmap": args.mex_count,
        "hydro_heatmap": args.hydro_count,
    }
    rows: list[dict[str, Any]] = []
    for prediction_path in prediction_paths:
        rows.extend(
            evaluate_prediction_file(
                prediction_path=prediction_path,
                count_lookup=count_lookup,
                default_counts=default_counts,
                min_distance=args.min_distance,
                target_threshold=args.target_threshold,
                prediction_threshold=args.prediction_threshold,
                match_radius=args.match_radius,
            )
        )
    _write_rows(args.out, rows)
    summary = _summarize(rows)
    args.summary_out.parent.mkdir(parents=True, exist_ok=True)
    args.summary_out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Evaluated {len(prediction_paths)} prediction file(s)")
    print(f"Wrote point metrics to {args.out}")
    print(f"Wrote point summary to {args.summary_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
