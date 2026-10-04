"""Extract V1 Lua entities from canonical SupCom map inventories."""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

NUMBER = r"[-+]?\d+(?:\.\d+)?"
STRING_VALUE_RE = re.compile(
    r"\[['\"](?P<key>[^'\"]+)['\"]\]\s*=\s*STRING\(\s*['\"](?P<value>[^'\"]*)['\"]",
    re.I,
)
TYPE_RE = re.compile(r"\['type'\]\s*=\s*STRING\(\s*['\"]([^'\"]+)['\"]\s*\)", re.I)
PROP_RE = re.compile(r"\['prop'\]\s*=\s*STRING\(\s*['\"]([^'\"]+)['\"]\s*\)", re.I)
VECTOR3_RE = re.compile(rf"VECTOR3\(\s*({NUMBER})\s*,\s*({NUMBER})\s*,\s*({NUMBER})\s*\)", re.I)
POSITION_RE = re.compile(
    rf"\[['\"]position['\"]\]\s*=\s*VECTOR3\(\s*({NUMBER})\s*,\s*({NUMBER})\s*,\s*({NUMBER})\s*\)",
    re.I,
)
POSITION_BRACE_RE = re.compile(
    rf"\bPosition\b\s*=\s*{{\s*({NUMBER})\s*,\s*({NUMBER})\s*,\s*({NUMBER})\s*}}",
    re.I,
)
ORIENTATION_RE = re.compile(
    rf"\[['\"]orientation['\"]\]\s*=\s*VECTOR3\(\s*({NUMBER})\s*,\s*({NUMBER})\s*,\s*({NUMBER})\s*\)",
    re.I,
)
ORIENTATION_BRACE_RE = re.compile(
    rf"\bOrientation\b\s*=\s*{{\s*({NUMBER})\s*,\s*({NUMBER})\s*,\s*({NUMBER})\s*}}",
    re.I,
)
BLUEPRINT_RE = re.compile(
    r"(?:\[['\"](?:type|blueprint|Blueprint)['\"]\]|(?:type|blueprint|Blueprint))\s*=\s*['\"]([^'\"]+)['\"]",
    re.I,
)
ARMY_BLOCK_RE = re.compile(r"\['(?P<army>ARMY_\d+|NEUTRAL_CIVILIAN)'\]\s*=\s*{", re.I)
MARKER_START_RE = re.compile(r"\['(?P<name>[^'\"]+)'\]\s*=\s*{")
GROUP_START_RE = re.compile(r"\['(?P<name>[^'\"]+)'\]\s*=\s*GROUP\s*{")
UNIT_START_RE = re.compile(r"\['(?P<name>UNIT_[^'\"]*)'\]\s*=\s*{", re.I)
RECTANGLE_RE = re.compile(
    rf"RECTANGLE\(\s*({NUMBER})\s*,\s*({NUMBER})\s*,\s*({NUMBER})\s*,\s*({NUMBER})\s*\)",
    re.I,
)

RECLAIM_HINTS = ("tree", "rock", "boulder", "wreck", "reclaim", "log", "debris")
CIVILIAN_HINTS = ("civilian", "/civilian/", "uec", "uac", "urb", "xsc", "xec")
BUILDING_HINTS = ("uab", "ueb", "urb", "xsb", "ueb5", "uab5", "urb5", "building")


@dataclass(frozen=True)
class Point3:
    x: float
    y: float
    z: float


@dataclass
class MarkerEntity:
    name: str
    marker_type: str
    position: Point3 | None = None
    prop: str = ""


@dataclass
class UnitEntity:
    army: str
    name: str
    blueprint: str
    position: Point3 | None = None
    orientation: Point3 | None = None
    kind: str = "unit"
    group_path: list[str] = field(default_factory=list)


@dataclass
class AreaEntity:
    name: str
    rectangle: list[float] = field(default_factory=list)


def _read_text(path: Path | None) -> tuple[str, str | None]:
    if path is None:
        return "", "missing_file"
    try:
        return path.read_text(encoding="utf-8", errors="replace"), None
    except OSError as exc:
        return "", f"failed_to_read_{path.name}: {exc}"


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


def _block_end(text: str, open_brace_index: int) -> int:
    depth = 0
    in_string: str | None = None
    index = open_brace_index
    while index < len(text):
        char = text[index]
        if in_string:
            if char == "\\":
                index += 2
                continue
            if char == in_string:
                in_string = None
        elif char in ("'", '"'):
            in_string = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index + 1
        index += 1
    return len(text)


def _named_blocks(text: str, start_re: re.Pattern[str]) -> list[tuple[str, str]]:
    blocks: list[tuple[str, str]] = []
    for name, block, _, _ in _named_blocks_with_spans(text, start_re):
        blocks.append((name, block))
    return blocks


def _named_blocks_with_spans(
    text: str, start_re: re.Pattern[str]
) -> list[tuple[str, str, int, int]]:
    blocks: list[tuple[str, str, int, int]] = []
    for match in start_re.finditer(text):
        open_index = text.find("{", match.end() - 1)
        if open_index == -1:
            continue
        end_index = _block_end(text, open_index)
        blocks.append((match.group("name"), text[open_index:end_index], match.start(), end_index))
    return blocks


def _section_block(text: str, section_name: str) -> str:
    match = re.search(rf"\b{re.escape(section_name)}\s*=\s*{{", text)
    if not match:
        return ""
    open_index = text.find("{", match.end() - 1)
    return text[open_index : _block_end(text, open_index)]


def _master_markers_block(text: str) -> str:
    markers_match = re.search(r"\bMarkers\s*=\s*{", text)
    if not markers_match:
        return ""
    open_index = text.find("{", markers_match.end() - 1)
    return text[open_index : _block_end(text, open_index)]


def _point_from_match(match: re.Match[str] | None) -> Point3 | None:
    if not match:
        return None
    return Point3(float(match.group(1)), float(match.group(2)), float(match.group(3)))


def _position_from_block(block: str) -> Point3 | None:
    return _point_from_match(POSITION_RE.search(block) or POSITION_BRACE_RE.search(block))


def _orientation_from_block(block: str) -> Point3 | None:
    return _point_from_match(ORIENTATION_RE.search(block) or ORIENTATION_BRACE_RE.search(block))


def _parse_markers(text: str) -> list[MarkerEntity]:
    markers_block = _master_markers_block(text)
    if not markers_block:
        return []

    markers: list[MarkerEntity] = []
    for name, block in _named_blocks(markers_block, MARKER_START_RE):
        type_match = TYPE_RE.search(block)
        if not type_match:
            continue
        prop_match = PROP_RE.search(block)
        markers.append(
            MarkerEntity(
                name=name,
                marker_type=type_match.group(1),
                position=_point_from_match(POSITION_RE.search(block)),
                prop=prop_match.group(1) if prop_match else "",
            )
        )
    return markers


def _parse_areas(text: str) -> list[AreaEntity]:
    areas_block = _section_block(text, "Areas")
    areas: list[AreaEntity] = []
    for name, block in _named_blocks(areas_block, MARKER_START_RE):
        rectangle_match = RECTANGLE_RE.search(block)
        rectangle = [float(value) for value in rectangle_match.groups()] if rectangle_match else []
        areas.append(AreaEntity(name=name, rectangle=rectangle))
    return areas


def _context_has_any(values: list[str], hints: tuple[str, ...]) -> bool:
    joined = " ".join(values).lower()
    return any(hint in joined for hint in hints)


def _classify_blueprint(
    blueprint: str,
    army: str,
    name: str = "",
    group_path: list[str] | None = None,
) -> str:
    lower = blueprint.lower()
    context = [name, *(group_path or [])]
    if any(hint in lower for hint in RECLAIM_HINTS) or _context_has_any(context, RECLAIM_HINTS):
        return "reclaim"
    if (
        "civilian" in army.lower()
        or any(hint in lower for hint in CIVILIAN_HINTS)
        or _context_has_any(context, ("civilian",))
    ):
        if any(hint in lower for hint in BUILDING_HINTS):
            return "civilian_building"
        return "civilian_unit"
    if any(hint in lower for hint in BUILDING_HINTS):
        return "building"
    return "unit"


def _army_for_index(text: str, index: int) -> str:
    army = ""
    for match in ARMY_BLOCK_RE.finditer(text, 0, index):
        army = match.group("army")
    return army


def _group_path_for_index(
    group_spans: list[tuple[str, str, int, int]], index: int
) -> list[str]:
    return [name for name, _, start, end in group_spans if start <= index < end]


def _parse_units(text: str) -> list[UnitEntity]:
    units: list[UnitEntity] = []
    group_spans = _named_blocks_with_spans(text, GROUP_START_RE)
    for name, block, start, _ in _named_blocks_with_spans(text, UNIT_START_RE):
        blueprint_match = BLUEPRINT_RE.search(block)
        if not blueprint_match:
            continue
        army = _army_for_index(text, start)
        blueprint = blueprint_match.group(1)
        group_path = _group_path_for_index(group_spans, start)
        units.append(
            UnitEntity(
                army=army,
                name=name,
                blueprint=blueprint,
                position=_position_from_block(block),
                orientation=_orientation_from_block(block),
                kind=_classify_blueprint(blueprint, army, name=name, group_path=group_path),
                group_path=group_path,
            )
        )
    return units


def _parse_props(text: str) -> list[UnitEntity]:
    props: list[UnitEntity] = []
    props_block = _section_block(text, "Props")
    for name, block in _named_blocks(props_block, MARKER_START_RE):
        string_values = {
            match.group("key"): match.group("value") for match in STRING_VALUE_RE.finditer(block)
        }
        blueprint = (
            string_values.get("prop")
            or string_values.get("type")
            or string_values.get("blueprint")
            or ""
        )
        if not blueprint:
            blueprint_match = BLUEPRINT_RE.search(block)
            blueprint = blueprint_match.group(1) if blueprint_match else ""
        if not blueprint:
            continue
        props.append(
            UnitEntity(
                army="PROP",
                name=name,
                blueprint=blueprint,
                position=_position_from_block(block) or _point_from_match(VECTOR3_RE.search(block)),
                orientation=_orientation_from_block(block),
                kind=_classify_blueprint(blueprint, "PROP", name=name),
            )
        )
    return props


def _positions(items: list[MarkerEntity | UnitEntity]) -> list[dict[str, float | str]]:
    output = []
    for item in items:
        if item.position is None:
            continue
        record: dict[str, float | str] = {
            "name": item.name,
            "x": item.position.x,
            "y": item.position.y,
            "z": item.position.z,
        }
        if isinstance(item, MarkerEntity):
            record["type"] = item.marker_type
        else:
            record["blueprint"] = item.blueprint
            record["army"] = item.army
            record["kind"] = item.kind
            record["group_path"] = "/".join(item.group_path)
        output.append(record)
    return output


def _team_counts_from_scenario(text: str) -> tuple[int | None, list[int]]:
    team_sizes: list[int] = []
    team_re = r"\{\s*name\s*=\s*['\"][^'\"]+['\"].*?armies\s*=\s*{(.*?)}"
    for team_block in re.findall(team_re, text, re.I | re.S):
        armies = re.findall(r"ARMY_\d+", team_block, re.I)
        if armies:
            team_sizes.append(len(set(armies)))
    return (len(team_sizes) if team_sizes else None), team_sizes


def parse_map_entities(map_record: dict[str, Any], maps_root: Path) -> dict[str, Any]:
    warnings: list[str] = []
    scenario_text, scenario_warning = _read_text(_first_path(map_record, "scenario_lua", maps_root))
    save_text, save_warning = _read_text(_first_path(map_record, "save_lua", maps_root))
    if scenario_warning:
        warnings.append(f"scenario:{scenario_warning}")
    if save_warning:
        warnings.append(f"save:{save_warning}")

    markers = _parse_markers(save_text)
    units = _parse_units(save_text)
    props = _parse_props(save_text)
    areas = _parse_areas(save_text)

    marker_counts = Counter(marker.marker_type for marker in markers)
    unit_blueprints = Counter(unit.blueprint for unit in units)
    prop_blueprints = Counter(prop.blueprint for prop in props)
    unit_kinds = Counter(unit.kind for unit in units)
    prop_kinds = Counter(prop.kind for prop in props)
    reclaim_entities = [unit for unit in [*units, *props] if unit.kind == "reclaim"]
    civilian_units = [unit for unit in units if unit.kind == "civilian_unit"]
    civilian_buildings = [unit for unit in units if unit.kind == "civilian_building"]
    team_count, team_sizes = _team_counts_from_scenario(scenario_text)

    return {
        "map_dir": map_record.get("top_level_dir") or map_record.get("map_dir") or "",
        "selected_map_dir": map_record.get("selected_map_dir", ""),
        "team_count_declared": team_count,
        "team_sizes_declared": team_sizes,
        "area_count": len(areas),
        "areas": [asdict(area) for area in areas],
        "marker_count": len(markers),
        "marker_type_counts": dict(sorted(marker_counts.items())),
        "spawn_positions": _positions(
            [marker for marker in markers if marker.name.upper().startswith("ARMY_")]
        ),
        "mex_positions": _positions([marker for marker in markers if marker.marker_type == "Mass"]),
        "hydro_positions": _positions(
            [marker for marker in markers if marker.marker_type == "Hydrocarbon"]
        ),
        "unit_count": len(units),
        "unit_kind_counts": dict(sorted(unit_kinds.items())),
        "unit_blueprint_counts": dict(sorted(unit_blueprints.items())),
        "prop_count": len(props),
        "prop_kind_counts": dict(sorted(prop_kinds.items())),
        "prop_blueprint_counts": dict(sorted(prop_blueprints.items())),
        "reclaim_entity_count": len(reclaim_entities),
        "reclaim_entity_positions": _positions(reclaim_entities),
        "reclaim_entity_type_counts": dict(
            sorted(Counter(entity.blueprint for entity in reclaim_entities).items())
        ),
        "civilian_unit_count": len(civilian_units),
        "civilian_unit_positions": _positions(civilian_units),
        "civilian_building_count": len(civilian_buildings),
        "civilian_building_positions": _positions(civilian_buildings),
        "civilian_type_counts": dict(
            sorted(
                Counter(
                    entity.blueprint for entity in [*civilian_units, *civilian_buildings]
                ).items()
            )
        ),
        "warnings": warnings,
    }


def extract_entities(inventory: dict[str, Any]) -> list[dict[str, Any]]:
    maps_root = Path(inventory["maps_root"])
    return [parse_map_entities(map_record, maps_root) for map_record in inventory.get("maps", [])]


SUMMARY_COLUMNS = [
    "map_dir",
    "selected_map_dir",
    "team_count_declared",
    "team_sizes_declared",
    "area_count",
    "marker_count",
    "spawn_count",
    "mex_count",
    "hydro_count",
    "spawn_positions_json",
    "mex_positions_json",
    "hydro_positions_json",
    "unit_count",
    "prop_count",
    "reclaim_entity_count",
    "reclaim_entity_positions_json",
    "civilian_unit_count",
    "civilian_unit_positions_json",
    "civilian_building_count",
    "civilian_building_positions_json",
    "marker_type_counts_json",
    "unit_kind_counts_json",
    "prop_kind_counts_json",
    "reclaim_entity_type_counts_json",
    "civilian_type_counts_json",
    "warnings",
]


def _summary_row(record: dict[str, Any]) -> dict[str, Any]:
    marker_counts = record["marker_type_counts"]
    return {
        "map_dir": record["map_dir"],
        "selected_map_dir": record["selected_map_dir"],
        "team_count_declared": record["team_count_declared"] or "",
        "team_sizes_declared": "|".join(str(size) for size in record["team_sizes_declared"]),
        "area_count": record["area_count"],
        "marker_count": record["marker_count"],
        "spawn_count": len(record["spawn_positions"]),
        "mex_count": marker_counts.get("Mass", 0),
        "hydro_count": marker_counts.get("Hydrocarbon", 0),
        "spawn_positions_json": json.dumps(record["spawn_positions"], sort_keys=True),
        "mex_positions_json": json.dumps(record["mex_positions"], sort_keys=True),
        "hydro_positions_json": json.dumps(record["hydro_positions"], sort_keys=True),
        "unit_count": record["unit_count"],
        "prop_count": record["prop_count"],
        "reclaim_entity_count": record["reclaim_entity_count"],
        "reclaim_entity_positions_json": json.dumps(
            record["reclaim_entity_positions"], sort_keys=True
        ),
        "civilian_unit_count": record["civilian_unit_count"],
        "civilian_unit_positions_json": json.dumps(
            record["civilian_unit_positions"], sort_keys=True
        ),
        "civilian_building_count": record["civilian_building_count"],
        "civilian_building_positions_json": json.dumps(
            record["civilian_building_positions"], sort_keys=True
        ),
        "marker_type_counts_json": json.dumps(marker_counts, sort_keys=True),
        "unit_kind_counts_json": json.dumps(record["unit_kind_counts"], sort_keys=True),
        "prop_kind_counts_json": json.dumps(record["prop_kind_counts"], sort_keys=True),
        "reclaim_entity_type_counts_json": json.dumps(
            record["reclaim_entity_type_counts"], sort_keys=True
        ),
        "civilian_type_counts_json": json.dumps(record["civilian_type_counts"], sort_keys=True),
        "warnings": "|".join(record["warnings"]),
    }


def write_jsonl(records: list[dict[str, Any]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def write_summary_csv(records: list[dict[str, Any]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SUMMARY_COLUMNS)
        writer.writeheader()
        writer.writerows(_summary_row(record) for record in records)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract V1 marker, unit, prop, civilian, and reclaim entities from Lua files."
    )
    parser.add_argument(
        "--inventory",
        required=True,
        type=Path,
        help="Canonical inventory JSON generated by supmapai.extract.canonical_inventory.",
    )
    parser.add_argument(
        "--out",
        required=True,
        type=Path,
        help="Detailed JSONL output path.",
    )
    parser.add_argument(
        "--summary-out",
        type=Path,
        help="Optional flat CSV summary output path.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    inventory = json.loads(args.inventory.read_text(encoding="utf-8-sig"))
    records = extract_entities(inventory)
    write_jsonl(records, args.out)
    if args.summary_out:
        write_summary_csv(records, args.summary_out)
    print(f"Wrote {len(records)} Lua entity record(s) to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
