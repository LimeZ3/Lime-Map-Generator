"""Extract dense prop/reclaim objects from Supreme Commander .scmap files."""

from __future__ import annotations

import argparse
import csv
import json
import math
import struct
import time
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

CSV_COLUMNS = [
    "map_dir",
    "selected_map_dir",
    "scmap_path",
    "decode_ms",
    "scmap_version",
    "map_width",
    "map_height",
    "prop_count",
    "tree_prop_count",
    "rock_prop_count",
    "boulder_prop_count",
    "reclaim_prop_count",
    "other_prop_count",
    "prop_type_counts_json",
    "prop_path_counts_json",
    "warnings",
]

TERRAIN_TEXTURE_COUNT = 10
TERRAIN_NORMAL_COUNT = 9
WAVE_NORMAL_COUNT = 4


@dataclass(frozen=True)
class ScmapProp:
    path: str
    x: float
    y: float
    z: float
    rotation: float
    kind: str


class BinaryReader:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.offset = 0

    def remaining(self) -> int:
        return len(self.data) - self.offset

    def skip(self, count: int) -> None:
        if count < 0 or self.offset + count > len(self.data):
            raise ValueError(f"Attempted to skip beyond file at offset {self.offset}")
        self.offset += count

    def read_u8(self) -> int:
        if self.offset + 1 > len(self.data):
            raise ValueError(f"Unexpected EOF at offset {self.offset}")
        value = self.data[self.offset]
        self.offset += 1
        return value

    def read_i16(self) -> int:
        value = struct.unpack_from("<h", self.data, self.offset)[0]
        self.offset += 2
        return value

    def read_i32(self) -> int:
        value = struct.unpack_from("<i", self.data, self.offset)[0]
        self.offset += 4
        return value

    def read_f32(self) -> float:
        value = struct.unpack_from("<f", self.data, self.offset)[0]
        self.offset += 4
        return value

    def read_vec2(self) -> tuple[float, float]:
        return (self.read_f32(), self.read_f32())

    def read_vec3(self) -> tuple[float, float, float]:
        return (self.read_f32(), self.read_f32(), self.read_f32())

    def read_vec4(self) -> tuple[float, float, float, float]:
        return (self.read_f32(), self.read_f32(), self.read_f32(), self.read_f32())

    def read_string_null(self) -> str:
        start = self.offset
        while self.offset < len(self.data) and self.data[self.offset] != 0:
            self.offset += 1
        if self.offset >= len(self.data):
            raise ValueError(f"Unterminated string at offset {start}")
        value = self.data[start : self.offset].decode("ascii", errors="replace")
        self.offset += 1
        return value

    def read_string(self, length: int) -> str:
        if length < 0 or self.offset + length > len(self.data):
            raise ValueError(f"Invalid string length {length} at offset {self.offset}")
        value = self.data[self.offset : self.offset + length].decode("ascii", errors="replace")
        self.offset += length
        return value


def _skip_raw_image(reader: BinaryReader) -> None:
    byte_count = reader.read_i32() - 128
    reader.skip(128 + byte_count)


def _skip_compressed_image(reader: BinaryReader) -> None:
    byte_count = reader.read_i32() - 128
    reader.skip(128 + byte_count)


def _skip_lighting(reader: BinaryReader) -> None:
    reader.read_f32()
    for _ in range(4):
        reader.read_vec3()
    reader.read_vec4()
    reader.read_f32()
    reader.read_vec3()
    reader.read_f32()
    reader.read_f32()


def _skip_water(reader: BinaryReader) -> None:
    reader.read_u8()
    reader.read_f32()
    reader.read_f32()
    reader.read_f32()
    reader.read_vec3()
    reader.read_vec2()
    for _ in range(7):
        reader.read_f32()
    reader.read_vec3()
    reader.read_vec3()
    reader.read_f32()
    reader.read_f32()
    reader.read_string_null()
    reader.read_string_null()
    for _ in range(WAVE_NORMAL_COUNT):
        reader.read_f32()
    for _ in range(WAVE_NORMAL_COUNT):
        reader.read_vec2()
        reader.read_string_null()


def _skip_wave_generator(reader: BinaryReader) -> None:
    reader.read_string_null()
    reader.read_string_null()
    reader.read_vec3()
    reader.read_f32()
    reader.read_vec3()
    for _ in range(10):
        reader.read_f32()


def _skip_decal(reader: BinaryReader) -> None:
    reader.read_i32()
    reader.read_i32()
    texture_count = reader.read_i32()
    if texture_count < 0 or texture_count > 16:
        raise ValueError(f"Unreasonable decal texture count: {texture_count}")
    for _ in range(texture_count):
        reader.read_string(reader.read_i32())
    reader.read_vec3()
    reader.read_vec3()
    reader.read_vec3()
    reader.read_f32()
    reader.read_f32()
    reader.read_i32()


def _skip_decal_group(reader: BinaryReader) -> None:
    reader.read_i32()
    reader.read_string_null()
    length = reader.read_i32()
    if length < 0:
        raise ValueError(f"Invalid decal group length: {length}")
    reader.skip(length * 4)


def _skip_skybox(reader: BinaryReader) -> None:
    reader.read_vec3()
    for _ in range(3):
        reader.read_f32()
    reader.read_i32()
    reader.read_i32()
    reader.read_f32()
    reader.read_vec3()
    reader.read_vec3()
    reader.read_f32()
    reader.read_string_null()
    reader.read_string_null()

    planet_count = reader.read_i32()
    if planet_count < 0 or planet_count > 1024:
        raise ValueError(f"Unreasonable skybox planet count: {planet_count}")
    for _ in range(planet_count):
        reader.read_vec3()
        reader.read_f32()
        reader.read_vec2()
        reader.read_vec4()

    reader.skip(3)
    reader.read_f32()
    reader.read_vec3()
    reader.read_string_null()
    cirrus_layer_count = reader.read_i32()
    if cirrus_layer_count < 0 or cirrus_layer_count > 1024:
        raise ValueError(f"Unreasonable cirrus layer count: {cirrus_layer_count}")
    for _ in range(cirrus_layer_count):
        reader.read_vec2()
        reader.read_f32()
        reader.read_vec2()
    reader.read_f32()


def _classify_prop(path: str) -> str:
    lower = path.lower()
    if "tree" in lower or "/trees/" in lower:
        return "tree"
    if "boulder" in lower:
        return "boulder"
    if "rock" in lower:
        return "rock"
    if any(token in lower for token in ("reclaim", "wreck", "debris", "log")):
        return "reclaim"
    return "other"


def _read_prop(reader: BinaryReader) -> ScmapProp:
    path = reader.read_string_null()
    x, y, z = reader.read_vec3()
    rotation_x = reader.read_vec3()
    reader.read_vec3()
    reader.read_vec3()
    reader.read_vec3()
    rotation = math.atan2(rotation_x[2], rotation_x[0])
    return ScmapProp(
        path=path,
        x=round(float(x), 4),
        y=round(float(y), 4),
        z=round(float(z), 4),
        rotation=round(float(rotation), 6),
        kind=_classify_prop(path),
    )


def read_scmap_props(scmap_path: Path) -> tuple[dict[str, Any], list[ScmapProp]]:
    started = time.perf_counter()
    data = scmap_path.read_bytes()
    reader = BinaryReader(data)
    warnings: list[str] = []

    if data[:4] != b"Map\x1a":
        raise ValueError(f"Unrecognized .scmap header: {scmap_path}")

    reader.read_i32()
    reader.read_i32()
    reader.read_i32()
    reader.read_i32()
    reader.read_f32()
    reader.read_f32()
    reader.read_i32()
    reader.read_i16()
    _skip_raw_image(reader)

    version = reader.read_i32()
    if version not in (52, 53, 56, 60):
        warnings.append(f"unsupported_scmap_version_{version}")

    width = reader.read_i32()
    height = reader.read_i32()
    reader.read_f32()
    reader.skip((width + 1) * (height + 1) * 2)
    if version < 56:
        warnings.append(f"old_scmap_version_{version}_modern_prop_section_not_decoded")
        decoded_ms = (time.perf_counter() - started) * 1000
        return (
            {
                "scmap_path": str(scmap_path),
                "decode_ms": round(decoded_ms, 3),
                "scmap_version": version,
                "map_width": width,
                "map_height": height,
                "warnings": warnings,
            },
            [],
        )
    if version >= 56:
        reader.read_u8()

    reader.read_string_null()
    reader.read_string_null()
    reader.read_string_null()
    cube_map_count = reader.read_i32()
    if cube_map_count < 0 or cube_map_count > 1024:
        raise ValueError(f"Unreasonable cube map count: {cube_map_count}")
    for _ in range(cube_map_count):
        reader.read_string_null()
        reader.read_string_null()

    _skip_lighting(reader)
    _skip_water(reader)

    wave_generator_count = reader.read_i32()
    if wave_generator_count < 0 or wave_generator_count > 500000:
        raise ValueError(f"Unreasonable wave generator count: {wave_generator_count}")
    for _ in range(wave_generator_count):
        _skip_wave_generator(reader)

    for _ in range(6):
        reader.read_i32()

    if version > 56:
        reader.read_f32()

    for _ in range(TERRAIN_TEXTURE_COUNT):
        reader.read_string_null()
        reader.read_f32()
    for _ in range(TERRAIN_NORMAL_COUNT):
        reader.read_string_null()
        reader.read_f32()

    reader.read_i32()
    reader.read_i32()

    decal_count = reader.read_i32()
    if decal_count < 0 or decal_count > 250000:
        raise ValueError(f"Unreasonable decal count: {decal_count}")
    for _ in range(decal_count):
        _skip_decal(reader)

    decal_group_count = reader.read_i32()
    if decal_group_count < 0 or decal_group_count > 250000:
        raise ValueError(f"Unreasonable decal group count: {decal_group_count}")
    for _ in range(decal_group_count):
        _skip_decal_group(reader)

    reader.read_i32()
    reader.read_i32()

    normal_map_count = reader.read_i32()
    if normal_map_count != 1:
        warnings.append(f"unexpected_normal_map_count_{normal_map_count}")
    _skip_compressed_image(reader)
    _skip_raw_image(reader)
    _skip_raw_image(reader)

    water_map_count = reader.read_i32()
    if water_map_count != 1:
        warnings.append(f"unexpected_water_map_count_{water_map_count}")
    _skip_compressed_image(reader)
    half_size = (height // 2) * (width // 2)
    reader.skip(half_size)
    reader.skip(half_size)
    reader.skip(half_size)
    reader.skip(width * height)

    if version >= 60:
        _skip_skybox(reader)

    prop_count = reader.read_i32()
    if prop_count < 0 or prop_count > 2_000_000:
        raise ValueError(f"Unreasonable prop count: {prop_count}")
    props = [_read_prop(reader) for _ in range(prop_count)]

    decoded_ms = (time.perf_counter() - started) * 1000
    metadata = {
        "scmap_path": str(scmap_path),
        "decode_ms": round(decoded_ms, 3),
        "scmap_version": version,
        "map_width": width,
        "map_height": height,
        "warnings": warnings,
    }
    return metadata, props


def _file_entries(map_record: dict[str, Any], key: str) -> list[dict[str, Any]]:
    direct_entries = map_record.get(key)
    if direct_entries is not None:
        return direct_entries
    return map_record.get("files", {}).get(key, [])


def _first_scmap_path(map_record: dict[str, Any], maps_root: Path) -> Path | None:
    entries = _file_entries(map_record, "scmap")
    if not entries:
        return None
    return maps_root / Path(entries[0]["path"])


def _record_for_map(map_record: dict[str, Any], maps_root: Path) -> dict[str, Any]:
    map_dir = map_record.get("top_level_dir") or map_record.get("map_dir") or ""
    selected_map_dir = map_record.get("selected_map_dir", "")
    scmap_path = _first_scmap_path(map_record, maps_root)
    if scmap_path is None:
        return {
            "map_dir": map_dir,
            "selected_map_dir": selected_map_dir,
            "scmap_path": "",
            "props": [],
            "warnings": ["missing_scmap"],
        }

    try:
        metadata, props = read_scmap_props(scmap_path)
        return {
            "map_dir": map_dir,
            "selected_map_dir": selected_map_dir,
            **metadata,
            "props": [asdict(prop) for prop in props],
        }
    except Exception as exc:
        return {
            "map_dir": map_dir,
            "selected_map_dir": selected_map_dir,
            "scmap_path": str(scmap_path),
            "props": [],
            "warnings": [f"scmap_prop_decode_failed:{type(exc).__name__}:{exc}"],
        }


def extract_scmap_props(
    inventory: dict[str, Any],
    map_dir_filter: str | None,
    max_maps: int,
) -> list[dict[str, Any]]:
    maps_root = Path(inventory["maps_root"])
    maps = []
    for map_record in inventory.get("maps", []):
        map_dir = map_record.get("top_level_dir") or map_record.get("map_dir") or ""
        if map_dir_filter and map_dir != map_dir_filter:
            continue
        maps.append(map_record)
    if len(maps) > max_maps:
        raise ValueError(
            f"Refusing to decode {len(maps)} maps with --max-maps {max_maps}. "
            "Raise --max-maps deliberately for larger batches."
        )
    return [_record_for_map(map_record, maps_root) for map_record in maps]


def _summary_row(record: dict[str, Any]) -> dict[str, Any]:
    props = record.get("props", [])
    kind_counts = Counter(prop["kind"] for prop in props)
    path_counts = Counter(prop["path"] for prop in props)
    reclaim_count = sum(
        kind_counts.get(kind, 0) for kind in ("tree", "rock", "boulder", "reclaim")
    )
    return {
        "map_dir": record["map_dir"],
        "selected_map_dir": record.get("selected_map_dir", ""),
        "scmap_path": record.get("scmap_path", ""),
        "decode_ms": record.get("decode_ms", ""),
        "scmap_version": record.get("scmap_version", ""),
        "map_width": record.get("map_width", ""),
        "map_height": record.get("map_height", ""),
        "prop_count": len(props),
        "tree_prop_count": kind_counts.get("tree", 0),
        "rock_prop_count": kind_counts.get("rock", 0),
        "boulder_prop_count": kind_counts.get("boulder", 0),
        "reclaim_prop_count": reclaim_count,
        "other_prop_count": kind_counts.get("other", 0),
        "prop_type_counts_json": json.dumps(dict(sorted(kind_counts.items())), sort_keys=True),
        "prop_path_counts_json": json.dumps(dict(sorted(path_counts.items())), sort_keys=True),
        "warnings": "|".join(record.get("warnings", [])),
    }


def write_jsonl(records: list[dict[str, Any]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def write_summary_csv(records: list[dict[str, Any]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(_summary_row(record) for record in records)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract dense prop objects from .scmap files.")
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--map-dir", help="Canonical top-level map folder to decode.")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--summary-out", type=Path)
    parser.add_argument(
        "--max-maps",
        type=int,
        default=1,
        help="Safety limit. Defaults to 1 to avoid accidental large dataset runs.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    inventory = json.loads(args.inventory.read_text(encoding="utf-8-sig"))
    records = extract_scmap_props(inventory, args.map_dir, args.max_maps)
    write_jsonl(records, args.out)
    if args.summary_out:
        write_summary_csv(records, args.summary_out)
    print(f"Wrote {len(records)} SCMAP prop record(s) to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
