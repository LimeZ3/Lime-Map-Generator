"""Inventory likely Supreme Commander map files in a dataset folder."""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

IMAGE_SUFFIXES = {".bmp", ".dds", ".jpeg", ".jpg", ".png", ".tga"}


@dataclass(frozen=True)
class FileEntry:
    """A file path plus basic facts useful for later extraction passes."""

    path: str
    size_bytes: int


@dataclass
class MapFolderInventory:
    """Likely map files grouped by their containing folder."""

    map_dir: str
    scmap: list[FileEntry] = field(default_factory=list)
    scenario_lua: list[FileEntry] = field(default_factory=list)
    save_lua: list[FileEntry] = field(default_factory=list)
    preview_images: list[FileEntry] = field(default_factory=list)
    other_images: list[FileEntry] = field(default_factory=list)

    @property
    def has_core_map_files(self) -> bool:
        return bool(self.scmap or self.scenario_lua or self.save_lua)


def _relative_or_absolute(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def _file_entry(path: Path, root: Path) -> FileEntry:
    return FileEntry(path=_relative_or_absolute(path, root), size_bytes=path.stat().st_size)


def _is_preview_image(path: Path) -> bool:
    lower_name = path.name.lower()
    return path.suffix.lower() in IMAGE_SUFFIXES and "preview" in lower_name


def _inventory_files(files: Iterable[Path], maps_root: Path) -> dict[Path, MapFolderInventory]:
    by_dir: dict[Path, MapFolderInventory] = {}

    for file_path in files:
        if not file_path.is_file():
            continue

        parent = file_path.parent
        inventory = by_dir.setdefault(
            parent,
            MapFolderInventory(map_dir=_relative_or_absolute(parent, maps_root)),
        )

        lower_name = file_path.name.lower()
        suffix = file_path.suffix.lower()
        entry = _file_entry(file_path, maps_root)

        if suffix == ".scmap":
            inventory.scmap.append(entry)
        elif lower_name.endswith("_scenario.lua"):
            inventory.scenario_lua.append(entry)
        elif lower_name.endswith("_save.lua"):
            inventory.save_lua.append(entry)
        elif _is_preview_image(file_path):
            inventory.preview_images.append(entry)
        elif suffix in IMAGE_SUFFIXES:
            inventory.other_images.append(entry)

    return by_dir


def build_inventory(maps_root: Path) -> dict:
    """Build a JSON-serializable inventory for a SupCom maps directory."""

    maps_root = maps_root.expanduser().resolve()
    if not maps_root.exists():
        raise FileNotFoundError(f"Maps root does not exist: {maps_root}")
    if not maps_root.is_dir():
        raise NotADirectoryError(f"Maps root is not a directory: {maps_root}")

    grouped = _inventory_files(maps_root.rglob("*"), maps_root)
    likely_maps = [
        inventory
        for inventory in grouped.values()
        if inventory.has_core_map_files or inventory.preview_images
    ]
    likely_maps.sort(key=lambda item: item.map_dir.lower())

    return {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "maps_root": str(maps_root),
        "map_count": len(likely_maps),
        "maps": [asdict(item) for item in likely_maps],
    }


def write_inventory(inventory: dict, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(inventory, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scan a directory of SupCom map folders and write a file inventory JSON."
    )
    parser.add_argument(
        "--maps-root",
        required=True,
        type=Path,
        help="Root directory containing Supreme Commander map folders.",
    )
    parser.add_argument(
        "--out",
        required=True,
        type=Path,
        help="Output JSON path, for example data\\manifests\\inventory.json.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    inventory = build_inventory(args.maps_root)
    write_inventory(inventory, args.out)
    print(f"Wrote {inventory['map_count']} likely map folder(s) to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
