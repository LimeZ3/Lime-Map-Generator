"""Extract first-pass map metadata from inventory, scenario Lua, and save Lua."""

from __future__ import annotations

import argparse
import csv
import json
import re
import struct
from collections import Counter
from pathlib import Path
from typing import Any

CSV_COLUMNS = [
    "map_dir",
    "top_level_dir",
    "selected_map_dir",
    "candidate_count",
    "backup_candidate_count",
    "selection_reason",
    "name_signals",
    "scenario_name",
    "map_version",
    "scenario_size_x",
    "scenario_size_z",
    "scmap_width",
    "scmap_height",
    "player_slots",
    "reclaim_mass",
    "reclaim_energy",
    "scmap_size_bytes",
    "mex_count",
    "hydro_count",
    "spawn_marker_count",
    "total_marker_count",
    "land_path_node_count",
    "air_path_node_count",
    "amphibious_path_node_count",
    "transport_marker_count",
    "naval_marker_count",
    "expansion_area_count",
    "combat_zone_count",
    "rough_navy_presence",
    "rough_land_pathing",
    "rough_air_pathing",
    "rough_expansion_presence",
    "marker_type_counts_json",
    "warnings",
]

STRING_RE_TEMPLATE = r"\b{key}\s*=\s*(['\"])(.*?)\1"
NUMBER_RE_TEMPLATE = r"\b{key}\s*=\s*([-+]?\d+(?:\.\d+)?)"
TYPE_RE = re.compile(r"\['type'\]\s*=\s*STRING\(\s*['\"]([^'\"]+)['\"]\s*\)", re.I)


def _file_entries(map_record: dict[str, Any], key: str) -> list[dict[str, Any]]:
    direct_entries = map_record.get(key)
    if direct_entries is not None:
        return direct_entries
    return map_record.get("files", {}).get(key, [])


def _first_path(map_record: dict[str, Any], key: str, maps_root: Path) -> Path | None:
    entries = _file_entries(map_record, key)
    if not entries:
        return None
    relative = entries[0].get("path")
    if not relative:
        return None
    return maps_root / Path(relative)


def _read_text(path: Path) -> tuple[str, str | None]:
    try:
        return path.read_text(encoding="utf-8", errors="replace"), None
    except OSError as exc:
        return "", f"failed_to_read_{path.name}: {exc}"


def _string_assignment(text: str, key: str) -> str:
    match = re.search(STRING_RE_TEMPLATE.format(key=re.escape(key)), text, re.S)
    return match.group(2).strip() if match else ""


def _number_assignment(text: str, key: str) -> str:
    match = re.search(NUMBER_RE_TEMPLATE.format(key=re.escape(key)), text)
    return match.group(1) if match else ""


def _pair_assignment(text: str, key: str) -> tuple[str, str]:
    match = re.search(
        rf"\b{re.escape(key)}\s*=\s*{{\s*([-+]?\d+(?:\.\d+)?)\s*,\s*([-+]?\d+(?:\.\d+)?)",
        text,
        re.S,
    )
    if not match:
        return "", ""
    return match.group(1), match.group(2)


def _player_slots_from_scenario(text: str) -> int | str:
    army_ids: set[str] = set()
    for army_block in re.findall(r"\barmies\s*=\s*{(.*?)}", text, re.I | re.S):
        army_ids.update(re.findall(r"ARMY_(\d+)", army_block, re.I))

    if not army_ids:
        army_ids.update(re.findall(r"norushoffsetX_ARMY_(\d+)", text, re.I))

    return len(army_ids) if army_ids else ""


def _parse_scenario(path: Path | None) -> tuple[dict[str, Any], list[str]]:
    data: dict[str, Any] = {
        "scenario_name": "",
        "map_version": "",
        "scenario_size_x": "",
        "scenario_size_z": "",
        "player_slots": "",
        "reclaim_mass": "",
        "reclaim_energy": "",
    }
    warnings: list[str] = []

    if path is None:
        warnings.append("missing_scenario_lua")
        return data, warnings

    text, warning = _read_text(path)
    if warning:
        warnings.append(warning)
        return data, warnings

    size_x, size_z = _pair_assignment(text, "size")
    reclaim_mass, reclaim_energy = _pair_assignment(text, "reclaim")
    data.update(
        {
            "scenario_name": _string_assignment(text, "name"),
            "map_version": _number_assignment(text, "map_version"),
            "scenario_size_x": size_x,
            "scenario_size_z": size_z,
            "player_slots": _player_slots_from_scenario(text),
            "reclaim_mass": reclaim_mass,
            "reclaim_energy": reclaim_energy,
        }
    )
    return data, warnings


def _rough_presence(count: int, light_threshold: int, heavy_threshold: int) -> str:
    if count <= 0:
        return "none"
    if count < light_threshold:
        return "minor"
    if count < heavy_threshold:
        return "present"
    return "heavy"


def _parse_save(path: Path | None) -> tuple[dict[str, Any], list[str]]:
    data: dict[str, Any] = {
        "mex_count": 0,
        "hydro_count": 0,
        "spawn_marker_count": 0,
        "total_marker_count": 0,
        "land_path_node_count": 0,
        "air_path_node_count": 0,
        "amphibious_path_node_count": 0,
        "transport_marker_count": 0,
        "naval_marker_count": 0,
        "expansion_area_count": 0,
        "combat_zone_count": 0,
        "rough_navy_presence": "none",
        "rough_land_pathing": "none",
        "rough_air_pathing": "none",
        "rough_expansion_presence": "none",
        "marker_type_counts_json": "{}",
    }
    warnings: list[str] = []

    if path is None:
        warnings.append("missing_save_lua")
        return data, warnings

    text, warning = _read_text(path)
    if warning:
        warnings.append(warning)
        return data, warnings

    marker_types = Counter(TYPE_RE.findall(text))
    naval_marker_count = sum(
        count
        for marker_type, count in marker_types.items()
        if "naval" in marker_type.lower() or marker_type.lower() == "water path node"
    )
    land_path_node_count = marker_types.get("Land Path Node", 0)
    air_path_node_count = marker_types.get("Air Path Node", 0)
    expansion_area_count = marker_types.get("Expansion Area", 0)

    data.update(
        {
            "mex_count": marker_types.get("Mass", 0),
            "hydro_count": marker_types.get("Hydrocarbon", 0),
            "spawn_marker_count": marker_types.get("Blank Marker", 0),
            "total_marker_count": sum(marker_types.values()),
            "land_path_node_count": land_path_node_count,
            "air_path_node_count": air_path_node_count,
            "amphibious_path_node_count": marker_types.get("Amphibious Path Node", 0),
            "transport_marker_count": marker_types.get("Transport Marker", 0),
            "naval_marker_count": naval_marker_count,
            "expansion_area_count": expansion_area_count,
            "combat_zone_count": marker_types.get("Combat Zone", 0),
            "rough_navy_presence": _rough_presence(naval_marker_count, 4, 12),
            "rough_land_pathing": _rough_presence(land_path_node_count, 6, 20),
            "rough_air_pathing": _rough_presence(air_path_node_count, 6, 20),
            "rough_expansion_presence": _rough_presence(expansion_area_count, 3, 8),
            "marker_type_counts_json": json.dumps(
                dict(sorted(marker_types.items())),
                sort_keys=True,
            ),
        }
    )
    return data, warnings


def _parse_scmap_header(path: Path | None) -> tuple[dict[str, Any], list[str]]:
    data: dict[str, Any] = {
        "scmap_width": "",
        "scmap_height": "",
        "scmap_size_bytes": "",
    }
    warnings: list[str] = []

    if path is None:
        warnings.append("missing_scmap")
        return data, warnings

    try:
        stat = path.stat()
        data["scmap_size_bytes"] = stat.st_size
        header = path.read_bytes()[:32]
    except OSError as exc:
        warnings.append(f"failed_to_read_{path.name}: {exc}")
        return data, warnings

    if len(header) < 24 or header[:4] != b"Map\x1a":
        warnings.append("unrecognized_scmap_header")
        return data, warnings

    width, height = struct.unpack("<ff", header[16:24])
    data["scmap_width"] = int(width) if width.is_integer() else round(width, 3)
    data["scmap_height"] = int(height) if height.is_integer() else round(height, 3)
    return data, warnings


def extract_metadata(inventory: dict[str, Any]) -> list[dict[str, Any]]:
    maps_root = Path(inventory["maps_root"])
    rows: list[dict[str, Any]] = []

    for map_record in inventory.get("maps", []):
        warnings: list[str] = []
        row: dict[str, Any] = {column: "" for column in CSV_COLUMNS}
        row["map_dir"] = (
            map_record.get("top_level_dir")
            or map_record.get("map_dir")
            or map_record.get("selected_map_dir")
            or ""
        )
        row["top_level_dir"] = map_record.get("top_level_dir", "")
        row["selected_map_dir"] = map_record.get("selected_map_dir", "")
        row["candidate_count"] = map_record.get("candidate_count", "")
        row["backup_candidate_count"] = map_record.get("backup_candidate_count", "")
        row["selection_reason"] = map_record.get("selection_reason", "")
        row["name_signals"] = "|".join(map_record.get("name_signals", []))

        scenario_data, scenario_warnings = _parse_scenario(
            _first_path(map_record, "scenario_lua", maps_root)
        )
        save_data, save_warnings = _parse_save(_first_path(map_record, "save_lua", maps_root))
        scmap_data, scmap_warnings = _parse_scmap_header(
            _first_path(map_record, "scmap", maps_root)
        )

        row.update(scenario_data)
        row.update(save_data)
        row.update(scmap_data)
        warnings.extend(scenario_warnings)
        warnings.extend(save_warnings)
        warnings.extend(scmap_warnings)
        row["warnings"] = "|".join(warnings)
        rows.append(row)

    rows.sort(key=lambda item: str(item["map_dir"]).lower())
    return rows


def write_csv(rows: list[dict[str, Any]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract first-pass structural metadata from a SupCom map inventory."
    )
    parser.add_argument(
        "--inventory",
        required=True,
        type=Path,
        help="Inventory JSON generated by supmapai.extract.inventory.",
    )
    parser.add_argument(
        "--out",
        required=True,
        type=Path,
        help="Output CSV path, for example data\\interim\\map_metadata.csv.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
    rows = extract_metadata(inventory)
    write_csv(rows, args.out)
    print(f"Wrote {len(rows)} metadata row(s) to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
