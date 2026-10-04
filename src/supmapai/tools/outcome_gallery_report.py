"""Summarize generated terrain/structure gallery outcomes."""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


CSV_COLUMNS = [
    "noise",
    "sample",
    "sample_stem",
    "water_percent",
    "water_body_count",
    "largest_water_body_percent",
    "shoreline_length",
    "height_mean",
    "height_std",
    "buildable_percent",
    "passable_percent",
    "spawn_invalid_before",
    "spawn_moved",
    "spawn_dropped",
    "mex_invalid_before",
    "mex_moved",
    "mex_dropped",
    "hydro_invalid_before",
    "hydro_moved",
    "hydro_dropped",
    "reclaim_invalid_before",
    "reclaim_moved",
    "reclaim_dropped",
    "warning_count",
    "warnings",
    "terrain_sheet",
    "structure_sheet",
    "validated_preview",
]


def _float_or_none(value: Any) -> float | None:
    try:
        if value in ("", None):
            return None
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _stats(values: list[float]) -> dict[str, float | int | None]:
    values = sorted(value for value in values if math.isfinite(value))
    if not values:
        return {
            "count": 0,
            "min": None,
            "mean": None,
            "median": None,
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
        "mean": round(sum(values) / len(values), 6),
        "median": round(percentile(0.5), 6),
        "max": round(values[-1], 6),
    }


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, dict) else {}


def _noise_from_dir(path: Path) -> str:
    match = re.search(r"noise(\d+)", path.name)
    return match.group(1) if match else path.name


def _sample_from_path(path: str) -> tuple[str, int | None]:
    stem = Path(path).name.replace(".generated.npz", "")
    match = re.search(r"(\d+)$", stem)
    return stem, int(match.group(1)) if match else None


def _layer(report: dict[str, Any], name: str, field: str) -> Any:
    layers = report.get("layers") if isinstance(report.get("layers"), dict) else {}
    layer = layers.get(name) if isinstance(layers.get(name), dict) else {}
    return layer.get(field, 0)


def _build_rows(base_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for terrain_dir in sorted(base_dir.glob("terrain_noise*")):
        if not terrain_dir.is_dir():
            continue
        noise = _noise_from_dir(terrain_dir)
        metrics_rows = _read_csv(terrain_dir / "terrain_metrics.csv")
        validated_dir = base_dir / f"validated_noise{noise}"
        structures_dir = base_dir / f"structures_noise{noise}"
        for metric_row in metrics_rows:
            sample_stem, sample = _sample_from_path(metric_row.get("sample_path", ""))
            report = _read_json(validated_dir / f"{sample_stem}.validator_report.json")
            warnings = report.get("warnings", [])
            if not isinstance(warnings, list):
                warnings = [str(warnings)]
            row: dict[str, Any] = {
                "noise": noise,
                "sample": "" if sample is None else sample,
                "sample_stem": sample_stem,
                "water_percent": metric_row.get("water_percent", ""),
                "water_body_count": metric_row.get("water_body_count", ""),
                "largest_water_body_percent": metric_row.get("largest_water_body_percent", ""),
                "shoreline_length": metric_row.get("shoreline_length", ""),
                "height_mean": metric_row.get("height_mean", ""),
                "height_std": metric_row.get("height_std", ""),
                "buildable_percent": report.get("buildable_percent", ""),
                "passable_percent": report.get("passable_percent", ""),
                "spawn_invalid_before": _layer(report, "spawns", "invalid_before"),
                "spawn_moved": _layer(report, "spawns", "moved"),
                "spawn_dropped": _layer(report, "spawns", "dropped"),
                "mex_invalid_before": _layer(report, "mexes", "invalid_before"),
                "mex_moved": _layer(report, "mexes", "moved"),
                "mex_dropped": _layer(report, "mexes", "dropped"),
                "hydro_invalid_before": _layer(report, "hydros", "invalid_before"),
                "hydro_moved": _layer(report, "hydros", "moved"),
                "hydro_dropped": _layer(report, "hydros", "dropped"),
                "reclaim_invalid_before": report.get("reclaim", {}).get("invalid_before", 0)
                if isinstance(report.get("reclaim"), dict)
                else 0,
                "reclaim_moved": report.get("reclaim", {}).get("moved", 0)
                if isinstance(report.get("reclaim"), dict)
                else 0,
                "reclaim_dropped": report.get("reclaim", {}).get("dropped", 0)
                if isinstance(report.get("reclaim"), dict)
                else 0,
                "warning_count": len(warnings),
                "warnings": "; ".join(str(warning) for warning in warnings),
                "terrain_sheet": str(terrain_dir / "sheets" / f"{sample_stem}.sheet.png"),
                "structure_sheet": str(structures_dir / "sheets" / f"{sample_stem}.sheet.png"),
                "validated_preview": str(validated_dir / f"{sample_stem}.validated.preview.png"),
            }
            rows.append(row)
    return rows


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    numeric_fields = [
        "water_percent",
        "water_body_count",
        "largest_water_body_percent",
        "shoreline_length",
        "height_std",
        "buildable_percent",
        "passable_percent",
        "spawn_moved",
        "mex_moved",
        "hydro_moved",
        "reclaim_moved",
        "warning_count",
    ]
    by_noise: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_noise[str(row.get("noise", ""))].append(row)

    per_noise: dict[str, Any] = {}
    for noise, noise_rows in sorted(by_noise.items()):
        per_noise[noise] = {
            "sample_count": len(noise_rows),
            "metrics": {
                field: _stats(
                    [
                        value
                        for row in noise_rows
                        if (value := _float_or_none(row.get(field))) is not None
                    ]
                )
                for field in numeric_fields
            },
        }

    return {
        "schema": "mapgen_outcome_gallery_report_v1",
        "created_at": datetime.now(UTC).isoformat(),
        "sample_count": len(rows),
        "noise_levels": per_noise,
    }


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _write_markdown(path: Path, summary: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    lines = [
        "# Outcome Gallery Report",
        "",
        f"Samples: {summary['sample_count']}",
        "",
        "## Noise Summary",
        "",
        "| noise | samples | water % mean | buildable % mean | passable % mean | mex moved mean | warnings |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for noise, payload in summary["noise_levels"].items():
        metrics = payload["metrics"]
        lines.append(
            "| {noise} | {count} | {water} | {buildable} | {passable} | {mex_moved} | {warnings} |".format(
                noise=noise,
                count=payload["sample_count"],
                water=metrics["water_percent"]["mean"],
                buildable=metrics["buildable_percent"]["mean"],
                passable=metrics["passable_percent"]["mean"],
                mex_moved=metrics["mex_moved"]["mean"],
                warnings=metrics["warning_count"]["mean"],
            )
        )

    def score(row: dict[str, Any]) -> float:
        mex_moved = _float_or_none(row.get("mex_moved")) or 0.0
        hydro_moved = _float_or_none(row.get("hydro_moved")) or 0.0
        spawn_moved = _float_or_none(row.get("spawn_moved")) or 0.0
        water = _float_or_none(row.get("water_percent")) or 0.0
        buildable = _float_or_none(row.get("buildable_percent")) or 0.0
        water_penalty = abs(water - 25.0) / 10.0
        buildable_penalty = abs(buildable - 55.0) / 10.0
        return mex_moved + hydro_moved * 0.5 + spawn_moved * 2.0 + water_penalty + buildable_penalty

    ranked = sorted(rows, key=score)
    lines.extend(
        [
            "",
            "## Lowest Repair Burden",
            "",
            "| noise | sample | water % | buildable % | passable % | mex moved | hydro moved | preview |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for row in ranked[:12]:
        lines.append(
            "| {noise} | {sample} | {water} | {buildable} | {passable} | {mex_moved} | {hydro_moved} | {preview} |".format(
                noise=row["noise"],
                sample=row["sample"],
                water=round(float(row["water_percent"]), 3),
                buildable=round(float(row["buildable_percent"]), 3),
                passable=round(float(row["passable_percent"]), 3),
                mex_moved=row["mex_moved"],
                hydro_moved=row["hydro_moved"],
                preview=row["validated_preview"],
            )
        )

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-dir", required=True, type=Path)
    parser.add_argument("--out-csv", type=Path)
    parser.add_argument("--out-json", type=Path)
    parser.add_argument("--out-md", type=Path)
    args = parser.parse_args(argv)

    rows = _build_rows(args.base_dir)
    summary = _summary(rows)
    out_csv = args.out_csv or args.base_dir / "gallery_summary.csv"
    out_json = args.out_json or args.base_dir / "gallery_summary.json"
    out_md = args.out_md or args.base_dir / "gallery_summary.md"

    _write_csv(out_csv, rows)
    out_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    _write_markdown(out_md, summary, rows)
    print(f"Wrote {len(rows)} rows")
    print(f"CSV: {out_csv}")
    print(f"JSON: {out_json}")
    print(f"Markdown: {out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
