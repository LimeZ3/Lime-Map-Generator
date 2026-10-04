"""Create a focused quality report for a tensor dataset subset."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


REPORT_COLUMNS = [
    "map_id",
    "map_dir",
    "split",
    "split_group_key",
    "audit_status",
    "size_class",
    "player_slots",
    "spawn_count",
    "mex_count",
    "hydro_count",
    "predicted_team_setting",
    "duplicate_family_key",
    "water_percent",
    "buildable_percent",
    "height_min",
    "height_max",
    "warnings",
    "tensor_path",
]

NUMERIC_FIELDS = [
    "player_slots",
    "spawn_count",
    "mex_count",
    "hydro_count",
    "water_percent",
    "buildable_percent",
    "height_min",
    "height_max",
]


def _read_csv(path: Path | None) -> list[dict[str, str]]:
    if path is None or not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _sha256(path: Path | None) -> str:
    if path is None or not path.exists():
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _float_or_none(value: Any) -> float | None:
    try:
        if value in ("", None):
            return None
        number = float(str(value))
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _stats(values: list[float]) -> dict[str, float | int | None]:
    values = sorted(value for value in values if math.isfinite(value))
    if not values:
        return {
            "count": 0,
            "min": None,
            "p05": None,
            "p25": None,
            "median": None,
            "mean": None,
            "p75": None,
            "p95": None,
            "max": None,
        }

    def percentile(percent: float) -> float:
        if len(values) == 1:
            return values[0]
        pos = (len(values) - 1) * percent
        lower = int(math.floor(pos))
        upper = int(math.ceil(pos))
        if lower == upper:
            return values[lower]
        return values[lower] * (upper - pos) + values[upper] * (pos - lower)

    return {
        "count": len(values),
        "min": round(values[0], 6),
        "p05": round(percentile(0.05), 6),
        "p25": round(percentile(0.25), 6),
        "median": round(percentile(0.50), 6),
        "mean": round(sum(values) / len(values), 6),
        "p75": round(percentile(0.75), 6),
        "p95": round(percentile(0.95), 6),
        "max": round(values[-1], 6),
    }


def _counter(rows: list[dict[str, Any]], key: str, limit: int | None = None) -> dict[str, int]:
    counter = Counter(str(row.get(key) or "unknown") for row in rows)
    items = counter.most_common(limit)
    return dict(items)


def _index_by(rows: list[dict[str, str]], key: str) -> dict[str, dict[str, str]]:
    return {row[key]: row for row in rows if row.get(key)}


def _join_rows(
    manifest_rows: list[dict[str, str]],
    split_rows: list[dict[str, str]],
    audit_rows: list[dict[str, str]],
) -> list[dict[str, Any]]:
    split_by_map_id = _index_by(split_rows, "map_id")
    split_by_map_dir = _index_by(split_rows, "map_dir")
    audit_by_map_dir = _index_by(audit_rows, "map_dir")
    joined = []
    for row in manifest_rows:
        split = split_by_map_id.get(row.get("map_id", "")) or split_by_map_dir.get(
            row.get("map_dir", "")
        )
        audit = audit_by_map_dir.get(row.get("map_dir", ""), {})
        joined_row: dict[str, Any] = {column: row.get(column, "") for column in REPORT_COLUMNS}
        if split:
            joined_row["split"] = split.get("split", "")
            joined_row["split_group_key"] = split.get("split_group_key", "")
            joined_row["duplicate_family_key"] = (
                row.get("duplicate_family_key")
                or split.get("duplicate_family_key")
                or audit.get("duplicate_family_key")
                or ""
            )
        joined_row["audit_status"] = row.get("audit_status") or audit.get("audit_status", "")
        joined.append(joined_row)
    return joined


def _family_split_audit(rows: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, set[str]] = defaultdict(set)
    examples: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        key = str(row.get("duplicate_family_key") or row.get("split_group_key") or "")
        if not key:
            continue
        split = str(row.get("split") or "missing")
        groups[key].add(split)
        if len(examples[key]) < 8:
            examples[key].append(str(row.get("map_dir") or row.get("map_id") or ""))
    leaks = [
        {
            "group_key": key,
            "splits": sorted(splits),
            "map_count": sum(1 for row in rows if (row.get("duplicate_family_key") or row.get("split_group_key")) == key),
            "examples": examples[key],
        }
        for key, splits in groups.items()
        if len(splits - {"missing"}) > 1 or ("missing" in splits and len(splits) > 1)
    ]
    leaks.sort(key=lambda item: (-int(item["map_count"]), item["group_key"]))
    return {
        "family_group_count": len(groups),
        "leak_count": len(leaks),
        "leaks": leaks[:50],
    }


def _outliers(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for field in ("water_percent", "buildable_percent", "mex_count", "hydro_count", "player_slots"):
        numeric_rows = []
        for row in rows:
            value = _float_or_none(row.get(field))
            if value is not None:
                numeric_rows.append((value, row))
        if not numeric_rows:
            result[field] = []
            continue
        values = [value for value, _row in numeric_rows]
        low = _stats(values)["p05"]
        high = _stats(values)["p95"]
        if low is None or high is None:
            result[field] = []
            continue
        candidates = [
            {
                "map_dir": row.get("map_dir", ""),
                "map_id": row.get("map_id", ""),
                "split": row.get("split", ""),
                field: round(value, 6),
            }
            for value, row in numeric_rows
            if value <= float(low) or value >= float(high)
        ]
        candidates.sort(key=lambda item: float(item[field]))
        result[field] = candidates[:10] + candidates[-10:]
    return result


def build_report(
    tensor_manifest: Path,
    splits_csv: Path | None,
    audit_maps_csv: Path | None,
    dataset_name: str,
) -> tuple[list[dict[str, Any]], dict[str, Any], str]:
    manifest_rows = _read_csv(tensor_manifest)
    split_rows = _read_csv(splits_csv)
    audit_rows = _read_csv(audit_maps_csv)
    rows = _join_rows(manifest_rows, split_rows, audit_rows)

    numeric = {
        field: _stats(
            [
                value
                for value in (_float_or_none(row.get(field)) for row in rows)
                if value is not None
            ]
        )
        for field in NUMERIC_FIELDS
    }
    split_audit = _family_split_audit(rows)
    missing_tensor_files = [
        row["tensor_path"]
        for row in rows
        if row.get("tensor_path") and not (Path(row["tensor_path"]).exists())
    ]
    summary = {
        "schema": "mapgen_dataset_quality_v1",
        "dataset_name": dataset_name,
        "created_utc": datetime.now(UTC).isoformat(),
        "inputs": {
            "tensor_manifest": str(tensor_manifest),
            "tensor_manifest_sha256": _sha256(tensor_manifest),
            "splits_csv": str(splits_csv) if splits_csv else "",
            "splits_csv_sha256": _sha256(splits_csv),
            "audit_maps_csv": str(audit_maps_csv) if audit_maps_csv else "",
            "audit_maps_csv_sha256": _sha256(audit_maps_csv),
        },
        "counts": {
            "map_count": len(rows),
            "missing_split_count": sum(1 for row in rows if not row.get("split")),
            "missing_tensor_file_count": len(missing_tensor_files),
        },
        "by_split": _counter(rows, "split"),
        "by_size_class": _counter(rows, "size_class"),
        "by_audit_status": _counter(rows, "audit_status"),
        "by_player_slots": _counter(rows, "player_slots"),
        "by_predicted_team_setting": _counter(rows, "predicted_team_setting", limit=50),
        "numeric": numeric,
        "family_split_audit": split_audit,
        "outliers": _outliers(rows),
        "missing_tensor_files": missing_tensor_files[:50],
    }
    markdown = _markdown(summary)
    return rows, summary, markdown


def _markdown(summary: dict[str, Any]) -> str:
    counts = summary["counts"]
    family = summary["family_split_audit"]
    numeric = summary["numeric"]
    lines = [
        f"# {summary['dataset_name']} Quality Report",
        "",
        f"Created UTC: `{summary['created_utc']}`",
        "",
        "## Snapshot",
        "",
        f"- maps: `{counts['map_count']}`",
        f"- missing split rows: `{counts['missing_split_count']}`",
        f"- missing tensor files: `{counts['missing_tensor_file_count']}`",
        f"- family split leaks: `{family['leak_count']}`",
        "",
        "## Split Counts",
        "",
    ]
    for split, count in summary["by_split"].items():
        lines.append(f"- `{split or 'missing'}`: `{count}`")
    lines.extend(["", "## Numeric Summary", ""])
    for field, stats in numeric.items():
        lines.append(
            "- `{}`: min `{}`, median `{}`, mean `{}`, p95 `{}`, max `{}`".format(
                field,
                stats["min"],
                stats["median"],
                stats["mean"],
                stats["p95"],
                stats["max"],
            )
        )
    lines.extend(["", "## Team Settings", ""])
    for label, count in list(summary["by_predicted_team_setting"].items())[:20]:
        lines.append(f"- `{label}`: `{count}`")
    lines.extend(["", "## Family Split Audit", ""])
    if family["leak_count"]:
        lines.append("Potential split leaks detected:")
        for leak in family["leaks"][:20]:
            lines.append(
                f"- `{leak['group_key']}` in `{', '.join(leak['splits'])}` "
                f"({leak['map_count']} maps): {', '.join(leak['examples'][:4])}"
            )
    else:
        lines.append("No family/duplicate split leakage detected in this subset.")
    lines.extend(["", "## Inputs", ""])
    for key, value in summary["inputs"].items():
        lines.append(f"- `{key}`: `{value}`")
    lines.append("")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a tensor dataset quality report.")
    parser.add_argument("--tensor-manifest", required=True, type=Path)
    parser.add_argument("--splits-csv", type=Path)
    parser.add_argument("--audit-maps", type=Path)
    parser.add_argument("--dataset-name", default="dataset_v1")
    parser.add_argument("--json-out", required=True, type=Path)
    parser.add_argument("--csv-out", required=True, type=Path)
    parser.add_argument("--md-out", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows, summary, markdown = build_report(
        tensor_manifest=args.tensor_manifest,
        splits_csv=args.splits_csv,
        audit_maps_csv=args.audit_maps,
        dataset_name=args.dataset_name,
    )
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    _write_csv(args.csv_out, rows, REPORT_COLUMNS)
    args.md_out.parent.mkdir(parents=True, exist_ok=True)
    args.md_out.write_text(markdown, encoding="utf-8")
    print(f"Wrote dataset quality JSON to {args.json_out}")
    print(f"Wrote dataset quality CSV to {args.csv_out}")
    print(f"Wrote dataset quality Markdown to {args.md_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
