"""Find likely duplicate, version, and variant map families from names."""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

CSV_COLUMNS = [
    "family_key",
    "family_size",
    "recommended_map_dir",
    "map_dir",
    "is_backup_path",
    "scenario_name",
    "map_version",
    "version_tokens",
    "variant_tokens",
    "size_x",
    "size_z",
    "player_slots",
    "mex_count",
    "hydro_count",
    "rough_navy_presence",
    "reason",
]

VARIANT_TOKEN_PATTERNS = {
    "adaptive": r"\badaptive\b|\bai\b",
    "faf": r"\bfaf\b",
    "flooded": r"\bflood(?:ed)?\b|\bwater\b|\bnaval\b",
    "winter": r"\bwinter\b|\bsnow\b|\bice\b|\bfrozen\b",
    "desert": r"\bdesert\b|\bsand\b",
    "night": r"\bnight\b|\bdark\b",
    "survival": r"\bsurvival\b|\bsurvive\b",
    "phantom": r"\bphantom\b",
    "crazyrush": r"\bcrazy\s*_*rush\b|\bcr\b",
    "teamplay": r"\bteam\s*play\b|\bteamplay\b",
    "ffa": r"\bffa\b",
    "duel": r"\b1\s*v\s*1\b|\b1v1\b|\bduel\b",
    "team_size": r"\b[2-8]\s*v\s*[2-8]\b|\b[2-9]v[2-9]\b",
    "special_edition": r"\bspecial\b|\bse\b|\bedition\b|\brework\b|\bremake\b",
    "backup": r"\bbackup\b",
}

REMOVABLE_TOKEN_PATTERNS = [
    r"\.v\d{4}\b",
    r"\bv(?:ersion)?\.?\s*\d+\b",
    r"\bver\.?\s*\d+\b",
    r"\brev(?:ision)?\.?\s*\d+\b",
    r"\br\d+\b",
    r"\bfinal\b",
    r"\bfix(?:ed)?\b",
    r"\bupdate(?:d)?\b",
    r"\bofficial\b",
    r"\bmap\b",
    r"\bfaf\b",
    r"\badaptive\b",
    r"\bai\b",
    r"\bremake\b",
    r"\brework\b",
    r"\bspecial\b",
    r"\bedition\b",
    r"\bclassic\b",
    r"\b1\s*v\s*1\b",
    r"\b[2-8]\s*v\s*[2-8]\b",
    r"\b[1-9]v[1-9]\b",
    r"\b[1-9]\s*p\b",
    r"\b[1-9]\s*player(?:s)?\b",
    r"\b[0-9]{4}\b",
]

VERSION_TOKEN_RE = re.compile(
    r"\.v\d{4}\b|\bv(?:ersion)?\.?\s*\d+\b|\bver\.?\s*\d+\b|\br\d+\b|\bfinal\b",
    re.I,
)


def _name_source(row: dict[str, str]) -> str:
    scenario_name = row.get("scenario_name", "").strip()
    if scenario_name and scenario_name.lower() != "ffa":
        return scenario_name
    return row.get("map_dir", "")


def _normalize_for_token_search(text: str) -> str:
    normalized = text.lower()
    normalized = re.sub(r"[_\-.]+", " ", normalized)
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _normalize_text(text: str) -> str:
    normalized = _normalize_for_token_search(text)
    normalized = f" {normalized} "
    for pattern in REMOVABLE_TOKEN_PATTERNS:
        normalized = re.sub(pattern, " ", normalized, flags=re.I)
    return re.sub(r"\s+", " ", normalized).strip()


def _compact_key(normalized: str) -> str:
    return re.sub(r"[^a-z0-9]", "", normalized)


def _variant_tokens(text: str) -> list[str]:
    searchable = _normalize_for_token_search(text)
    return [
        token
        for token, pattern in VARIANT_TOKEN_PATTERNS.items()
        if re.search(pattern, searchable, re.I)
    ]


def _version_tokens(text: str) -> list[str]:
    return [match.group(0).strip() for match in VERSION_TOKEN_RE.finditer(text)]


def _int_or_zero(value: Any) -> int:
    try:
        return int(float(str(value)))
    except ValueError:
        return 0


def _is_backup_path(map_dir: str) -> bool:
    normalized = map_dir.replace("\\", "/").lower()
    return "/backup" in normalized or normalized.startswith("backup")


def _float_or_zero(value: Any) -> float:
    try:
        return float(str(value))
    except ValueError:
        return 0.0


def _recommend_row(rows: list[dict[str, str]]) -> dict[str, str]:
    def score(row: dict[str, str]) -> tuple[int, int, int, int, float, int]:
        is_top_level = int("/" not in row.get("map_dir", "").replace("\\", "/"))
        is_not_backup = int(not _is_backup_path(row.get("map_dir", "")))
        is_faf = int("faf" in row["variant_tokens"].split("|"))
        has_version = int(bool(row.get("map_version", "")))
        player_slots = _int_or_zero(row.get("player_slots", ""))
        reclaim = _float_or_zero(row.get("reclaim_mass", ""))
        scmap_size = _int_or_zero(row.get("scmap_size_bytes", ""))
        return (is_not_backup, is_top_level, is_faf, has_version, player_slots, reclaim, scmap_size)

    return max(rows, key=score)


def _row_reason(rows: list[dict[str, str]]) -> str:
    variant_sets = {row["variant_tokens"] for row in rows if row["variant_tokens"]}
    sizes = {(row.get("scenario_size_x", ""), row.get("scenario_size_z", "")) for row in rows}
    player_counts = {row.get("player_slots", "") for row in rows}
    reasons = ["same_normalized_name"]
    if any(row["version_tokens"] for row in rows):
        reasons.append("version_tokens")
    if len(variant_sets) > 1:
        reasons.append("variant_tokens")
    if len(sizes) > 1:
        reasons.append("different_sizes")
    if len(player_counts) > 1:
        reasons.append("different_player_counts")
    return "|".join(reasons)


def build_name_families(metadata_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)

    for row in metadata_rows:
        source_name = _name_source(row)
        family_key = _compact_key(_normalize_text(source_name))
        if not family_key:
            family_key = _compact_key(_normalize_text(row.get("map_dir", "")))

        enriched = dict(row)
        searchable_name = f"{row.get('map_dir', '')} {source_name}"
        enriched["family_key"] = family_key
        enriched["is_backup_path"] = str(_is_backup_path(row.get("map_dir", ""))).lower()
        enriched["version_tokens"] = "|".join(_version_tokens(searchable_name))
        enriched["variant_tokens"] = "|".join(_variant_tokens(searchable_name))
        grouped[family_key].append(enriched)

    output_rows: list[dict[str, str]] = []
    for family_key, rows in grouped.items():
        if len(rows) < 2:
            continue

        recommended = _recommend_row(rows)
        reason = _row_reason(rows)
        for row in sorted(rows, key=lambda item: item.get("map_dir", "").lower()):
            output_rows.append(
                {
                    "family_key": family_key,
                    "family_size": str(len(rows)),
                    "recommended_map_dir": recommended.get("map_dir", ""),
                    "map_dir": row.get("map_dir", ""),
                    "is_backup_path": row.get("is_backup_path", ""),
                    "scenario_name": row.get("scenario_name", ""),
                    "map_version": row.get("map_version", ""),
                    "version_tokens": row.get("version_tokens", ""),
                    "variant_tokens": row.get("variant_tokens", ""),
                    "size_x": row.get("scenario_size_x", ""),
                    "size_z": row.get("scenario_size_z", ""),
                    "player_slots": row.get("player_slots", ""),
                    "mex_count": row.get("mex_count", ""),
                    "hydro_count": row.get("hydro_count", ""),
                    "rough_navy_presence": row.get("rough_navy_presence", ""),
                    "reason": reason,
                }
            )

    output_rows.sort(
        key=lambda item: (-int(item["family_size"]), item["family_key"], item["map_dir"])
    )
    return output_rows


def read_metadata(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(rows: list[dict[str, str]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def write_summary(rows: list[dict[str, str]], out_path: Path) -> None:
    family_sizes: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    variants: Counter[str] = Counter()
    backup_rows = 0
    for row in rows:
        if row["map_dir"] == row["recommended_map_dir"]:
            family_sizes[row["family_size"]] += 1
        if row["is_backup_path"] == "true":
            backup_rows += 1
        for reason in row["reason"].split("|"):
            reasons[reason] += 1
        for variant in row["variant_tokens"].split("|"):
            if variant:
                variants[variant] += 1

    summary = {
        "candidate_row_count": len(rows),
        "candidate_family_count": sum(family_sizes.values()),
        "backup_candidate_row_count": backup_rows,
        "family_size_distribution": dict(
            sorted(family_sizes.items(), key=lambda item: int(item[0]))
        ),
        "reason_counts": dict(sorted(reasons.items())),
        "variant_token_counts": dict(sorted(variants.items())),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Find likely version, duplicate, and variant map families by normalized names."
    )
    parser.add_argument(
        "--metadata",
        required=True,
        type=Path,
        help="Metadata CSV generated by supmapai.extract.metadata_from_inventory.",
    )
    parser.add_argument(
        "--out",
        required=True,
        type=Path,
        help="Output CSV path for candidate duplicate/version families.",
    )
    parser.add_argument(
        "--summary-out",
        type=Path,
        help="Optional JSON summary output path.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows = build_name_families(read_metadata(args.metadata))
    write_csv(rows, args.out)
    if args.summary_out:
        write_summary(rows, args.summary_out)
    print(f"Wrote {len(rows)} likely duplicate/version row(s) to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
