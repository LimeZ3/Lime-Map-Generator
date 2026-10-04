"""Build a small contact sheet from terrain preview PNGs."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from PIL import Image, ImageDraw


def build_contact_sheet(
    terrain_csv: Path,
    out_path: Path,
    preview_column: str = "preview_path",
    tile_size: int = 256,
    label_height: int = 54,
) -> None:
    rows = list(csv.DictReader(terrain_csv.open(encoding="utf-8-sig")))
    if not rows:
        raise ValueError(f"No rows found in {terrain_csv}")

    tiles = []
    for row in rows:
        preview_path = Path(row[preview_column])
        image = Image.open(preview_path).convert("RGB")
        scale = min(tile_size / image.width, tile_size / image.height, 1.0)
        image = image.resize(
            (max(1, round(image.width * scale)), max(1, round(image.height * scale))),
            Image.Resampling.BILINEAR,
        )
        tile = Image.new("RGB", (tile_size, tile_size + label_height), "white")
        tile.paste(image, ((tile_size - image.width) // 2, (tile_size - image.height) // 2))

        draw = ImageDraw.Draw(tile)
        label_source = row.get("map_dir") or row.get("sample_stem") or row.get("sample") or preview_path.stem
        label = str(label_source).replace("_", " ")[:34]
        water = row.get("water_percent", "")
        buildable = row.get("buildable_percent", "")
        level = row.get("water_level", "")
        depth = row.get("water_depth_max", "")
        spawn_count = row.get("spawn_count", "")
        mex_count = row.get("mex_count", "")
        hydro_count = row.get("hydro_count", "")
        reclaim_count = row.get("total_reclaim_entity_count") or row.get("reclaim_entity_count", "")
        civilian_unit_count = row.get("civilian_unit_count", "")
        civilian_building_count = row.get("civilian_building_count", "")
        draw.text((4, tile_size + 8), label, fill="black")
        if water and buildable:
            subtitle = f"water {float(water):.1f}% build {float(buildable):.1f}%"
        elif water or level or depth:
            subtitle = f"water {water}% level {level} maxd {depth}"
        elif spawn_count or mex_count or hydro_count:
            subtitle = f"spawns {spawn_count} mex {mex_count} hydro {hydro_count}"
        elif reclaim_count or civilian_unit_count or civilian_building_count:
            subtitle = (
                f"reclaim {reclaim_count} civu {civilian_unit_count} "
                f"civb {civilian_building_count}"
            )
        else:
            subtitle = ""
        draw.text((4, tile_size + 28), subtitle, fill="black")
        tiles.append(tile)

    sheet = Image.new("RGB", (tile_size * len(tiles), tile_size + label_height), "white")
    for index, tile in enumerate(tiles):
        sheet.paste(tile, (index * tile_size, 0))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a terrain preview contact sheet.")
    parser.add_argument("--terrain-csv", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--preview-column", default="preview_path")
    parser.add_argument("--tile-size", default=256, type=int)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    build_contact_sheet(args.terrain_csv, args.out, args.preview_column, args.tile_size)
    print(f"Wrote contact sheet to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
