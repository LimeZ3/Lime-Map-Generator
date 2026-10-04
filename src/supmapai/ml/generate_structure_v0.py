"""Build complete V0 structural tensors from generated terrain samples."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from supmapai.ml.rule_place_points import place_points
from supmapai.ml.rule_place_reclaim import place_reclaim


def _write_npz(path: Path, tensor: np.ndarray, channels: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, tensor=tensor.astype(np.float32), channels=np.array(channels))


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def generate_one(
    terrain_path: Path,
    out_dir: Path,
    players: int,
    mex_per_spawn: int,
    center_mexes: int,
    hydros_per_spawn: int,
    early_reclaim_per_spawn: int,
    center_reclaim: int,
    field_reclaim: int,
    seed: int,
) -> dict[str, str]:
    stem = terrain_path.stem.replace(".generated", "")
    points_npz = out_dir / f"{stem}.points.npz"
    points_json = out_dir / f"{stem}.points.json"
    full_npz = out_dir / f"{stem}.full.npz"
    reclaim_json = out_dir / f"{stem}.reclaim.json"

    point_tensor, point_channels, point_metadata = place_points(
        input_path=terrain_path,
        players=players,
        mex_per_spawn=mex_per_spawn,
        center_mexes=center_mexes,
        hydros_per_spawn=hydros_per_spawn,
        water_threshold=0.5,
        search_radius=36,
    )
    _write_npz(points_npz, point_tensor, point_channels)
    _write_json(points_json, point_metadata)

    full_tensor, full_channels, reclaim_metadata = place_reclaim(
        input_path=points_npz,
        point_metadata_path=points_json,
        early_per_spawn=early_reclaim_per_spawn,
        center_count=center_reclaim,
        field_count=field_reclaim,
        water_threshold=0.5,
        seed=seed,
    )
    _write_npz(full_npz, full_tensor, full_channels)
    _write_json(reclaim_json, reclaim_metadata)
    return {
        "terrain_path": str(terrain_path),
        "points_npz": str(points_npz),
        "points_json": str(points_json),
        "full_npz": str(full_npz),
        "reclaim_json": str(reclaim_json),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate complete V0 structure tensors from terrain samples."
    )
    parser.add_argument("--samples-dir", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--manifest-out", required=True, type=Path)
    parser.add_argument("--max-items", type=int)
    parser.add_argument("--players", default=4, type=int)
    parser.add_argument("--mex-per-spawn", default=4, type=int)
    parser.add_argument("--center-mexes", default=4, type=int)
    parser.add_argument("--hydros-per-spawn", default=1, type=int)
    parser.add_argument("--early-reclaim-per-spawn", default=8, type=int)
    parser.add_argument("--center-reclaim", default=14, type=int)
    parser.add_argument("--field-reclaim", default=24, type=int)
    parser.add_argument("--seed", default=20260712, type=int)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    paths = sorted(args.samples_dir.glob("*.generated.npz"))
    if args.max_items is not None:
        paths = paths[: args.max_items]
    rows = []
    for index, terrain_path in enumerate(paths):
        rows.append(
            generate_one(
                terrain_path=terrain_path,
                out_dir=args.out_dir,
                players=args.players,
                mex_per_spawn=args.mex_per_spawn,
                center_mexes=args.center_mexes,
                hydros_per_spawn=args.hydros_per_spawn,
                early_reclaim_per_spawn=args.early_reclaim_per_spawn,
                center_reclaim=args.center_reclaim,
                field_reclaim=args.field_reclaim,
                seed=args.seed + index,
            )
        )
    args.manifest_out.parent.mkdir(parents=True, exist_ok=True)
    args.manifest_out.write_text(json.dumps({"count": len(rows), "items": rows}, indent=2))
    print(f"Generated {len(rows)} complete V0 structure tensor(s)")
    print(f"Wrote manifest to {args.manifest_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
