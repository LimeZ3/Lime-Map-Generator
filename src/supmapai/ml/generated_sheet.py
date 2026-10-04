"""Render generated tensor samples for visual QA."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont


def _to_uint8(array: np.ndarray) -> np.ndarray:
    finite = np.nan_to_num(array.astype(np.float32), nan=0.0, posinf=0.0, neginf=0.0)
    minimum = float(finite.min())
    maximum = float(finite.max())
    if maximum <= minimum:
        return np.zeros(finite.shape, dtype=np.uint8)
    return np.clip((finite - minimum) / (maximum - minimum) * 255, 0, 255).astype(np.uint8)


def _channel_image(channel: np.ndarray, size: int) -> Image.Image:
    return Image.fromarray(_to_uint8(channel), mode="L").convert("RGB").resize(
        (size, size),
        Image.Resampling.NEAREST,
    )


def _draw_label(draw: ImageDraw.ImageDraw, x: int, y: int, text: str) -> None:
    font = ImageFont.load_default()
    bbox = draw.textbbox((x, y), text, font=font)
    draw.rectangle((bbox[0] - 3, bbox[1] - 2, bbox[2] + 3, bbox[3] + 2), fill=(0, 0, 0))
    draw.text((x, y), text, fill=(255, 255, 255), font=font)


def render_generated_sheet(generated_npz: Path, out_path: Path, tile_size: int) -> None:
    archive = np.load(generated_npz)
    tensor = archive["tensor"]
    channels = (
        [str(item) for item in archive["channels"]]
        if "channels" in archive.files
        else [f"channel_{index:02d}" for index in range(tensor.shape[0])]
    )
    padding = 8
    label_height = 18
    width = tensor.shape[0] * tile_size + (tensor.shape[0] + 1) * padding
    height = tile_size + label_height + padding * 2
    sheet = Image.new("RGB", (width, height), (22, 24, 28))
    draw = ImageDraw.Draw(sheet)
    for channel_index, channel_name in enumerate(channels):
        x = padding + channel_index * (tile_size + padding)
        _draw_label(draw, x, padding, channel_name)
        sheet.paste(_channel_image(tensor[channel_index], tile_size), (x, padding + label_height))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_path)


def render_directory(input_dir: Path, out_dir: Path, max_items: int, tile_size: int) -> list[Path]:
    outputs = []
    paths = (
        sorted(input_dir.glob("*.generated.npz"))
        + sorted(input_dir.glob("*.full.npz"))
        + sorted(input_dir.glob("*.points.npz"))
    )
    for path in paths[:max_items]:
        out_path = out_dir / f"{path.stem}.png"
        render_generated_sheet(path, out_path, tile_size)
        outputs.append(out_path)
    return outputs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render generated tensor sample sheets.")
    parser.add_argument("--input-dir", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--max-items", default=8, type=int)
    parser.add_argument("--tile-size", default=160, type=int)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    outputs = render_directory(args.input_dir, args.out_dir, args.max_items, args.tile_size)
    print(f"Wrote {len(outputs)} generated sample sheet(s) to {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
