"""Build a canonical one-map-per-top-level-folder inventory."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from supmapai.extract.inventory import MapFolderInventory, _inventory_files

NAME_SIGNAL_PATTERNS = {
    "adaptive": r"\badaptive",
    "crater": r"\bcrater\b",
    "gap": r"\bgap\b",
    "pass": r"\bpass(?:age)?\b",
}

SCENARIO_VERSION_RE = re.compile(r"\bmap_version\s*=\s*(\d+)", re.I)
SCENARIO_NAME_RE = re.compile(r"\bname\s*=\s*(['\"])(.*?)\1", re.I | re.S)
FOLDER_VERSION_RE = re.compile(r"\.v(\d{4})\b", re.I)
BACKUP_RE = re.compile(r"(?:^|[\\/])backup[_\-\s]*(\d*)", re.I)


@dataclass
class CandidateVersion:
    """A candidate map version found inside one top-level map folder."""

    map_dir: str
    is_top_level: bool
    is_backup_path: bool
    scenario_name: str = ""
    scenario_map_version: int | None = None
    folder_version: int | None = None
    backup_number: int | None = None
    latest_write_time: str = ""
    completeness_score: int = 0
    scmap_count: int = 0
    scenario_count: int = 0
    save_count: int = 0
    preview_count: int = 0


@dataclass
class CanonicalMapInventory:
    """One canonical map record for a top-level FAF maps folder."""

    top_level_dir: str
    selected_map_dir: str
    selection_reason: str
    name_signals: list[str] = field(default_factory=list)
    candidate_count: int = 0
    backup_candidate_count: int = 0
    selected_candidate: CandidateVersion | None = None
    candidates: list[CandidateVersion] = field(default_factory=list)
    files: dict[str, Any] = field(default_factory=dict)


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _is_backup_path(relative_path: str) -> bool:
    return bool(BACKUP_RE.search(relative_path.replace("\\", "/")))


def _folder_version(relative_path: str) -> int | None:
    matches = FOLDER_VERSION_RE.findall(relative_path)
    return int(matches[-1]) if matches else None


def _backup_number(relative_path: str) -> int | None:
    match = BACKUP_RE.search(relative_path.replace("\\", "/"))
    if not match or not match.group(1):
        return None
    return int(match.group(1))


def _read_scenario_fields(path: Path | None) -> tuple[str, int | None]:
    if path is None or not path.exists():
        return "", None
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "", None

    name_match = SCENARIO_NAME_RE.search(text)
    version_match = SCENARIO_VERSION_RE.search(text)
    name = name_match.group(2).strip() if name_match else ""
    version = int(version_match.group(1)) if version_match else None
    return name, version


def _first_file_path(inventory: MapFolderInventory, attr: str, maps_root: Path) -> Path | None:
    entries = getattr(inventory, attr)
    if not entries:
        return None
    return maps_root / Path(entries[0].path)


def _latest_write_time(map_dir: Path) -> str:
    latest = map_dir.stat().st_mtime
    for file_path in map_dir.glob("*"):
        if file_path.is_file():
            latest = max(latest, file_path.stat().st_mtime)
    return datetime.fromtimestamp(latest, UTC).isoformat()


def _candidate_from_inventory(
    inventory: MapFolderInventory,
    top_level_dir: Path,
    maps_root: Path,
) -> CandidateVersion:
    relative_map_dir = inventory.map_dir
    scenario_name, scenario_map_version = _read_scenario_fields(
        _first_file_path(inventory, "scenario_lua", maps_root)
    )
    candidate_path = maps_root / Path(relative_map_dir)

    return CandidateVersion(
        map_dir=relative_map_dir,
        is_top_level=candidate_path.resolve() == top_level_dir.resolve(),
        is_backup_path=_is_backup_path(relative_map_dir),
        scenario_name=scenario_name,
        scenario_map_version=scenario_map_version,
        folder_version=_folder_version(relative_map_dir),
        backup_number=_backup_number(relative_map_dir),
        latest_write_time=_latest_write_time(candidate_path),
        completeness_score=sum(
            [
                bool(inventory.scmap),
                bool(inventory.scenario_lua),
                bool(inventory.save_lua),
            ]
        ),
        scmap_count=len(inventory.scmap),
        scenario_count=len(inventory.scenario_lua),
        save_count=len(inventory.save_lua),
        preview_count=len(inventory.preview_images),
    )


def _candidate_score(candidate: CandidateVersion) -> tuple[int, int, int, int, int, str]:
    """Prefer legal top-level maps, then newest version-like signals."""

    return (
        int(not candidate.is_backup_path),
        int(candidate.is_top_level),
        candidate.completeness_score,
        candidate.scenario_map_version or 0,
        candidate.folder_version or candidate.backup_number or 0,
        candidate.latest_write_time,
    )


def _selection_reason(selected: CandidateVersion, candidates: list[CandidateVersion]) -> str:
    reasons = []
    if selected.is_top_level:
        reasons.append("selected_top_level_map_folder")
    if selected.is_backup_path:
        reasons.append("selected_backup_candidate_no_better_option")
    if any(candidate.is_backup_path for candidate in candidates):
        reasons.append("backup_candidates_present")
    if len(candidates) > 1:
        reasons.append("multiple_candidate_versions")
    if selected.scenario_map_version is not None:
        reasons.append("scenario_map_version_available")
    return "|".join(reasons) or "single_candidate"


def _name_signals(text: str) -> list[str]:
    searchable = re.sub(r"[_\-.]+", " ", text.lower())
    searchable = re.sub(r"[^a-z0-9]+", " ", searchable)
    return [
        signal
        for signal, pattern in NAME_SIGNAL_PATTERNS.items()
        if re.search(pattern, searchable, re.I)
    ]


def _files_for_selected(
    selected: CandidateVersion,
    directory_inventory: dict[Path, MapFolderInventory],
    maps_root: Path,
) -> dict[str, Any]:
    selected_path = maps_root / Path(selected.map_dir)
    inventory = directory_inventory[selected_path]
    return {
        "scmap": [asdict(entry) for entry in inventory.scmap],
        "scenario_lua": [asdict(entry) for entry in inventory.scenario_lua],
        "save_lua": [asdict(entry) for entry in inventory.save_lua],
        "preview_images": [asdict(entry) for entry in inventory.preview_images],
        "other_images": [asdict(entry) for entry in inventory.other_images],
    }


def build_canonical_inventory(maps_root: Path) -> dict[str, Any]:
    maps_root = maps_root.expanduser().resolve()
    if not maps_root.exists():
        raise FileNotFoundError(f"Maps root does not exist: {maps_root}")
    if not maps_root.is_dir():
        raise NotADirectoryError(f"Maps root is not a directory: {maps_root}")

    directory_inventory = _inventory_files(maps_root.rglob("*"), maps_root)
    likely_dirs = {
        path: inventory
        for path, inventory in directory_inventory.items()
        if inventory.has_core_map_files or inventory.preview_images
    }

    by_top_level: dict[Path, list[tuple[Path, MapFolderInventory]]] = {}
    for path, inventory in likely_dirs.items():
        try:
            relative = path.relative_to(maps_root)
        except ValueError:
            continue
        if not relative.parts:
            continue
        top_level_dir = maps_root / relative.parts[0]
        by_top_level.setdefault(top_level_dir, []).append((path, inventory))

    maps: list[CanonicalMapInventory] = []
    top_level_dirs = sorted((path for path in maps_root.iterdir() if path.is_dir()), key=str)
    for top_level_dir in top_level_dirs:
        candidates = [
            _candidate_from_inventory(inventory, top_level_dir, maps_root)
            for _, inventory in by_top_level.get(top_level_dir, [])
        ]
        if not candidates:
            continue

        selected = max(candidates, key=_candidate_score)
        top_level_name = _relative(top_level_dir, maps_root)
        maps.append(
            CanonicalMapInventory(
                top_level_dir=top_level_name,
                selected_map_dir=selected.map_dir,
                selection_reason=_selection_reason(selected, candidates),
                name_signals=_name_signals(f"{top_level_name} {selected.scenario_name}"),
                candidate_count=len(candidates),
                backup_candidate_count=sum(candidate.is_backup_path for candidate in candidates),
                selected_candidate=selected,
                candidates=sorted(candidates, key=lambda candidate: candidate.map_dir.lower()),
                files=_files_for_selected(selected, directory_inventory, maps_root),
            )
        )

    return {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "maps_root": str(maps_root),
        "map_count": len(maps),
        "maps": [asdict(item) for item in maps],
    }


def write_inventory(inventory: dict[str, Any], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(inventory, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a one-map-per-top-level-folder inventory for FAF maps."
    )
    parser.add_argument(
        "--maps-root",
        required=True,
        type=Path,
        help="Root directory containing top-level FAF map folders.",
    )
    parser.add_argument(
        "--out",
        required=True,
        type=Path,
        help="Output JSON path, for example data\\manifests\\canonical_inventory.json.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    inventory = build_canonical_inventory(args.maps_root)
    write_inventory(inventory, args.out)
    print(f"Wrote {inventory['map_count']} canonical map folder(s) to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
