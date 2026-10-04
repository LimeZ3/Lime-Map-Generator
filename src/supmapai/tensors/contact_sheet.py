"""Render tensor channel contact sheets for visual QA."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont


def _read_manifest(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _to_uint8(array: np.ndarray) -> np.ndarray:
    finite = np.nan_to_num(array.astype(np.float32), nan=0.0, posinf=0.0, neginf=0.0)
    minimum = float(finite.min())
    maximum = float(finite.max())
    if maximum <= minimum:
        return np.zeros(finite.shape, dtype=np.uint8)
    return np.clip((finite - minimum) / (maximum - minimum) * 255, 0, 255).astype(np.uint8)


def _channel_image(channel: np.ndarray, size: int) -> Image.Image:
    image = Image.fromarray(_to_uint8(channel), mode="L").convert("RGB")
    return image.resize((size, size), Image.Resampling.NEAREST)


def _draw_label(draw: ImageDraw.ImageDraw, x: int, y: int, text: str) -> None:
    font = ImageFont.load_default()
    bbox = draw.textbbox((x, y), text, font=font)
    draw.rectangle((bbox[0] - 3, bbox[1] - 2, bbox[2] + 3, bbox[3] + 2), fill=(0, 0, 0))
    draw.text((x, y), text, fill=(255, 255, 255), font=font)


def render_tensor_sheet(
    tensor_path: Path,
    out_path: Path,
    tile_size: int,
    columns: int,
) -> None:
    archive = np.load(tensor_path)
    tensor = archive["tensor"]
    channels = [str(item) for item in archive["channels"]]
    rows = int(np.ceil(len(channels) / columns))
    padding = 10
    label_height = 18
    width = columns * tile_size + (columns + 1) * padding
    height = rows * (tile_size + label_height) + (rows + 1) * padding
    sheet = Image.new("RGB", (width, height), (22, 24, 28))
    draw = ImageDraw.Draw(sheet)
    for index, channel_name in enumerate(channels):
        row = index // columns
        column = index % columns
        x = padding + column * (tile_size + padding)
        y = padding + row * (tile_size + label_height + padding)
        sheet.paste(_channel_image(tensor[index], tile_size), (x, y + label_height))
        _draw_label(draw, x, y, channel_name)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_path)


def render_manifest_sheets(
    manifest_path: Path,
    out_dir: Path,
    max_maps: int,
    tile_size: int,
    columns: int,
) -> list[Path]:
    rows = _read_manifest(manifest_path)
    outputs = []
    for row in rows[:max_maps]:
        tensor_path_text = row.get("tensor_path", "")
        if not tensor_path_text:
            continue
        tensor_path = Path(tensor_path_text)
        out_path = out_dir / f"{row.get('map_id') or tensor_path.stem}.tensor_sheet.png"
        render_tensor_sheet(tensor_path, out_path, tile_size=tile_size, columns=columns)
        outputs.append(out_path)
    return outputs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render tensor channel contact sheets.")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--max-maps", default=10, type=int)
    parser.add_argument("--tile-size", default=160, type=int)
    parser.add_argument("--columns", default=4, type=int)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    outputs = render_manifest_sheets(
        manifest_path=args.manifest,
        out_dir=args.out_dir,
        max_maps=args.max_maps,
        tile_size=args.tile_size,
        columns=args.columns,
    )
    print(f"Wrote {len(outputs)} tensor contact sheet(s) to {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
