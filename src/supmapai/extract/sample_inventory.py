"""Sample a smaller canonical inventory for safe smoke batches."""

from __future__ import annotations

import argparse
import json
import random
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _has_required_files(map_record: dict[str, Any], require: set[str]) -> bool:
    files = map_record.get("files", {})
    return all(files.get(key) for key in require)


def sample_inventory(
    inventory: dict[str, Any],
    count: int,
    seed: int,
    require: set[str],
) -> dict[str, Any]:
    candidates = [
        map_record
        for map_record in inventory.get("maps", [])
        if _has_required_files(map_record, require)
    ]
    if count > len(candidates):
        raise ValueError(f"Requested {count} maps, but only {len(candidates)} match filters")

    rng = random.Random(seed)
    selected = rng.sample(candidates, count)
    selected.sort(key=lambda record: record.get("top_level_dir", "").lower())

    return {
        "schema_version": inventory.get("schema_version", 1),
        "generated_at": datetime.now(UTC).isoformat(),
        "source_generated_at": inventory.get("generated_at", ""),
        "source_map_count": inventory.get("map_count", len(inventory.get("maps", []))),
        "sample_seed": seed,
        "sample_count": count,
        "sample_required_files": sorted(require),
        "maps_root": inventory["maps_root"],
        "map_count": len(selected),
        "maps": selected,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a random sample from a canonical inventory."
    )
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--count", required=True, type=int)
    parser.add_argument("--seed", required=True, type=int)
    parser.add_argument(
        "--require",
        action="append",
        choices=["scmap", "scenario_lua", "save_lua"],
        default=[],
        help="Require this file group. May be passed multiple times.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    inventory = json.loads(args.inventory.read_text(encoding="utf-8-sig"))
    require = set(args.require or ["scmap", "scenario_lua", "save_lua"])
    sampled = sample_inventory(inventory, args.count, args.seed, require)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(sampled, indent=2), encoding="utf-8")
    print(
        f"Wrote {sampled['map_count']} sampled map(s) from "
        f"{sampled['source_map_count']} candidate map(s) to {args.out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
