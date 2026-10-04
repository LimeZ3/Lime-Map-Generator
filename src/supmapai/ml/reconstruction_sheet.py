"""Render original/reconstruction/difference sheets for autoencoder QA."""

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


def render_reconstruction_sheet(
    reconstruction_npz: Path,
    out_path: Path,
    tile_size: int,
) -> None:
    archive = np.load(reconstruction_npz)
    original = archive["original"]
    reconstruction = archive["reconstruction"]
    difference = np.abs(original - reconstruction)
    channels = (
        [str(item) for item in archive["channels"]]
        if "channels" in archive.files
        else [f"channel_{index:02d}" for index in range(original.shape[0])]
    )
    row_names = ["original", "reconstruction", "abs_diff"]
    tensors = [original, reconstruction, difference]
    channel_count = original.shape[0]
    padding = 8
    label_height = 18
    width = channel_count * tile_size + (channel_count + 1) * padding
    height = len(tensors) * (tile_size + label_height) + (len(tensors) + 1) * padding
    sheet = Image.new("RGB", (width, height), (22, 24, 28))
    draw = ImageDraw.Draw(sheet)
    for row_index, tensor in enumerate(tensors):
        y = padding + row_index * (tile_size + label_height + padding)
        _draw_label(draw, padding, y, row_names[row_index])
        for channel_index in range(channel_count):
            x = padding + channel_index * (tile_size + padding)
            sheet.paste(_channel_image(tensor[channel_index], tile_size), (x, y + label_height))
            if row_index == 0:
                _draw_label(draw, x, y + label_height, channels[channel_index])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_path)


def render_directory(input_dir: Path, out_dir: Path, max_items: int, tile_size: int) -> list[Path]:
    outputs = []
    paths = (
        sorted(input_dir.glob("*.reconstruction.npz"))
        + sorted(input_dir.glob("*.terrain_reconstruction.npz"))
        + sorted(input_dir.glob("*.prediction.npz"))
    )
    for path in paths[:max_items]:
        out_path = out_dir / f"{path.stem}.png"
        render_reconstruction_sheet(path, out_path, tile_size)
        outputs.append(out_path)
    return outputs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render reconstruction QA sheets.")
    parser.add_argument("--input-dir", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--max-items", default=8, type=int)
    parser.add_argument("--tile-size", default=96, type=int)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    outputs = render_directory(args.input_dir, args.out_dir, args.max_items, args.tile_size)
    print(f"Wrote {len(outputs)} reconstruction sheet(s) to {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
