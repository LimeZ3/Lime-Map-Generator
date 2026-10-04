"""Audit completed V1 batch outputs for dataset readiness and outliers."""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

MAP_AUDIT_COLUMNS = [
    "batch_name",
    "map_dir",
    "map_id",
    "scenario_name",
    "map_version",
    "size_class",
    "player_slots",
    "spawn_count",
    "mex_count",
    "hydro_count",
    "duplicate_family_key",
    "candidate_count",
    "backup_candidate_count",
    "source_quality",
    "audit_status",
    "issue_count",
    "issues",
    "outlier_count",
    "outlier_fields",
    "predicted_team_setting",
    "symmetry_label",
    "symmetry_score",
    "water_percent",
    "buildable_percent",
    "pathblocking_steep_percent",
    "land_unit_passable_percent",
    "total_reclaim_entity_count",
    "civilian_building_count",
    "texture_pack",
]

OUTLIER_COLUMNS = [
    "batch_name",
    "map_dir",
    "field",
    "value",
    "median",
    "mad",
    "robust_z",
    "reason",
]

WARNING_COLUMNS = ["token", "count"]

FAMILY_COLUMNS = [
    "family_key",
    "family_size",
    "ready_count",
    "review_count",
    "exclude_candidate_count",
    "candidate_maps_json",
]

NUMERIC_OUTLIER_FIELDS = [
    "water_percent",
    "buildable_percent",
    "pathblocking_steep_percent",
    "land_unit_passable_percent",
    "mex_per_player",
    "hydro_per_player",
    "total_reclaim_entity_count",
    "civilian_building_count",
    "scmap_prop_count",
    "tree_prop_count",
    "rock_prop_count",
    "boulder_prop_count",
    "predicted_team_balance_score",
]

READINESS_OUTLIER_FIELDS = {
    "water_percent",
    "buildable_percent",
    "pathblocking_steep_percent",
    "land_unit_passable_percent",
    "mex_per_player",
    "hydro_per_player",
    "predicted_team_balance_score",
}

OPTIONAL_STAGE_SUFFIXES = {
    "features": "_map_features_v1.csv",
    "terrain": "_terrain.csv",
    "markers": "_markers.csv",
    "entities": "_entities.csv",
    "resource_balance": "_resource_balance.csv",
    "team_layout": "_team_layout.csv",
    "structure_metrics": "_structure_metrics.csv",
}


def _read_csv(path: Path) -> list[dict[str, str]]:
    _set_csv_field_limit()
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _set_csv_field_limit() -> None:
    limit = sys.maxsize
    while True:
        try:
            csv.field_size_limit(limit)
            return
        except OverflowError:
            limit //= 10


def _write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def _float_or_none(value: Any) -> float | None:
    try:
        if value in ("", None):
            return None
        result = float(str(value))
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result):
        return None
    return result


def _int_or_zero(value: Any) -> int:
    numeric = _float_or_none(value)
    return int(numeric) if numeric is not None else 0


def _bool_text(value: str) -> bool | None:
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    return None


def _tokenize_warnings(*values: str) -> list[str]:
    tokens: list[str] = []
    for value in values:
        if not value:
            continue
        for token in re.split(r"[|;,]+", value):
            clean = token.strip()
            if clean:
                tokens.append(clean)
    return tokens


def _batch_name(path: Path) -> str:
    return path.name


def _stage_path(batch_dir: Path, batch_name: str, stage: str) -> Path:
    return batch_dir / f"{batch_name}{OPTIONAL_STAGE_SUFFIXES[stage]}"


def _discover_batches(batches_root: Path) -> list[Path]:
    if not batches_root.exists():
        return []
    return sorted(
        path
        for path in batches_root.iterdir()
        if path.is_dir() and path.name.startswith("batch_")
    )


def _read_feature_rows(batches_root: Path) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    rows: list[dict[str, str]] = []
    batch_statuses = []
    for batch_dir in _discover_batches(batches_root):
        batch_name = _batch_name(batch_dir)
        stage_paths = {
            stage: _stage_path(batch_dir, batch_name, stage)
            for stage in OPTIONAL_STAGE_SUFFIXES
        }
        present = {stage: path.exists() for stage, path in stage_paths.items()}
        feature_path = stage_paths["features"]
        map_count = 0
        if feature_path.exists():
            feature_rows = _read_csv(feature_path)
            map_count = len(feature_rows)
            for row in feature_rows:
                row["_batch_name"] = batch_name
            rows.extend(feature_rows)
        batch_statuses.append(
            {
                "batch_name": batch_name,
                "map_count": map_count,
                "present_stages": sorted(stage for stage, exists in present.items() if exists),
                "missing_stages": sorted(stage for stage, exists in present.items() if not exists),
            }
        )
    return rows, batch_statuses


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    count = len(ordered)
    middle = count // 2
    if count % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def _robust_stats(rows: list[dict[str, str]]) -> dict[str, dict[str, float]]:
    stats = {}
    for field in NUMERIC_OUTLIER_FIELDS:
        values = [
            value
            for row in rows
            if (value := _float_or_none(row.get(field))) is not None
        ]
        if len(values) < 20:
            continue
        median = _median(values)
        deviations = [abs(value - median) for value in values]
        mad = _median(deviations)
        if mad <= 0:
            nonzero = [value for value in deviations if value > 0]
            mad = min(nonzero) if nonzero else 0.0
        stats[field] = {"median": median, "mad": mad}
    return stats


def _hard_issues(row: dict[str, str]) -> list[str]:
    issues = []
    if row.get("source_quality") == "broken":
        issues.append("source_quality_broken")
    for field in ("has_scmap", "has_scenario_lua", "has_save_lua"):
        if _bool_text(row.get(field, "")) is False:
            issues.append(f"missing_{field.removeprefix('has_')}")
    if _int_or_zero(row.get("spawn_count")) <= 0:
        issues.append("zero_spawns")
    if _int_or_zero(row.get("mex_count")) <= 0:
        issues.append("zero_mexes")
    if _int_or_zero(row.get("player_slots")) and (
        _int_or_zero(row.get("player_slots")) != _int_or_zero(row.get("spawn_count"))
    ):
        issues.append("player_slots_mismatch_spawns")

    water_percent = _float_or_none(row.get("water_percent"))
    buildable_percent = _float_or_none(row.get("buildable_percent"))
    passable_percent = _float_or_none(row.get("land_unit_passable_percent"))
    steep_percent = _float_or_none(row.get("pathblocking_steep_percent"))
    if water_percent is not None and water_percent >= 98:
        issues.append("nearly_all_water")
    if buildable_percent is not None and buildable_percent <= 1:
        issues.append("almost_no_buildable_terrain")
    if passable_percent is not None and passable_percent <= 2:
        issues.append("almost_no_land_pathability")
    if steep_percent is not None and steep_percent >= 90:
        issues.append("mostly_pathblocking_steep")

    warnings = _tokenize_warnings(
        row.get("parse_warnings", ""),
        row.get("structure_warnings", ""),
    )
    for token in warnings:
        lowered = token.lower()
        if "failed" in lowered or lowered.startswith("missing_"):
            issues.append(f"warning:{token}")
    return sorted(set(issues))


def _outlier_rows(
    row: dict[str, str],
    stats: dict[str, dict[str, float]],
    robust_z_threshold: float,
) -> list[dict[str, Any]]:
    outliers = []
    for field, field_stats in stats.items():
        value = _float_or_none(row.get(field))
        if value is None:
            continue
        mad = field_stats["mad"]
        if mad <= 0:
            continue
        robust_z = 0.6745 * (value - field_stats["median"]) / mad
        if abs(robust_z) >= robust_z_threshold:
            outliers.append(
                {
                    "batch_name": row.get("_batch_name", ""),
                    "map_dir": row.get("top_level_dir", ""),
                    "field": field,
                    "value": round(value, 6),
                    "median": round(field_stats["median"], 6),
                    "mad": round(mad, 6),
                    "robust_z": round(robust_z, 6),
                    "reason": "robust_z_threshold",
                }
            )
    return outliers


def _audit_status(issues: list[str], outliers: list[dict[str, Any]]) -> str:
    exclude_tokens = {
        "source_quality_broken",
        "missing_scmap",
        "missing_scenario_lua",
        "missing_save_lua",
        "zero_spawns",
        "zero_mexes",
        "nearly_all_water",
        "almost_no_buildable_terrain",
        "almost_no_land_pathability",
    }
    if any(issue in exclude_tokens or issue.startswith("warning:") for issue in issues):
        return "exclude_candidate"
    readiness_outliers = [
        outlier for outlier in outliers if str(outlier.get("field")) in READINESS_OUTLIER_FIELDS
    ]
    if issues or readiness_outliers:
        return "review"
    return "ready"


def _audit_maps(
    feature_rows: list[dict[str, str]],
    robust_z_threshold: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], Counter[str]]:
    stats = _robust_stats(feature_rows)
    map_rows = []
    outlier_rows = []
    warning_counts: Counter[str] = Counter()
    for row in feature_rows:
        warnings = _tokenize_warnings(
            row.get("parse_warnings", ""),
            row.get("structure_warnings", ""),
            row.get("warnings", ""),
        )
        warning_counts.update(warnings)
        issues = _hard_issues(row)
        outliers = _outlier_rows(row, stats, robust_z_threshold)
        outlier_rows.extend(outliers)
        status = _audit_status(issues, outliers)
        map_rows.append(
            {
                "batch_name": row.get("_batch_name", ""),
                "map_dir": row.get("top_level_dir", ""),
                "map_id": row.get("map_id", ""),
                "scenario_name": row.get("scenario_name", ""),
                "map_version": row.get("map_version", ""),
                "size_class": row.get("size_class", ""),
                "player_slots": row.get("player_slots", ""),
                "spawn_count": row.get("spawn_count", ""),
                "mex_count": row.get("mex_count", ""),
                "hydro_count": row.get("hydro_count", ""),
                "duplicate_family_key": row.get("duplicate_family_key", ""),
                "candidate_count": row.get("candidate_count", ""),
                "backup_candidate_count": row.get("backup_candidate_count", ""),
                "source_quality": row.get("source_quality", ""),
                "audit_status": status,
                "issue_count": len(issues),
                "issues": "|".join(issues),
                "outlier_count": len(outliers),
                "outlier_fields": "|".join(sorted({str(item["field"]) for item in outliers})),
                "predicted_team_setting": row.get("predicted_team_setting", ""),
                "symmetry_label": row.get("symmetry_label", ""),
                "symmetry_score": row.get("symmetry_score", ""),
                "water_percent": row.get("water_percent", ""),
                "buildable_percent": row.get("buildable_percent", ""),
                "pathblocking_steep_percent": row.get("pathblocking_steep_percent", ""),
                "land_unit_passable_percent": row.get("land_unit_passable_percent", ""),
                "total_reclaim_entity_count": row.get("total_reclaim_entity_count", ""),
                "civilian_building_count": row.get("civilian_building_count", ""),
                "texture_pack": row.get("texture_pack", ""),
            }
        )
    return map_rows, outlier_rows, warning_counts


def _family_rows(map_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in map_rows:
        key = str(row.get("duplicate_family_key") or "")
        if key:
            grouped[key].append(row)

    rows = []
    for key, members in sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0])):
        if len(members) <= 1:
            continue
        status_counts = Counter(str(member["audit_status"]) for member in members)
        candidates = [
            {
                "map_dir": member["map_dir"],
                "status": member["audit_status"],
                "version": member.get("map_version", ""),
                "candidate_count": member.get("candidate_count", ""),
            }
            for member in members[:50]
        ]
        rows.append(
            {
                "family_key": key,
                "family_size": len(members),
                "ready_count": status_counts["ready"],
                "review_count": status_counts["review"],
                "exclude_candidate_count": status_counts["exclude_candidate"],
                "candidate_maps_json": json.dumps(candidates, sort_keys=True),
            }
        )
    return rows


def _summary(
    feature_rows: list[dict[str, str]],
    map_rows: list[dict[str, Any]],
    outlier_rows: list[dict[str, Any]],
    warning_counts: Counter[str],
    family_rows: list[dict[str, Any]],
    batch_statuses: list[dict[str, Any]],
) -> dict[str, Any]:
    status_counts = Counter(str(row["audit_status"]) for row in map_rows)
    size_counts = Counter(str(row.get("size_class") or "unknown") for row in map_rows)
    team_counts = Counter(str(row.get("predicted_team_setting") or "unknown") for row in map_rows)
    missing_stage_counts: Counter[str] = Counter()
    for status in batch_statuses:
        missing_stage_counts.update(status["missing_stages"])
    return {
        "map_count": len(feature_rows),
        "batch_count": len(batch_statuses),
        "audit_status_counts": dict(sorted(status_counts.items())),
        "size_class_counts": dict(sorted(size_counts.items())),
        "predicted_team_setting_counts": dict(team_counts.most_common(30)),
        "outlier_row_count": len(outlier_rows),
        "warning_token_counts": dict(warning_counts.most_common(50)),
        "duplicate_family_count": len(family_rows),
        "duplicate_family_map_count": sum(int(row["family_size"]) for row in family_rows),
        "missing_stage_counts": dict(sorted(missing_stage_counts.items())),
        "batches": batch_statuses,
    }


def run_audit(
    batches_root: Path,
    out_dir: Path,
    robust_z_threshold: float,
) -> dict[str, Any]:
    feature_rows, batch_statuses = _read_feature_rows(batches_root)
    map_rows, outlier_rows, warning_counts = _audit_maps(feature_rows, robust_z_threshold)
    family_rows = _family_rows(map_rows)
    summary = _summary(
        feature_rows,
        map_rows,
        outlier_rows,
        warning_counts,
        family_rows,
        batch_statuses,
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(out_dir / "dataset_audit_maps.csv", map_rows, MAP_AUDIT_COLUMNS)
    _write_csv(out_dir / "dataset_audit_outliers.csv", outlier_rows, OUTLIER_COLUMNS)
    _write_csv(
        out_dir / "dataset_audit_warnings.csv",
        [{"token": token, "count": count} for token, count in warning_counts.most_common()],
        WARNING_COLUMNS,
    )
    _write_csv(out_dir / "dataset_audit_families.csv", family_rows, FAMILY_COLUMNS)
    (out_dir / "dataset_audit_summary.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit completed V1 dataset batch outputs.")
    parser.add_argument("--batches-root", default=Path("data/interim/batches"), type=Path)
    parser.add_argument("--out-dir", default=Path("data/audit/v1"), type=Path)
    parser.add_argument("--robust-z-threshold", default=8.0, type=float)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary = run_audit(
        batches_root=args.batches_root,
        out_dir=args.out_dir,
        robust_z_threshold=args.robust_z_threshold,
    )
    print(
        "Audited "
        f"{summary['map_count']} map(s) across {summary['batch_count']} batch folder(s)."
    )
    print(f"Status counts: {summary['audit_status_counts']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
