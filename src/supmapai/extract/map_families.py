"""Detect V1 map families, version winners, and name-based variant flags."""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

CSV_COLUMNS = [
    "family_key",
    "family_size",
    "recommended_map_dir",
    "recommended_reason",
    "map_dir",
    "scenario_name",
    "variant_flags",
    "variant_flag_count",
    "is_variant_named",
    "scenario_map_version",
    "folder_version",
    "highest_detected_version",
    "latest_write_time",
    "candidate_count",
    "backup_candidate_count",
    "selection_reason",
    "scmap_count",
    "scenario_count",
    "save_count",
    "preview_count",
    "clone_reskin_candidate",
    "reason",
]

VARIANT_FLAG_PATTERNS = {
    "adaptive": r"\badaptive\b",
    "flooded": r"\bflood(?:ed|ing)?\b|\bflooded\s+version\b",
    "dry": r"\bdry\b|\bdry\s+version\b",
    "survival": r"\bsurvival\b|\bsurvive\b",
    "phantom": r"\bphantom\b",
    "coop": r"\bcoop\b|\bco\s*op\b|\bcampaign\s+coop\b",
    "gap": r"\bgap\b",
    "pass": r"\bpass\b|\bpassage\b",
    "crater": r"\bcrater\b",
}

FAMILY_STRIP_FLAG_PATTERNS = [
    VARIANT_FLAG_PATTERNS["adaptive"],
    VARIANT_FLAG_PATTERNS["flooded"],
    VARIANT_FLAG_PATTERNS["dry"],
    VARIANT_FLAG_PATTERNS["survival"],
    VARIANT_FLAG_PATTERNS["phantom"],
    VARIANT_FLAG_PATTERNS["coop"],
]

STRIP_PATTERNS = [
    *FAMILY_STRIP_FLAG_PATTERNS,
    r"\.v\d{4}\b",
    r"\bv(?:ersion)?\.?\s*\d+\b",
    r"\bver\.?\s*\d+\b",
    r"\brev(?:ision)?\.?\s*\d+\b",
    r"\br\d+\b",
    r"\bfinal\b",
    r"\bfixed?\b",
    r"\bupdate(?:d)?\b",
    r"\bofficial\b",
    r"\bfaf\b",
    r"\bmap\b",
    r"\bremake\b",
    r"\brework\b",
    r"\bclassic\b",
    r"\bspecial\b",
    r"\bedition\b",
    r"\bthe\b",
]

VERSION_RE = re.compile(
    r"\.v(?P<folder>\d{4})\b|"
    r"\bv(?:ersion)?\.?\s*(?P<version>\d+)\b|"
    r"\bver\.?\s*(?P<ver>\d+)\b|"
    r"\brev(?:ision)?\.?\s*(?P<rev>\d+)\b|"
    r"\br(?P<revision>\d+)\b",
    re.I,
)


def _normalize_token_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[_\-.]+", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _base_name(text: str) -> str:
    normalized = f" {_normalize_token_text(text)} "
    for pattern in STRIP_PATTERNS:
        normalized = re.sub(pattern, " ", normalized, flags=re.I)
    normalized = re.sub(r"\b\d+\s*x\s*\d+\b", " ", normalized)
    normalized = re.sub(r"\b\d+\s*v\s*\d+\b", " ", normalized)
    normalized = re.sub(r"\b\d+\s*p\b", " ", normalized)
    normalized = re.sub(r"\b\d+\s*player(?:s)?\b", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _compact_key(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text)


def _variant_flags(text: str) -> list[str]:
    searchable = _normalize_token_text(text)
    return [
        flag
        for flag, pattern in VARIANT_FLAG_PATTERNS.items()
        if re.search(pattern, searchable, re.I)
    ]


def _version_from_text(text: str) -> int | None:
    versions: list[int] = []
    for match in VERSION_RE.finditer(text):
        for value in match.groupdict().values():
            if value is not None:
                versions.append(int(value))
    return max(versions) if versions else None


def _int_or_none(value: Any) -> int | None:
    if value in ("", None):
        return None
    try:
        return int(float(str(value)))
    except ValueError:
        return None


def _candidate_version(candidate: dict[str, Any]) -> int | None:
    values = [
        _int_or_none(candidate.get("scenario_map_version")),
        _int_or_none(candidate.get("folder_version")),
        _int_or_none(candidate.get("backup_number")),
        _version_from_text(str(candidate.get("map_dir", ""))),
        _version_from_text(str(candidate.get("scenario_name", ""))),
    ]
    numeric = [value for value in values if value is not None]
    return max(numeric) if numeric else None


def _latest_write_sort_value(value: str) -> str:
    if not value:
        return ""
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).isoformat()
    except ValueError:
        return value


def _best_candidate(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    def score(candidate: dict[str, Any]) -> tuple[int, int, int, int, str]:
        return (
            _candidate_version(candidate) or 0,
            int(bool(candidate.get("is_top_level"))),
            int(not bool(candidate.get("is_backup_path"))),
            int(candidate.get("completeness_score") or 0),
            _latest_write_sort_value(str(candidate.get("latest_write_time", ""))),
        )

    return max(candidates, key=score)


def _source_name(map_record: dict[str, Any]) -> str:
    selected = map_record.get("selected_candidate") or {}
    scenario_name = str(selected.get("scenario_name", "")).strip()
    if scenario_name and scenario_name.lower() != "ffa":
        return scenario_name
    return str(map_record.get("top_level_dir", ""))


def _record_candidates(map_record: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = map_record.get("candidates") or []
    if candidates:
        return candidates
    selected = map_record.get("selected_candidate")
    return [selected] if selected else []


def _row_from_map_record(map_record: dict[str, Any]) -> dict[str, Any]:
    selected = map_record.get("selected_candidate") or {}
    source_name = _source_name(map_record)
    searchable_name = " ".join(
        [
            str(map_record.get("top_level_dir", "")),
            str(map_record.get("selected_map_dir", "")),
            source_name,
        ]
    )
    base = _base_name(source_name) or _base_name(str(map_record.get("top_level_dir", "")))
    family_key = _compact_key(base) or _compact_key(str(map_record.get("top_level_dir", "")))
    flags = _variant_flags(searchable_name)
    highest_version = _candidate_version(selected)

    return {
        "family_key": family_key,
        "map_dir": map_record.get("top_level_dir", ""),
        "scenario_name": source_name,
        "variant_flags": "|".join(flags),
        "variant_flag_count": len(flags),
        "is_variant_named": bool(flags),
        "scenario_map_version": selected.get("scenario_map_version") or "",
        "folder_version": selected.get("folder_version") or "",
        "highest_detected_version": highest_version or "",
        "latest_write_time": selected.get("latest_write_time", ""),
        "candidate_count": map_record.get("candidate_count", 0),
        "backup_candidate_count": map_record.get("backup_candidate_count", 0),
        "selection_reason": map_record.get("selection_reason", ""),
        "scmap_count": selected.get("scmap_count", ""),
        "scenario_count": selected.get("scenario_count", ""),
        "save_count": selected.get("save_count", ""),
        "preview_count": selected.get("preview_count", ""),
        "_candidate_winner": _best_candidate(_record_candidates(map_record)),
    }


def _family_reasons(rows: list[dict[str, Any]]) -> str:
    reasons = []
    if len(rows) > 1:
        reasons.append("same_normalized_base_name")
    if any(row["variant_flags"] for row in rows):
        reasons.append("named_variant_flags")
    if len({row["variant_flags"] for row in rows if row["variant_flags"]}) > 1:
        reasons.append("multiple_variant_flag_sets")
    if any(int(row["candidate_count"] or 0) > 1 for row in rows):
        reasons.append("multiple_versions_inside_folder")
    if len({str(row["highest_detected_version"]) for row in rows}) > 1:
        reasons.append("different_detected_versions")
    return "|".join(reasons) or "single_original_name"


def _recommend_map(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def score(row: dict[str, Any]) -> tuple[int, int, int, int, int, str]:
        winner = row["_candidate_winner"]
        return (
            _candidate_version(winner) or _int_or_none(row["highest_detected_version"]) or 0,
            int(not bool(winner.get("is_backup_path"))),
            int(bool(winner.get("is_top_level"))),
            int(winner.get("completeness_score") or 0),
            int(row.get("scmap_count") or 0),
            _latest_write_sort_value(str(row.get("latest_write_time", ""))),
        )

    return max(rows, key=score)


def build_map_families(inventory: dict[str, Any]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for map_record in inventory.get("maps", []):
        row = _row_from_map_record(map_record)
        grouped[row["family_key"]].append(row)

    output: list[dict[str, Any]] = []
    for family_key, rows in grouped.items():
        recommended = _recommend_map(rows)
        reason = _family_reasons(rows)
        clone_reskin_candidate = len(rows) > 1
        for row in rows:
            clean = {column: "" for column in CSV_COLUMNS}
            clean.update(row)
            clean["family_key"] = family_key
            clean["family_size"] = len(rows)
            clean["recommended_map_dir"] = recommended["map_dir"]
            clean["recommended_reason"] = "highest_detected_version_wins"
            clean["clone_reskin_candidate"] = str(clone_reskin_candidate).lower()
            clean["reason"] = reason
            clean["is_variant_named"] = str(bool(row["is_variant_named"])).lower()
            clean.pop("_candidate_winner", None)
            output.append(clean)

    output.sort(
        key=lambda row: (
            -int(row["family_size"]),
            str(row["family_key"]),
            str(row["map_dir"]).lower(),
        )
    )
    return output


def write_csv(rows: list[dict[str, Any]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def write_summary(rows: list[dict[str, Any]], out_path: Path) -> None:
    flags: Counter[str] = Counter()
    family_sizes: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    recommended_rows = 0
    clone_rows = 0

    for row in rows:
        if row["recommended_map_dir"] == row["map_dir"]:
            recommended_rows += 1
            family_sizes[str(row["family_size"])] += 1
        if row["clone_reskin_candidate"] == "true":
            clone_rows += 1
        for flag in str(row["variant_flags"]).split("|"):
            if flag:
                flags[flag] += 1
        for reason in str(row["reason"]).split("|"):
            if reason:
                reason_counts[reason] += 1

    summary = {
        "row_count": len(rows),
        "family_count": recommended_rows,
        "clone_reskin_candidate_rows": clone_rows,
        "clone_reskin_candidate_families": sum(
            count for size, count in family_sizes.items() if int(size) > 1
        ),
        "family_size_distribution": dict(
            sorted(family_sizes.items(), key=lambda item: int(item[0]))
        ),
        "variant_flag_counts": dict(sorted(flags.items())),
        "reason_counts": dict(sorted(reason_counts.items())),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Detect strict V1 map families and name-based variant flags."
    )
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--summary-out", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    inventory = json.loads(args.inventory.read_text(encoding="utf-8-sig"))
    rows = build_map_families(inventory)
    write_csv(rows, args.out)
    if args.summary_out:
        write_summary(rows, args.summary_out)
    print(f"Wrote {len(rows)} map family row(s) to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
