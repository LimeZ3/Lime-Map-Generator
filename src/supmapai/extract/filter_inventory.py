"""Filter canonical or chunked map inventories without touching raw map folders."""

from __future__ import annotations

import argparse
import copy
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _record_search_text(map_record: dict[str, Any]) -> str:
    parts: list[str] = []

    def add(value: Any) -> None:
        if value not in ("", None):
            parts.append(str(value))

    add(map_record.get("top_level_dir"))
    add(map_record.get("selected_map_dir"))
    add(map_record.get("selection_reason"))
    for signal in map_record.get("name_signals", []):
        add(signal)

    for candidate_key in ("selected_candidate",):
        candidate = map_record.get(candidate_key) or {}
        add(candidate.get("map_dir"))
        add(candidate.get("scenario_name"))

    for candidate in map_record.get("candidates", []):
        add(candidate.get("map_dir"))
        add(candidate.get("scenario_name"))

    for entries in map_record.get("files", {}).values():
        for entry in entries:
            add(entry.get("path"))

    return " ".join(parts)


def _compile_patterns(patterns: list[str]) -> list[re.Pattern[str]]:
    return [re.compile(pattern, re.I) for pattern in patterns]


def _should_exclude(map_record: dict[str, Any], patterns: list[re.Pattern[str]]) -> bool:
    text = _record_search_text(map_record)
    return any(pattern.search(text) for pattern in patterns)


def filter_inventory(
    inventory: dict[str, Any],
    exclude_patterns: list[re.Pattern[str]],
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    kept = []
    removed = []
    for map_record in inventory.get("maps", []):
        if _should_exclude(map_record, exclude_patterns):
            removed.append(
                {
                    "top_level_dir": str(map_record.get("top_level_dir", "")),
                    "selected_map_dir": str(map_record.get("selected_map_dir", "")),
                    "scenario_name": str(
                        (map_record.get("selected_candidate") or {}).get("scenario_name", "")
                    ),
                }
            )
        else:
            kept.append(map_record)

    filtered = copy.deepcopy(inventory)
    filtered["generated_at"] = datetime.now(UTC).isoformat()
    filtered["source_generated_at"] = inventory.get("generated_at", "")
    filtered["source_map_count"] = inventory.get("map_count", len(inventory.get("maps", [])))
    filtered["map_count"] = len(kept)
    filtered["filter_excluded_count"] = len(removed)
    filtered["filter_exclude_patterns"] = [pattern.pattern for pattern in exclude_patterns]
    filtered["maps"] = kept
    return filtered, removed


def write_filtered_inventory(
    inventory_path: Path,
    out_path: Path,
    exclude_patterns: list[re.Pattern[str]],
    summary_out: Path | None,
) -> None:
    inventory = json.loads(inventory_path.read_text(encoding="utf-8-sig"))
    filtered, removed = filter_inventory(inventory, exclude_patterns)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(filtered, indent=2), encoding="utf-8")
    if summary_out is not None:
        summary_out.parent.mkdir(parents=True, exist_ok=True)
        summary_out.write_text(
            json.dumps(
                {
                    "source_inventory": str(inventory_path),
                    "out_inventory": str(out_path),
                    "source_map_count": inventory.get(
                        "map_count",
                        len(inventory.get("maps", [])),
                    ),
                    "filtered_map_count": filtered["map_count"],
                    "removed_count": len(removed),
                    "exclude_patterns": [pattern.pattern for pattern in exclude_patterns],
                    "removed_maps": removed,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    print(f"Wrote {filtered['map_count']} map(s) to {out_path}; removed {len(removed)}")


def write_filtered_inventory_dir(
    inventory_dir: Path,
    out_dir: Path,
    exclude_patterns: list[re.Pattern[str]],
    summary_out: Path | None,
    manifest_name: str,
) -> None:
    manifest_path = inventory_dir / manifest_name
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))

    out_dir.mkdir(parents=True, exist_ok=True)
    removed_all: list[dict[str, str]] = []
    output_chunks = []
    total_map_count = 0
    for chunk in manifest.get("chunks", []):
        input_path = inventory_dir / str(chunk["inventory_path"])
        output_path = out_dir / str(chunk["inventory_path"])
        inventory = json.loads(input_path.read_text(encoding="utf-8-sig"))
        filtered, removed = filter_inventory(inventory, exclude_patterns)
        output_path.write_text(json.dumps(filtered, indent=2), encoding="utf-8")
        removed_all.extend(
            {
                **item,
                "chunk_index": str(chunk.get("chunk_index", "")),
                "inventory_path": str(chunk.get("inventory_path", "")),
            }
            for item in removed
        )
        total_map_count += filtered["map_count"]
        output_chunks.append(
            {
                **chunk,
                "source_map_count": chunk.get("map_count", 0),
                "map_count": filtered["map_count"],
                "filter_excluded_count": len(removed),
            }
        )

    output_manifest = copy.deepcopy(manifest)
    output_manifest["generated_at"] = datetime.now(UTC).isoformat()
    output_manifest["source_manifest_path"] = str(manifest_path)
    output_manifest["source_total_map_count"] = manifest.get("total_map_count", 0)
    output_manifest["total_map_count"] = total_map_count
    output_manifest["filter_excluded_count"] = len(removed_all)
    output_manifest["filter_exclude_patterns"] = [
        pattern.pattern for pattern in exclude_patterns
    ]
    output_manifest["chunks"] = output_chunks
    (out_dir / manifest_name).write_text(json.dumps(output_manifest, indent=2), encoding="utf-8")

    if summary_out is not None:
        summary_out.parent.mkdir(parents=True, exist_ok=True)
        summary_out.write_text(
            json.dumps(
                {
                    "source_manifest": str(manifest_path),
                    "out_dir": str(out_dir),
                    "source_total_map_count": manifest.get("total_map_count", 0),
                    "filtered_total_map_count": total_map_count,
                    "removed_count": len(removed_all),
                    "exclude_patterns": [pattern.pattern for pattern in exclude_patterns],
                    "removed_maps": removed_all,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    print(
        f"Wrote filtered chunk directory {out_dir}: "
        f"{total_map_count} map(s), removed {len(removed_all)}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Filter map inventory JSON files.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--inventory", type=Path)
    source.add_argument("--inventory-dir", type=Path)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--out", type=Path)
    target.add_argument("--out-dir", type=Path)
    parser.add_argument(
        "--exclude-regex",
        required=True,
        action="append",
        help="Case-insensitive regex. May be passed multiple times.",
    )
    parser.add_argument("--summary-out", type=Path)
    parser.add_argument("--manifest-name", default="batch_manifest.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    patterns = _compile_patterns(args.exclude_regex)
    if args.inventory is not None:
        if args.out is None:
            raise ValueError("--out is required with --inventory")
        write_filtered_inventory(args.inventory, args.out, patterns, args.summary_out)
    else:
        if args.out_dir is None:
            raise ValueError("--out-dir is required with --inventory-dir")
        write_filtered_inventory_dir(
            args.inventory_dir,
            args.out_dir,
            patterns,
            args.summary_out,
            args.manifest_name,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
