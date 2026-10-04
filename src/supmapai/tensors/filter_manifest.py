"""Filter a tensor manifest for focused ML experiments."""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _matches_any(value: str, allowed: set[str]) -> bool:
    return not allowed or value in allowed


def filter_rows(
    rows: list[dict[str, str]],
    size_classes: set[str],
    audit_statuses: set[str],
    name_regex: re.Pattern[str] | None,
    min_players: int | None,
    max_players: int | None,
) -> list[dict[str, str]]:
    filtered = []
    for row in rows:
        if not row.get("tensor_path"):
            continue
        if not _matches_any(row.get("size_class", ""), size_classes):
            continue
        if not _matches_any(row.get("audit_status", ""), audit_statuses):
            continue
        if name_regex is not None and not name_regex.search(row.get("map_dir", "")):
            continue
        try:
            players = int(float(row.get("player_slots", "") or 0))
        except ValueError:
            players = 0
        if min_players is not None and players < min_players:
            continue
        if max_players is not None and players > max_players:
            continue
        filtered.append(row)
    return filtered


def _summarize(rows: list[dict[str, str]]) -> dict[str, Any]:
    summary: dict[str, Any] = {"count": len(rows), "by_size_class": {}, "by_audit_status": {}}
    for row in rows:
        size = row.get("size_class", "")
        status = row.get("audit_status", "")
        summary["by_size_class"][size] = summary["by_size_class"].get(size, 0) + 1
        summary["by_audit_status"][status] = summary["by_audit_status"].get(status, 0) + 1
    if rows:
        players = []
        water = []
        for row in rows:
            try:
                players.append(float(row.get("player_slots", "") or 0.0))
                water.append(float(row.get("water_percent", "") or 0.0))
            except ValueError:
                continue
        if players:
            summary["player_slots"] = {
                "min": min(players),
                "max": max(players),
                "mean": round(sum(players) / len(players), 6),
            }
        if water:
            summary["water_percent"] = {
                "min": min(water),
                "max": max(water),
                "mean": round(sum(water) / len(water), 6),
            }
    return summary


def _parse_csv_set(value: str | None) -> set[str]:
    if not value:
        return set()
    return {part.strip() for part in value.split(",") if part.strip()}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Filter a tensor manifest for a focused run.")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--summary-out", required=True, type=Path)
    parser.add_argument("--size-class", help="Comma-separated allowed size classes, e.g. 10km")
    parser.add_argument("--audit-status", help="Comma-separated allowed audit statuses, e.g. ready")
    parser.add_argument("--name-regex", help="Regex matched against map_dir.")
    parser.add_argument("--min-players", type=int)
    parser.add_argument("--max-players", type=int)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows = _read_csv(args.manifest)
    fieldnames = list(rows[0].keys()) if rows else []
    name_regex = re.compile(args.name_regex, flags=re.IGNORECASE) if args.name_regex else None
    filtered = filter_rows(
        rows,
        size_classes=_parse_csv_set(args.size_class),
        audit_statuses=_parse_csv_set(args.audit_status),
        name_regex=name_regex,
        min_players=args.min_players,
        max_players=args.max_players,
    )
    _write_csv(args.out, filtered, fieldnames)
    summary = _summarize(filtered)
    args.summary_out.parent.mkdir(parents=True, exist_ok=True)
    args.summary_out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Wrote {len(filtered)} filtered tensor row(s) to {args.out}")
    print(f"Wrote summary to {args.summary_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
