"""Export reclaim/civilian entity positions and QA previews."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

ENTITY_COLUMNS = [
    "map_dir",
    "source",
    "kind",
    "name",
    "blueprint",
    "army",
    "group_path",
    "x",
    "y",
    "z",
    "playable_x",
    "playable_z",
    "norm_x",
    "norm_z",
    "in_playable_area",
    "preview_path",
]

SUMMARY_COLUMNS = [
    "map_dir",
    "reclaim_entity_count",
    "scmap_prop_count",
    "tree_prop_count",
    "rock_prop_count",
    "boulder_prop_count",
    "scmap_reclaim_prop_count",
    "total_reclaim_entity_count",
    "civilian_unit_count",
    "civilian_building_count",
    "entities_in_playable_area",
    "entities_outside_playable_area",
    "entity_preview_path",
]


def _read_jsonl_by_map(path: Path) -> dict[str, dict[str, Any]]:
    records = {}
    with path.open(encoding="utf-8-sig") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            records[record["map_dir"]] = record
    return records


def _read_optional_jsonl_by_map(path: Path | None) -> dict[str, dict[str, Any]]:
    if path is None or not path.exists():
        return {}
    return _read_jsonl_by_map(path)


def _read_csv_by_map(path: Path) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return {row["map_dir"]: row for row in csv.DictReader(handle)}


def _float_value(row: dict[str, str], key: str, default: float = 0.0) -> float:
    try:
        return float(row.get(key, "") or default)
    except ValueError:
        return default


def _entity_groups(entity: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    return (
        ("reclaim", "reclaim_entity_positions"),
        ("civilian_unit", "civilian_unit_positions"),
        ("civilian_building", "civilian_building_positions"),
    )


def _entity_rows_for_map(
    map_dir: str,
    entity: dict[str, Any],
    terrain: dict[str, str],
    preview_path: str,
) -> list[dict[str, Any]]:
    x0 = _float_value(terrain, "playable_x0")
    z0 = _float_value(terrain, "playable_z0")
    width = max(_float_value(terrain, "playable_width"), 1.0)
    height = max(_float_value(terrain, "playable_height"), 1.0)
    x1 = x0 + width
    z1 = z0 + height

    rows = []
    for kind, key in _entity_groups(entity):
        for item in entity.get(key, []):
            x = float(item["x"])
            y = float(item["y"])
            z = float(item["z"])
            playable_x = x - x0
            playable_z = z - z0
            in_playable = x0 <= x < x1 and z0 <= z < z1
            rows.append(
                {
                    "map_dir": map_dir,
                    "source": "save_lua",
                    "kind": kind,
                    "name": item["name"],
                    "blueprint": item.get("blueprint", ""),
                    "army": item.get("army", ""),
                    "group_path": item.get("group_path", ""),
                    "x": round(x, 4),
                    "y": round(y, 4),
                    "z": round(z, 4),
                    "playable_x": round(playable_x, 4),
                    "playable_z": round(playable_z, 4),
                    "norm_x": round(playable_x / width, 6),
                    "norm_z": round(playable_z / height, 6),
                    "in_playable_area": str(in_playable).lower(),
                    "preview_path": preview_path,
                }
            )
    return rows


def _scmap_prop_rows_for_map(
    map_dir: str,
    scmap_props: dict[str, Any] | None,
    terrain: dict[str, str],
    preview_path: str,
) -> list[dict[str, Any]]:
    if not scmap_props:
        return []

    x0 = _float_value(terrain, "playable_x0")
    z0 = _float_value(terrain, "playable_z0")
    width = max(_float_value(terrain, "playable_width"), 1.0)
    height = max(_float_value(terrain, "playable_height"), 1.0)
    x1 = x0 + width
    z1 = z0 + height

    rows = []
    for index, prop in enumerate(scmap_props.get("props", [])):
        x = float(prop["x"])
        y = float(prop["y"])
        z = float(prop["z"])
        playable_x = x - x0
        playable_z = z - z0
        in_playable = x0 <= x < x1 and z0 <= z < z1
        rows.append(
            {
                "map_dir": map_dir,
                "source": "scmap",
                "kind": prop.get("kind", "prop"),
                "name": f"SCMAP_PROP_{index}",
                "blueprint": prop.get("path", ""),
                "army": "PROP",
                "group_path": "",
                "x": round(x, 4),
                "y": round(y, 4),
                "z": round(z, 4),
                "playable_x": round(playable_x, 4),
                "playable_z": round(playable_z, 4),
                "norm_x": round(playable_x / width, 6),
                "norm_z": round(playable_z / height, 6),
                "in_playable_area": str(in_playable).lower(),
                "preview_path": preview_path,
            }
        )
    return rows


def _draw_entity_preview(
    entity: dict[str, Any],
    scmap_props: dict[str, Any] | None,
    terrain: dict[str, str],
    out_path: Path,
) -> None:
    width = max(int(round(_float_value(terrain, "playable_width"))), 1)
    height = max(int(round(_float_value(terrain, "playable_height"))), 1)
    x0 = _float_value(terrain, "playable_x0")
    z0 = _float_value(terrain, "playable_z0")

    image = Image.new("RGB", (width, height), (28, 30, 34))
    draw = ImageDraw.Draw(image)

    styles = {
        "reclaim_entity_positions": ((245, 150, 45), 3, "circle"),
        "civilian_unit_positions": ((175, 120, 245), 5, "circle"),
        "civilian_building_positions": ((245, 80, 190), 5, "square"),
    }
    for key, (color, radius, shape) in styles.items():
        for item in entity.get(key, []):
            x = float(item["x"]) - x0
            z = float(item["z"]) - z0
            if not (0 <= x < width and 0 <= z < height):
                continue
            bounds = (x - radius, z - radius, x + radius, z + radius)
            if shape == "square":
                draw.rectangle(bounds, fill=color, outline=(255, 255, 255))
            else:
                draw.ellipse(bounds, fill=color, outline=(255, 255, 255))

    prop_styles = {
        "tree": ((60, 185, 90), 1),
        "rock": ((170, 165, 145), 1),
        "boulder": ((205, 185, 125), 1),
        "reclaim": ((245, 150, 45), 1),
        "other": ((120, 120, 120), 1),
    }
    if scmap_props:
        for prop in scmap_props.get("props", []):
            x = float(prop["x"]) - x0
            z = float(prop["z"]) - z0
            if not (0 <= x < width and 0 <= z < height):
                continue
            color, radius = prop_styles.get(prop.get("kind", "other"), prop_styles["other"])
            draw.rectangle((x - radius, z - radius, x + radius, z + radius), fill=color)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    max_size = 512
    scale = min(max_size / width, max_size / height, 1.0)
    out_size = (max(1, round(width * scale)), max(1, round(height * scale)))
    image.resize(out_size, Image.Resampling.NEAREST).save(out_path)


def export_entity_layers(
    entities_jsonl: Path,
    terrain_csv: Path,
    out_csv: Path,
    summary_out: Path | None,
    preview_dir: Path | None,
    scmap_props_jsonl: Path | None = None,
) -> None:
    entities = _read_jsonl_by_map(entities_jsonl)
    scmap_props_by_map = _read_optional_jsonl_by_map(scmap_props_jsonl)
    terrain_rows = _read_csv_by_map(terrain_csv)

    entity_rows = []
    summary_rows = []
    for map_dir, terrain in terrain_rows.items():
        entity = entities.get(map_dir)
        if entity is None:
            continue
        preview_path = ""
        scmap_props = scmap_props_by_map.get(map_dir)
        if preview_dir is not None:
            preview_path_obj = preview_dir / f"{map_dir}.entities.png"
            _draw_entity_preview(entity, scmap_props, terrain, preview_path_obj)
            preview_path = str(preview_path_obj)

        rows = _entity_rows_for_map(map_dir, entity, terrain, preview_path)
        rows.extend(_scmap_prop_rows_for_map(map_dir, scmap_props, terrain, preview_path))
        entity_rows.extend(rows)
        outside = sum(1 for row in rows if row["in_playable_area"] != "true")
        scmap_prop_count = len(scmap_props.get("props", [])) if scmap_props else 0
        scmap_kind_counts: dict[str, int] = {}
        if scmap_props:
            for prop in scmap_props.get("props", []):
                kind = prop.get("kind", "other")
                scmap_kind_counts[kind] = scmap_kind_counts.get(kind, 0) + 1
        scmap_reclaim_count = sum(
            scmap_kind_counts.get(kind, 0) for kind in ("tree", "rock", "boulder", "reclaim")
        )
        save_reclaim_count = len(entity.get("reclaim_entity_positions", []))
        summary_rows.append(
            {
                "map_dir": map_dir,
                "reclaim_entity_count": save_reclaim_count,
                "scmap_prop_count": scmap_prop_count,
                "tree_prop_count": scmap_kind_counts.get("tree", 0),
                "rock_prop_count": scmap_kind_counts.get("rock", 0),
                "boulder_prop_count": scmap_kind_counts.get("boulder", 0),
                "scmap_reclaim_prop_count": scmap_reclaim_count,
                "total_reclaim_entity_count": save_reclaim_count + scmap_reclaim_count,
                "civilian_unit_count": len(entity.get("civilian_unit_positions", [])),
                "civilian_building_count": len(entity.get("civilian_building_positions", [])),
                "entities_in_playable_area": len(rows) - outside,
                "entities_outside_playable_area": outside,
                "entity_preview_path": preview_path,
            }
        )

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=ENTITY_COLUMNS)
        writer.writeheader()
        writer.writerows(entity_rows)

    if summary_out is not None:
        summary_out.parent.mkdir(parents=True, exist_ok=True)
        with summary_out.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=SUMMARY_COLUMNS)
            writer.writeheader()
            writer.writerows(summary_rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export reclaim/civilian entity layers.")
    parser.add_argument("--entities-jsonl", required=True, type=Path)
    parser.add_argument("--terrain-csv", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--summary-out", type=Path)
    parser.add_argument("--preview-dir", type=Path)
    parser.add_argument("--scmap-props-jsonl", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    export_entity_layers(
        args.entities_jsonl,
        args.terrain_csv,
        args.out,
        args.summary_out,
        args.preview_dir,
        args.scmap_props_jsonl,
    )
    print(f"Wrote entity rows to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
