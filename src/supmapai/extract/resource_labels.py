"""Derive robust density and fairness labels from resource balance metrics."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

LABEL_COLUMNS = [
    "map_dir",
    "spawn_count",
    "playable_area",
    "symmetry_label",
    "symmetry_detected",
    "mex_count",
    "mex_per_spawn",
    "mex_per_10k_area",
    "mex_per_spawn_label",
    "mex_per_area_label",
    "mex_density_label",
    "mex_assigned_spawn_fairness_score",
    "mex_fairness_label",
    "hydro_count",
    "hydro_per_spawn",
    "hydro_per_10k_area",
    "hydro_per_spawn_label",
    "hydro_per_area_label",
    "hydro_density_label",
    "hydro_assigned_spawn_fairness_score",
    "hydro_fairness_label",
    "reclaim_points_streamed",
    "reclaim_points_per_spawn",
    "reclaim_points_per_10k_area",
    "reclaim_per_spawn_label",
    "reclaim_per_area_label",
    "reclaim_density_label",
    "reclaim_assigned_spawn_fairness_score",
    "reclaim_fairness_label",
    "civilian_building_count",
    "civilian_buildings_per_spawn",
    "civilian_buildings_per_10k_area",
    "civilian_buildings_per_spawn_label",
    "civilian_buildings_per_area_label",
    "civilian_density_label",
    "overall_resource_fairness_score",
    "overall_resource_fairness_label",
    "warnings",
]

DENSITY_LABELS = ["very_few", "few", "normal", "more", "lots"]


def _set_csv_field_limit() -> None:
    limit = 2**31 - 1
    while True:
        try:
            csv.field_size_limit(limit)
            return
        except OverflowError:
            limit //= 10


def _float_or_none(value: Any) -> float | None:
    if value in ("", None):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _read_rows(paths: list[Path]) -> list[dict[str, str]]:
    rows = []
    for path in paths:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows.extend(csv.DictReader(handle))
    return rows


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    index = (len(values) - 1) * pct
    lower = int(index)
    upper = min(lower + 1, len(values) - 1)
    if lower == upper:
        return values[lower]
    return values[lower] + (values[upper] - values[lower]) * (index - lower)


def _thresholds(rows: list[dict[str, str]], column: str) -> list[float]:
    values = [
        value
        for row in rows
        if (value := _float_or_none(row.get(column))) is not None
    ]
    if len(values) < 5:
        return []
    low = _percentile(values, 0.025)
    high = _percentile(values, 0.975)
    trimmed = [value for value in values if low <= value <= high]
    if len(trimmed) < 5:
        trimmed = values
    return [_percentile(trimmed, pct) for pct in (0.2, 0.4, 0.6, 0.8)]


def _density_label(value: float | None, thresholds: list[float]) -> str:
    if value is None or not thresholds:
        return "unknown"
    for label, threshold in zip(DENSITY_LABELS, thresholds, strict=False):
        if value <= threshold:
            return label
    return DENSITY_LABELS[-1]


def _label_rank(label: str) -> int:
    if label not in DENSITY_LABELS:
        return -1
    return DENSITY_LABELS.index(label)


def _combined_density_label(left: str, right: str) -> str:
    ranks = [rank for label in (left, right) if (rank := _label_rank(label)) >= 0]
    if not ranks:
        return "unknown"
    return DENSITY_LABELS[round(sum(ranks) / len(ranks))]


def _fairness_label(score: float | None) -> str:
    if score is None:
        return "unknown"
    if score >= 0.85:
        return "balanced"
    if score >= 0.7:
        return "mildly_uneven"
    if score >= 0.45:
        return "uneven"
    return "severe_imbalance"


def build_resource_labels(
    rows: list[dict[str, str]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    density_columns = [
        "mex_per_spawn",
        "mex_per_10k_area",
        "hydro_per_spawn",
        "hydro_per_10k_area",
        "reclaim_points_per_spawn",
        "reclaim_points_per_10k_area",
        "civilian_buildings_per_spawn",
        "civilian_buildings_per_10k_area",
    ]
    thresholds = {column: _thresholds(rows, column) for column in density_columns}

    output = []
    for row in rows:
        clean = {column: "" for column in LABEL_COLUMNS}
        clean.update(
            {
                "map_dir": row.get("map_dir", ""),
                "spawn_count": row.get("spawn_count", ""),
                "playable_area": row.get("playable_area", ""),
                "symmetry_label": row.get("symmetry_label", ""),
                "symmetry_detected": row.get("symmetry_detected", ""),
                "mex_count": row.get("mex_count", ""),
                "mex_per_spawn": row.get("mex_per_spawn", ""),
                "mex_per_10k_area": row.get("mex_per_10k_area", ""),
                "hydro_count": row.get("hydro_count", ""),
                "hydro_per_spawn": row.get("hydro_per_spawn", ""),
                "hydro_per_10k_area": row.get("hydro_per_10k_area", ""),
                "reclaim_points_streamed": row.get("reclaim_points_streamed", ""),
                "reclaim_points_per_spawn": row.get("reclaim_points_per_spawn", ""),
                "reclaim_points_per_10k_area": row.get("reclaim_points_per_10k_area", ""),
                "civilian_building_count": row.get("civilian_building_count", ""),
                "civilian_buildings_per_spawn": row.get("civilian_buildings_per_spawn", ""),
                "civilian_buildings_per_10k_area": row.get(
                    "civilian_buildings_per_10k_area",
                    "",
                ),
                "warnings": row.get("warnings", ""),
            }
        )

        for density_prefix, count_prefix, spawn_label_column, area_label_column in (
            ("mex", "mex", "mex_per_spawn_label", "mex_per_area_label"),
            ("hydro", "hydro", "hydro_per_spawn_label", "hydro_per_area_label"),
            ("reclaim", "reclaim_points", "reclaim_per_spawn_label", "reclaim_per_area_label"),
            (
                "civilian",
                "civilian_buildings",
                "civilian_buildings_per_spawn_label",
                "civilian_buildings_per_area_label",
            ),
        ):
            spawn_column = f"{count_prefix}_per_spawn"
            area_column = f"{count_prefix}_per_10k_area"
            spawn_label = _density_label(
                _float_or_none(row.get(spawn_column)),
                thresholds[spawn_column],
            )
            area_label = _density_label(
                _float_or_none(row.get(area_column)),
                thresholds[area_column],
            )
            clean[spawn_label_column] = spawn_label
            clean[area_label_column] = area_label
            clean[f"{density_prefix}_density_label"] = _combined_density_label(
                spawn_label,
                area_label,
            )

        fairness_scores = []
        for prefix in ("mex", "hydro", "reclaim"):
            score = _float_or_none(row.get(f"{prefix}_assigned_spawn_fairness_score"))
            clean[f"{prefix}_assigned_spawn_fairness_score"] = (
                round(score, 6) if score is not None else ""
            )
            clean[f"{prefix}_fairness_label"] = _fairness_label(score)
            if score is not None:
                fairness_scores.append(score)
        overall_score = min(fairness_scores) if fairness_scores else None
        clean["overall_resource_fairness_score"] = (
            round(overall_score, 6) if overall_score is not None else ""
        )
        clean["overall_resource_fairness_label"] = _fairness_label(overall_score)
        output.append(clean)

    summary = {
        "row_count": len(output),
        "density_thresholds": {
            column: [round(value, 6) for value in column_thresholds]
            for column, column_thresholds in thresholds.items()
        },
    }
    return output, summary


def write_csv(rows: list[dict[str, Any]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=LABEL_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def write_summary(summary: dict[str, Any], rows: list[dict[str, Any]], out_path: Path) -> None:
    counts: dict[str, dict[str, int]] = {}
    for column in LABEL_COLUMNS:
        if not column.endswith("_label"):
            continue
        column_counts: dict[str, int] = {}
        for row in rows:
            label = str(row.get(column, ""))
            column_counts[label] = column_counts.get(label, 0) + 1
        counts[column] = dict(sorted(column_counts.items()))
    payload = {**summary, "label_counts": counts}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Derive robust resource density/fairness labels from resource balance CSVs."
    )
    parser.add_argument("--input", required=True, action="append", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--summary-out", type=Path)
    return parser.parse_args()


def main() -> int:
    _set_csv_field_limit()
    args = parse_args()
    rows, summary = build_resource_labels(_read_rows(args.input))
    write_csv(rows, args.out)
    if args.summary_out:
        write_summary(summary, rows, args.summary_out)
    print(f"Wrote {len(rows)} resource label row(s) to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
