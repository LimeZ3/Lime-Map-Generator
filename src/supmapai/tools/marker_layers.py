"""Export exact spawn/mex/hydro positions and QA marker previews."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

MARKER_COLUMNS = [
    "map_dir",
    "kind",
    "name",
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
    "spawn_count",
    "mex_count",
    "hydro_count",
    "markers_in_playable_area",
    "markers_outside_playable_area",
    "marker_preview_path",
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


def _read_csv_by_map(path: Path) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return {row["map_dir"]: row for row in csv.DictReader(handle)}


def _float_value(row: dict[str, str], key: str, default: float = 0.0) -> float:
    try:
        return float(row.get(key, "") or default)
    except ValueError:
        return default


def _marker_rows_for_map(
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
    for kind, key in (
        ("spawn", "spawn_positions"),
        ("mex", "mex_positions"),
        ("hydro", "hydro_positions"),
    ):
        for marker in entity.get(key, []):
            x = float(marker["x"])
            y = float(marker["y"])
            z = float(marker["z"])
            playable_x = x - x0
            playable_z = z - z0
            in_playable = x0 <= x < x1 and z0 <= z < z1
            rows.append(
                {
                    "map_dir": map_dir,
                    "kind": kind,
                    "name": marker["name"],
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


def _draw_marker_preview(
    entity: dict[str, Any],
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
        "spawn_positions": ((235, 80, 80), 7),
        "mex_positions": ((245, 210, 70), 4),
        "hydro_positions": ((65, 205, 235), 6),
    }
    for key, (color, radius) in styles.items():
        for marker in entity.get(key, []):
            x = float(marker["x"]) - x0
            z = float(marker["z"]) - z0
            if not (0 <= x < width and 0 <= z < height):
                continue
            draw.ellipse(
                (x - radius, z - radius, x + radius, z + radius),
                fill=color,
                outline=(255, 255, 255),
            )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    max_size = 512
    scale = min(max_size / width, max_size / height, 1.0)
    out_size = (max(1, round(width * scale)), max(1, round(height * scale)))
    image.resize(out_size, Image.Resampling.NEAREST).save(out_path)


def export_marker_layers(
    entities_jsonl: Path,
    terrain_csv: Path,
    out_csv: Path,
    summary_out: Path | None,
    preview_dir: Path | None,
) -> None:
    entities = _read_jsonl_by_map(entities_jsonl)
    terrain_rows = _read_csv_by_map(terrain_csv)

    marker_rows = []
    summary_rows = []
    for map_dir, terrain in terrain_rows.items():
        entity = entities.get(map_dir)
        if entity is None:
            continue
        preview_path = ""
        if preview_dir is not None:
            preview_path_obj = preview_dir / f"{map_dir}.markers.png"
            _draw_marker_preview(entity, terrain, preview_path_obj)
            preview_path = str(preview_path_obj)

        rows = _marker_rows_for_map(map_dir, entity, terrain, preview_path)
        marker_rows.extend(rows)
        outside = sum(1 for row in rows if row["in_playable_area"] != "true")
        summary_rows.append(
            {
                "map_dir": map_dir,
                "spawn_count": len(entity.get("spawn_positions", [])),
                "mex_count": len(entity.get("mex_positions", [])),
                "hydro_count": len(entity.get("hydro_positions", [])),
                "markers_in_playable_area": len(rows) - outside,
                "markers_outside_playable_area": outside,
                "marker_preview_path": preview_path,
            }
        )

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MARKER_COLUMNS)
        writer.writeheader()
        writer.writerows(marker_rows)

    if summary_out is not None:
        summary_out.parent.mkdir(parents=True, exist_ok=True)
        with summary_out.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=SUMMARY_COLUMNS)
            writer.writeheader()
            writer.writerows(summary_rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export spawn/mex/hydro marker layers.")
    parser.add_argument("--entities-jsonl", required=True, type=Path)
    parser.add_argument("--terrain-csv", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--summary-out", type=Path)
    parser.add_argument("--preview-dir", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    export_marker_layers(
        args.entities_jsonl,
        args.terrain_csv,
        args.out,
        args.summary_out,
        args.preview_dir,
    )
    print(f"Wrote marker rows to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
