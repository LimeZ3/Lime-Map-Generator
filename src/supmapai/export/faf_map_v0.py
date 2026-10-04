"""Export a crude generated structure as a loadable FAF map folder.

The default V1 mode patches generated height/water structure into a template
.scmap heightmap while preserving template textures/decals/water shader data.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw

from supmapai.export.scmap_writer import patch_scmap_heightmap
from supmapai.export.validator import validate_structure


def _load_tensor(path: Path) -> tuple[np.ndarray, list[str]]:
    archive = np.load(path)
    tensor = archive["tensor"].astype(np.float32)
    channels = (
        [str(item) for item in archive["channels"]]
        if "channels" in archive.files
        else [f"channel_{index:02d}" for index in range(tensor.shape[0])]
    )
    return tensor, channels


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _world(point: dict[str, Any], map_size: int, grid_size: int) -> tuple[float, float]:
    x = (float(point["x"]) + 0.5) / grid_size * map_size
    z = (float(point["y"]) + 0.5) / grid_size * map_size
    return round(x, 3), round(z, 3)


def _marker_block(
    name: str,
    marker_type: str,
    x: float,
    z: float,
    y: float = 20.0,
) -> str:
    size = 3.0 if marker_type == "Hydrocarbon" else 1.0
    color = "ff008000" if marker_type == "Hydrocarbon" else "ff808080"
    resource_lines = ""
    size_line = ""
    if marker_type in {"Mass", "Hydrocarbon"}:
        size_line = f"                    ['size'] = FLOAT( {size:.6f} ),\n"
        resource_lines = (
            "                    ['resource'] = BOOLEAN( true ),\n"
            "                    ['amount'] = FLOAT( 100.000000 ),\n"
        )
    return (
        f"                ['{name}'] = {{\n"
        f"{size_line}"
        f"{resource_lines}"
        f"                    ['color'] = STRING( '{color}' ),\n"
        "                    ['editorIcon'] = STRING( '' ),\n"
        f"                    ['type'] = STRING( '{marker_type}' ),\n"
        "                    ['prop'] = STRING( '/env/common/props/markers/M_Blank_prop.bp' ),\n"
        "                    ['orientation'] = VECTOR3( 0, 0, 0 ),\n"
        f"                    ['position'] = VECTOR3( {x:.3f}, {y:.3f}, {z:.3f} ),\n"
        "                },\n"
    )


def _army_block(index: int) -> str:
    return (
        f"        ['ARMY_{index}'] = \n"
        "        {\n"
        "            personality = '',\n"
        "            plans = '',\n"
        "            color = 0,\n"
        "            faction = 0,\n"
        "            Economy = {\n"
        "                mass = 0,\n"
        "                energy = 0,\n"
        "            },\n"
        "            Alliances = {\n"
        "            },\n"
        "            ['Units'] = GROUP {\n"
        "                orders = '',\n"
        "                platoon = '',\n"
        "                Units = {\n"
        "                },\n"
        "            },\n"
        "            PlatoonBuilders = {\n"
        "                next_platoon_builder_id = '1',\n"
        "                Builders = {\n"
        "                },\n"
        "            },\n"
        "        },\n"
    )


def _extra_army_block(index: int) -> str:
    return _army_block(index)


def _reclaim_unit_block(unit_id: int, point: dict[str, Any], map_size: int, grid_size: int) -> str:
    x, z = _world(point, map_size, grid_size)
    blueprint = "uel0105" if point.get("kind") == "early_reclaim" else "uea0104"
    return (
        f"                            ['UNIT_{unit_id}'] = {{\n"
        f"                                type = '{blueprint}',\n"
        "                                orders = '',\n"
        "                                platoon = '',\n"
        f"                                Position = {{ {x:.3f}, 20.000, {z:.3f} }},\n"
        "                                Orientation = { 0, 0, 0 },\n"
        "                            },\n"
    )


def _neutral_civilian_block(
    reclaim_points: list[dict[str, Any]],
    map_size: int,
    grid_size: int,
    max_reclaim_units: int,
) -> str:
    units = "".join(
        _reclaim_unit_block(index + 1, point, map_size, grid_size)
        for index, point in enumerate(reclaim_points[:max_reclaim_units])
    )
    return (
        "        ['NEUTRAL_CIVILIAN'] = \n"
        "        {\n"
        "            personality = '',\n"
        "            plans = '',\n"
        "            color = 0,\n"
        "            faction = 0,\n"
        "            Economy = {\n"
        "                mass = 0,\n"
        "                energy = 0,\n"
        "            },\n"
        "            Alliances = {\n"
        "            },\n"
        "            ['Units'] = GROUP {\n"
        "                orders = '',\n"
        "                platoon = '',\n"
        "                Units = {\n"
        "                    ['WRECKAGE'] = GROUP {\n"
        "                        orders = '',\n"
        "                        platoon = '',\n"
        "                        Units = {\n"
        f"{units}"
        "                        },\n"
        "                    },\n"
        "                },\n"
        "            },\n"
        "            PlatoonBuilders = {\n"
        "                next_platoon_builder_id = '1',\n"
        "                Builders = {\n"
        "                },\n"
        "            },\n"
        "        },\n"
    )


def _scenario_lua(
    map_name: str,
    folder_name: str,
    basename: str,
    players: int,
    map_size: int,
    scmap_terrain: str,
) -> str:
    armies = ", ".join(f"'ARMY_{index}'" for index in range(1, players + 1))
    description = (
        "MapGen ML V1 demo. Generated terrain is written into the .scmap heightmap; "
        "textures and water shader data are inherited from a template."
        if scmap_terrain == "generated"
        else "MapGen ML V0 demo. Terrain carrier is a copied template .scmap; "
        "starts/resources/reclaim and preview are generated."
    )
    return (
        "version = 3\n"
        "ScenarioInfo = {\n"
        f"    name = \"{map_name}\",\n"
        f"    description = \"{description}\",\n"
        f"    preview = '/maps/{folder_name}/{basename}_preview.png',\n"
        "    map_version = 1,\n"
        "    type = 'skirmish',\n"
        "    starts = true,\n"
        f"    size = {{{map_size}, {map_size}}},\n"
        "    reclaim = {0, 0},\n"
        f"    map = '/maps/{folder_name}/{basename}.scmap',\n"
        f"    save = '/maps/{folder_name}/{basename}_save.lua',\n"
        f"    script = '/maps/{folder_name}/{basename}_script.lua',\n"
        "    norushradius = 40,\n"
        "    Configurations = {\n"
        "        ['standard'] = {\n"
        "            teams = {\n"
        "                {\n"
        "                    name = 'FFA',\n"
        f"                    armies = {{{armies}}}\n"
        "                },\n"
        "            },\n"
        "            customprops = {\n"
        "                ['ExtraArmies'] = STRING( 'ARMY_17 NEUTRAL_CIVILIAN' ),\n"
        "            },\n"
        "        },\n"
        "    },\n"
        "}\n"
    )


def _basename_from_folder(folder_name: str) -> str:
    lower = folder_name.lower()
    version_index = lower.rfind(".v")
    if version_index > 0 and lower[version_index + 2 :].isdigit():
        return folder_name[:version_index]
    return folder_name


def _save_lua(
    points: dict[str, list[dict[str, Any]]],
    reclaim_points: list[dict[str, Any]],
    players: int,
    map_size: int,
    grid_size: int,
    max_reclaim_units: int,
) -> str:
    marker_blocks = []
    mexes = _dedupe_points(points["mexes"], min_distance=3.0)
    hydros = _dedupe_points(points["hydros"], min_distance=4.0)
    spawns = _dedupe_points(points["spawns"], min_distance=8.0)
    for index, point in enumerate(mexes):
        x, z = _world(point, map_size, grid_size)
        marker_blocks.append(_marker_block(f"Mass {index:02d}", "Mass", x, z))
    for index, point in enumerate(hydros):
        x, z = _world(point, map_size, grid_size)
        marker_blocks.append(_marker_block(f"Hydrocarbon {index:02d}", "Hydrocarbon", x, z))
    for index, point in enumerate(spawns[:players], start=1):
        x, z = _world(point, map_size, grid_size)
        marker_blocks.append(_marker_block(f"ARMY_{index}", "Blank Marker", x, z))

    armies = "".join(_army_block(index) for index in range(1, players + 1))
    armies += _extra_army_block(17)
    armies += _neutral_civilian_block(reclaim_points, map_size, grid_size, max_reclaim_units)
    return (
        "-- Generated by MapGen export.faf_map_v0\n"
        "Scenario = {\n"
        "    next_area_id = '0',\n"
        "    Props = {\n"
        "    },\n"
        "    Areas = {\n"
        "        ['AREA_1'] = {\n"
        f"            ['rectangle'] = RECTANGLE( 0, 0, {map_size}, {map_size} ),\n"
        "        },\n"
        "    },\n"
        "    MasterChain = {\n"
        "        ['_MASTERCHAIN_'] = {\n"
        "            Markers = {\n"
        f"{''.join(marker_blocks)}"
        "            },\n"
        "        },\n"
        "    },\n"
        "    Chains = {\n"
        "    },\n"
        "    Orders = {\n"
        "    },\n"
        "    Platoons = {\n"
        "    },\n"
        "    next_army_id = '0',\n"
        "    next_group_id = '0',\n"
        "    next_unit_id = '0',\n"
        "    Armies = {\n"
        f"{armies}"
        "    },\n"
        "}\n"
    )


def _dedupe_points(points: list[dict[str, Any]], min_distance: float) -> list[dict[str, Any]]:
    kept: list[dict[str, Any]] = []
    min_distance_sq = min_distance * min_distance
    for point in points:
        px = float(point["x"])
        py = float(point["y"])
        is_far_enough = all(
            (px - float(other["x"])) ** 2 + (py - float(other["y"])) ** 2 >= min_distance_sq
            for other in kept
        )
        if is_far_enough:
            kept.append(point)
    return kept


def _to_uint8(array: np.ndarray) -> np.ndarray:
    finite = np.nan_to_num(array.astype(np.float32), nan=0.0, posinf=0.0, neginf=0.0)
    minimum = float(finite.min())
    maximum = float(finite.max())
    if maximum <= minimum:
        return np.zeros(finite.shape, dtype=np.uint8)
    return np.clip((finite - minimum) / (maximum - minimum) * 255, 0, 255).astype(np.uint8)


def _write_preview(
    tensor_path: Path,
    point_metadata: dict[str, Any],
    out_path: Path,
) -> None:
    tensor, channels = _load_tensor(tensor_path)
    lookup = {name: index for index, name in enumerate(channels)}
    height = _to_uint8(tensor[lookup.get("height_norm", 0)])
    water = tensor[lookup.get("water_mask", 1)] >= 0.5
    image = Image.fromarray(height, mode="L").convert("RGB")
    pixels = np.array(image)
    pixels[water] = (40, 105, 180)
    image = Image.fromarray(pixels).resize((512, 512), Image.Resampling.NEAREST)
    draw = ImageDraw.Draw(image)
    colors = {"spawns": (255, 80, 80), "mexes": (255, 220, 70), "hydros": (60, 220, 255)}
    radii = {"spawns": 5, "mexes": 3, "hydros": 4}
    for layer, items in point_metadata["points"].items():
        for point in items:
            x = int(float(point["norm_x"]) * 512)
            y = int(float(point["norm_z"]) * 512)
            radius = radii[layer]
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=colors[layer])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(out_path)


def export_map(
    generated_tensor: Path,
    point_metadata_path: Path,
    reclaim_metadata_path: Path,
    template_scmap: Path,
    out_root: Path,
    folder_name: str,
    map_name: str,
    players: int,
    map_size: int,
    max_reclaim_units: int,
    scmap_terrain: str,
    validate_structure_points: bool,
) -> Path:
    point_metadata = _load_json(point_metadata_path)
    reclaim_metadata = _load_json(reclaim_metadata_path)
    out_dir = out_root / folder_name
    out_dir.mkdir(parents=True, exist_ok=True)
    basename = _basename_from_folder(folder_name)
    validation_report = None
    if validate_structure_points:
        point_metadata, reclaim_metadata, validation_report, _ = validate_structure(
            generated_tensor=generated_tensor,
            point_metadata=point_metadata,
            reclaim_metadata=reclaim_metadata,
            players=players,
            max_reclaim_points=max_reclaim_units,
            template_scmap=template_scmap if scmap_terrain == "generated" else None,
        )
        (out_dir / "mapgen_validated_points.json").write_text(
            json.dumps(point_metadata, indent=2),
            encoding="utf-8",
        )
        (out_dir / "mapgen_validated_reclaim.json").write_text(
            json.dumps(reclaim_metadata, indent=2),
            encoding="utf-8",
        )
        (out_dir / "mapgen_validator_report.json").write_text(
            json.dumps(validation_report, indent=2),
            encoding="utf-8",
        )
    out_scmap = out_dir / f"{basename}.scmap"
    terrain_patch_summary = None
    if scmap_terrain == "generated":
        terrain_patch_summary = patch_scmap_heightmap(
            template_scmap=template_scmap,
            generated_tensor=generated_tensor,
            out_scmap=out_scmap,
        )
    else:
        shutil.copy2(template_scmap, out_scmap)
    (out_dir / f"{basename}_scenario.lua").write_text(
        _scenario_lua(map_name, folder_name, basename, players, map_size, scmap_terrain),
        encoding="utf-8",
    )
    (out_dir / f"{basename}_save.lua").write_text(
        _save_lua(
            points=point_metadata["points"],
            reclaim_points=reclaim_metadata["points"],
            players=players,
            map_size=map_size,
            grid_size=256,
            max_reclaim_units=max_reclaim_units,
        ),
        encoding="utf-8",
    )
    (out_dir / f"{basename}_script.lua").write_text(
        (
            "local ScenarioUtils = import('/lua/sim/ScenarioUtilities.lua')\n\n"
            "function OnPopulate()\n"
            "    ScenarioUtils.InitializeArmies()\n"
            "end\n\n"
            "function OnStart()\n"
            "end\n"
        ),
        encoding="utf-8",
    )
    _write_preview(generated_tensor, point_metadata, out_dir / f"{basename}_preview.png")
    metadata = {
        "schema": "mapgen_faf_export_v1",
        "limitation": (
            "V1 writes generated heights only; textures, decals, props, water shader settings, "
            "and the embedded .scmap preview are inherited from the template."
            if scmap_terrain == "generated"
            else "Template mode copies the .scmap terrain; generated terrain is preview-only."
        ),
        "scmap_terrain": scmap_terrain,
        "validate_structure": validate_structure_points,
        "validation_report": validation_report,
        "terrain_patch_summary": (
            terrain_patch_summary.__dict__ if terrain_patch_summary is not None else None
        ),
        "generated_tensor": str(generated_tensor),
        "point_metadata": str(point_metadata_path),
        "reclaim_metadata": str(reclaim_metadata_path),
        "template_scmap": str(template_scmap),
        "folder_name": folder_name,
        "map_name": map_name,
        "players": players,
        "map_size": map_size,
        "max_reclaim_units": max_reclaim_units,
    }
    (out_dir / "mapgen_export_metadata.json").write_text(
        json.dumps(metadata, indent=2),
        encoding="utf-8",
    )
    return out_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export a generated structure as a FAF map.")
    parser.add_argument("--generated-tensor", required=True, type=Path)
    parser.add_argument("--point-metadata", required=True, type=Path)
    parser.add_argument("--reclaim-metadata", required=True, type=Path)
    parser.add_argument("--template-scmap", required=True, type=Path)
    parser.add_argument("--out-root", required=True, type=Path)
    parser.add_argument("--folder-name", default="mapgen_ml_demo_v0001")
    parser.add_argument("--map-name", default="MapGen ML Demo v0001")
    parser.add_argument("--players", default=4, type=int)
    parser.add_argument("--map-size", default=512, type=int)
    parser.add_argument("--max-reclaim-units", default=70, type=int)
    parser.add_argument(
        "--scmap-terrain",
        default="generated",
        choices=["generated", "template"],
        help="Use generated height/water terrain or copy the template .scmap unchanged.",
    )
    parser.add_argument(
        "--validate-structure",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Repair starts/resources/reclaim against generated terrain before export.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    out_dir = export_map(
        generated_tensor=args.generated_tensor,
        point_metadata_path=args.point_metadata,
        reclaim_metadata_path=args.reclaim_metadata,
        template_scmap=args.template_scmap,
        out_root=args.out_root,
        folder_name=args.folder_name,
        map_name=args.map_name,
        players=args.players,
        map_size=args.map_size,
        max_reclaim_units=args.max_reclaim_units,
        scmap_terrain=args.scmap_terrain,
        validate_structure_points=args.validate_structure,
    )
    print(f"Wrote FAF demo map folder to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
