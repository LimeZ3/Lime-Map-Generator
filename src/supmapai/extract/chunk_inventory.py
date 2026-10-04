"""Split a canonical inventory into deterministic processing chunks."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _has_required_files(map_record: dict[str, Any], require: set[str]) -> bool:
    files = map_record.get("files", {})
    return all(files.get(key) for key in require)


def _chunk_records(records: list[dict[str, Any]], chunk_size: int) -> list[list[dict[str, Any]]]:
    return [records[index : index + chunk_size] for index in range(0, len(records), chunk_size)]


def chunk_inventory(
    inventory: dict[str, Any],
    chunk_size: int,
    require: set[str],
) -> list[dict[str, Any]]:
    if chunk_size <= 0:
        raise ValueError("--chunk-size must be positive")

    records = [
        map_record
        for map_record in inventory.get("maps", [])
        if _has_required_files(map_record, require)
    ]
    records.sort(key=lambda record: record.get("top_level_dir", "").lower())
    chunks = _chunk_records(records, chunk_size)
    chunk_count = len(chunks)

    output = []
    for index, chunk in enumerate(chunks):
        output.append(
            {
                "schema_version": inventory.get("schema_version", 1),
                "generated_at": datetime.now(UTC).isoformat(),
                "source_generated_at": inventory.get("generated_at", ""),
                "source_map_count": inventory.get("map_count", len(inventory.get("maps", []))),
                "chunk_index": index,
                "chunk_count": chunk_count,
                "chunk_size": chunk_size,
                "chunk_required_files": sorted(require),
                "maps_root": inventory["maps_root"],
                "map_count": len(chunk),
                "maps": chunk,
            }
        )
    return output


def write_chunks(chunks: list[dict[str, Any]], out_dir: Path, prefix: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    width = max(4, len(str(max(len(chunks) - 1, 0))))
    for chunk in chunks:
        index = int(chunk["chunk_index"])
        out_path = out_dir / f"{prefix}_{index:0{width}d}_inventory.json"
        out_path.write_text(json.dumps(chunk, indent=2), encoding="utf-8")

    manifest = {
        "generated_at": datetime.now(UTC).isoformat(),
        "prefix": prefix,
        "chunk_count": len(chunks),
        "chunk_size": chunks[0]["chunk_size"] if chunks else 0,
        "total_map_count": sum(chunk["map_count"] for chunk in chunks),
        "chunks": [
            {
                "chunk_index": chunk["chunk_index"],
                "map_count": chunk["map_count"],
                "inventory_path": f"{prefix}_{int(chunk['chunk_index']):0{width}d}_inventory.json",
            }
            for chunk in chunks
        ],
    }
    (out_dir / f"{prefix}_manifest.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Split a canonical inventory into chunks.")
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--prefix", default="batch")
    parser.add_argument("--chunk-size", default=250, type=int)
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
    chunks = chunk_inventory(
        inventory=inventory,
        chunk_size=args.chunk_size,
        require=set(args.require or ["scmap", "scenario_lua", "save_lua"]),
    )
    write_chunks(chunks, args.out_dir, args.prefix)
    print(
        f"Wrote {len(chunks)} chunk inventory file(s), "
        f"{sum(chunk['map_count'] for chunk in chunks)} map(s) total"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
