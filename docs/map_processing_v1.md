# Map Processing V1

V1 should extract concrete, explainable facts from map files before survey or ML. No diffusion models, no learned classifiers, and no AI-marker analysis in this phase.

The goal is one stable output record per canonical map folder. Missing or uncertain fields should be explicit rather than guessed.

## Source Definition

One map is one immediate folder under the FAF maps root:

```text
C:\Program Files (x86)\Steam\steamapps\common\FAF_modsmaps\maps
```

Nested `Backup_*` folders or internal version folders are candidate versions of that same map. The canonical inventory chooses the best available representative and records the candidate counts.

## V1 Pipeline

```text
FAF maps folder
-> canonical inventory
-> Lua extraction
-> SCMAP terrain/header extraction
-> exact marker layer export
-> reclaim/civilian entity layer export
-> resource balance and team-layout inference
-> structure metrics
-> derived feature pass
-> survey seed export
-> ML feature table
```

Recommended commands:

```powershell
python -m supmapai.extract.canonical_inventory --maps-root "C:\Program Files (x86)\Steam\steamapps\common\FAF_modsmaps\maps" --out data\manifests\faf_modsmaps_canonical_inventory.json
python -m supmapai.extract.metadata_from_inventory --inventory data\manifests\faf_modsmaps_canonical_inventory.json --out data\interim\faf_modsmaps_canonical_metadata.csv
python -m supmapai.extract.name_families --metadata data\interim\faf_modsmaps_canonical_metadata.csv --out data\interim\faf_modsmaps_canonical_name_families.csv --summary-out data\interim\faf_modsmaps_canonical_name_families_summary.json
```

Full-dataset processing should be run in resumable chunks, not as one monolithic command:

```powershell
python -m supmapai.extract.chunk_inventory --inventory data\manifests\faf_modsmaps_canonical_inventory.json --out-dir data\manifests\batches_250 --prefix batch --chunk-size 250 --require scmap --require scenario_lua --require save_lua

python -m supmapai.tools.run_v1_batch --inventory data\manifests\batches_250\batch_0000_inventory.json --out-dir data\interim\batches\batch_0000 --preview-dir data\exports\previews\batch_0000 --batch-name batch_0000 --max-maps 250
```

The batch runner writes per-map survey/admin PNGs:

- `*.terrain.png`
- `*.water_depth.png`
- `*.pathability.png`
- `*.markers.png`
- `*.entities.png`

Run later chunks by changing `batch_0000` to `batch_0001`, `batch_0002`, etc. Keep chunk outputs separate so parser fixes can be rerun against only the affected chunk.

Future V1 tools:

```powershell
python -m supmapai.extract.lua_entities --inventory data\manifests\faf_modsmaps_canonical_inventory.json --out data\interim\faf_modsmaps_lua_entities.jsonl
python -m supmapai.extract.scmap_terrain --inventory data\manifests\faf_modsmaps_canonical_inventory.json --out data\interim\faf_modsmaps_terrain_metrics.csv --preview-dir data\interim\structural_previews
python -m supmapai.tools.marker_layers --entities-jsonl data\interim\faf_modsmaps_lua_entities.jsonl --terrain-csv data\interim\faf_modsmaps_terrain_metrics.csv --out data\interim\faf_modsmaps_markers.csv --summary-out data\interim\faf_modsmaps_markers_summary.csv --preview-dir data\interim\structural_previews
python -m supmapai.tools.entity_layers --entities-jsonl data\interim\faf_modsmaps_lua_entities.jsonl --terrain-csv data\interim\faf_modsmaps_terrain_metrics.csv --out data\interim\faf_modsmaps_entities.csv --summary-out data\interim\faf_modsmaps_entities_summary.csv --preview-dir data\interim\structural_previews
python -m supmapai.extract.scmap_props --inventory data\manifests\faf_modsmaps_canonical_inventory.json --out data\interim\faf_modsmaps_scmap_props.jsonl --summary-out data\interim\faf_modsmaps_scmap_props_summary.csv --max-maps 1
python -m supmapai.extract.structure_metrics --inventory data\manifests\faf_modsmaps_canonical_inventory.json --terrain data\interim\faf_modsmaps_terrain_metrics.csv --markers data\interim\faf_modsmaps_markers.csv --entities data\interim\faf_modsmaps_entities.csv --out data\interim\faf_modsmaps_structure_metrics.csv --max-maps 1
python -m supmapai.extract.features_v1 --metadata data\interim\faf_modsmaps_canonical_metadata.csv --entities data\interim\faf_modsmaps_lua_entities.jsonl --terrain data\interim\faf_modsmaps_terrain_metrics.csv --scmap-props-summary data\interim\faf_modsmaps_scmap_props_summary.csv --name-families data\interim\faf_modsmaps_canonical_name_families.csv --out data\processed\features_v1\map_features_v1.csv --survey-out apps\crowd-labeler\src\data\maps.generated.json
python -m supmapai.tools.dataset_audit --batches-root data\interim\batches --out-dir data\audit\v1_current
python -m supmapai.tensors.export_tensors --inventory data\manifests\batches_250_no_neroxis\batch_0024_inventory.json --features data\interim\batches\batch_0024\batch_0024_map_features_v1.csv --markers data\interim\batches\batch_0024\batch_0024_markers.csv --entities data\interim\batches\batch_0024\batch_0024_entities.csv --audit-maps data\audit\v1_current\dataset_audit_maps.csv --audit-status ready --audit-status review --out-dir data\tensors\v1_smoke\batch_0024 --manifest-out data\tensors\v1_smoke\batch_0024_manifest.csv --max-maps 2 --grid-size 256
python -m supmapai.tensors.contact_sheet --manifest data\tensors\v1_smoke\batch_0024_manifest.csv --out-dir data\tensors\v1_smoke\qa --max-maps 2
python -m supmapai.tensors.split_dataset --audit-maps data\audit\v1_current\dataset_audit_maps.csv --out data\splits\v1_current\splits.csv --summary-out data\splits\v1_current\splits_summary.json
```

## Output Files

### `canonical_inventory.json`

Purpose: one canonical map record per top-level folder, with selected internal version.

Already implemented:

- `top_level_dir`
- `selected_map_dir`
- `selection_reason`
- `name_signals`
- `candidate_count`
- `backup_candidate_count`
- selected file paths
- all candidate versions/backups

### `lua_entities.jsonl`

Purpose: detailed entities and object counts from `_scenario.lua` and `_save.lua`.

One JSON object per canonical map. This file should preserve detailed counts and positions, not just summary features.

Implemented first pass:

- marker positions for spawns, mexes, and hydros
- exact spawn/mex/hydro `x/y/z` positions
- marker type counts
- declared team count/team sizes when parseable
- unit blueprint counts
- prop blueprint counts
- reclaim entity counts and positions when encoded as save-Lua wreckage groups or props
- civilian unit/building counts and positions using conservative blueprint and group-name heuristics
- group path/context for parsed save-Lua units, so optional wreckage groups can be classified as reclaim even when the blueprint is a normal unit type

Known gap: individual reclaim entity counts can still remain zero when reclaim is stored only inside `.scmap` prop data or another format not exposed as save-Lua units/props.

### `terrain_metrics.csv`

Purpose: terrain and texture metrics from `.scmap`.

This is where buildable terrain, water percentage, steep-pathblocking terrain, and texture pack should come from.

Implemented first pass:

- safe single-map decoding with `--max-maps 1` default
- preview DDS skip
- 16-byte terrain prefix skip before the heightmap block
- heightmap decode for tested FA `.scmap` files
- conversion from `(map_size + 1)` height vertices to playable terrain cells
- playable-area crop from `_save.lua` `AREA_1` when present
- playable-cell height stats
- parsed water-block elevation when present
- uncertain histogram water-level fallback when a water block is not found
- water/land percentages
- shallow/medium/deep water percentages from terrain depth below the water plane
- continuous water-depth preview channel for QA and future tensor export
- connected water-body count, area, bounding boxes, and per-body depth stats
- land-unit passable/unpassable masks from water plus steep terrain
- connected passable-land component count, area, and bounding boxes
- tiny connected-water-component filtering only when water level is histogram-inferred
- optional removal of tiny water components confined to map-corner artifact zones, disabled by default
- rough buildable/slope/steep percentages from configurable slope thresholds
- texture path extraction
- structural terrain preview PNG

Validated on Seton's Clutch, Dual Gap, Canis River, Monument Valley, Tabula Rasa, and The Drunken Beetles Dance. Do not run this across thousands of maps until more sample maps and failure modes have been tested.

### `map_features_v1.csv`

Purpose: flat, stable table for survey display, filtering, and ML conditioning.

This should be the main V1 data product.

Implemented first pass:

- identity/canonical fields
- source quality and parse warnings
- size and slot counts
- spawn/mex/hydro counts
- exact spawn/mex/hydro position JSON
- declared reclaim totals and per-player ratios
- civilian unit/building counts
- duplicate family key from name-family detection
- terrain/symmetry/texture columns present but blank or `unknown` until `.scmap` decoding
- dense natural reclaim counts from `.scmap` props when `scmap_props_summary.csv` is supplied

### `maps.generated.json`

Purpose: compact survey-app seed derived from `map_features_v1.csv`.

It should not expose raw local file paths.

## Field Schema

### Identity

| Field | Type | Source | Required | Notes |
| --- | --- | --- | --- | --- |
| `map_id` | string | derived | yes | Stable slug/hash from canonical folder. |
| `top_level_dir` | string | canonical inventory | yes | User-facing folder identity. |
| `selected_map_dir` | string | canonical inventory | yes | Internal representative folder. |
| `scenario_name` | string | scenario Lua | yes | Empty only if scenario parse fails. |
| `scenario_description` | string | scenario Lua | no | Useful for survey/admin context. |
| `map_version` | int/null | scenario Lua | no | Scenario `map_version`. |
| `name_signals` | string list | folder/name | yes | Example: `adaptive`, `gap`, `pass`, `crater`. |
| `duplicate_family_key` | string/null | name families | no | Normalized likely-family key. |
| `candidate_count` | int | canonical inventory | yes | Internal candidate versions/backups. |
| `backup_candidate_count` | int | canonical inventory | yes | Usually exclude from independent training. |

### Files And Parse Status

| Field | Type | Source | Required | Notes |
| --- | --- | --- | --- | --- |
| `has_scmap` | bool | inventory | yes | |
| `has_scenario_lua` | bool | inventory | yes | |
| `has_save_lua` | bool | inventory | yes | |
| `has_preview_image` | bool | inventory | yes | Existing image only. |
| `parse_warnings` | string list | all tools | yes | Include missing/invalid file warnings. |
| `source_quality` | enum | derived | yes | `complete`, `partial`, `broken`. |

### Map Size And Slots

| Field | Type | Source | Required | Notes |
| --- | --- | --- | --- | --- |
| `size_x` | int/null | scenario/scmap | yes | Scenario size preferred; validate against `.scmap`. |
| `size_z` | int/null | scenario/scmap | yes | |
| `size_class` | enum | derived | yes | Example: `5km`, `10km`, `20km`, `40km`, `80km`. |
| `player_slots` | int/null | scenario/save | yes | Count configured `ARMY_*` slots. |
| `spawn_count` | int | save Lua | yes | Count spawn/blank markers that represent starts. |
| `spawn_positions_json` | JSON array | save Lua | yes | Exact spawn marker names, types, and `x/y/z` coordinates. |
| `slots_match_spawns` | bool/null | derived | yes | Useful quality warning. |

### Team Layout And Spawn Geometry

| Field | Type | Source | Required | Notes |
| --- | --- | --- | --- | --- |
| `team_count_declared` | int/null | scenario Lua | yes | From configurations where possible. |
| `team_layout_label` | enum/null | derived | yes | `ffa`, `two_teams`, `three_plus_teams`, `unknown`. |
| `spawn_geometry_label` | enum/null | derived | yes | `corners`, `opposite_sides`, `radial`, `mixed`, `unknown`. |
| `spawn_center_distance_mean` | float/null | derived | no | Normalized distance from map center. |
| `spawn_pair_distance_min` | float/null | derived | no | Normalized closest spawn distance. |
| `spawn_pair_distance_mean` | float/null | derived | no | Normalized average spawn distance. |

### Resources

| Field | Type | Source | Required | Notes |
| --- | --- | --- | --- | --- |
| `mex_count` | int | save Lua | yes | Marker type `Mass`. |
| `hydro_count` | int | save Lua | yes | Marker type `Hydrocarbon`. |
| `mex_positions_json` | JSON array | save Lua | yes | Exact mass marker names, types, and `x/y/z` coordinates. |
| `hydro_positions_json` | JSON array | save Lua | yes | Exact hydro marker names, types, and `x/y/z` coordinates. |
| `mex_per_player` | float/null | derived | yes | Null if player count missing. |
| `hydro_per_player` | float/null | derived | yes | |
| `reclaim_mass_total_declared` | float/null | scenario Lua | yes | Scenario `reclaim` mass. |
| `reclaim_energy_total_declared` | float/null | scenario Lua | yes | Scenario `reclaim` energy. |
| `reclaim_entity_count` | int/null | save Lua/scmap props | yes | Count individual reclaim props/units if extractable. |
| `scmap_prop_count` | int/null | scmap props | no | Total props in the `.scmap` prop section. |
| `tree_prop_count` | int/null | scmap props | no | Natural tree props, usually reclaimable. |
| `rock_prop_count` | int/null | scmap props | no | Natural rock props, usually reclaimable. |
| `boulder_prop_count` | int/null | scmap props | no | Natural boulder props, usually reclaimable. |
| `scmap_reclaim_prop_count` | int/null | scmap props | no | Tree + rock + boulder + explicit reclaim-like prop paths. |
| `total_reclaim_entity_count` | int/null | derived | no | Save-Lua reclaim plus `.scmap` natural reclaim props. |
| `reclaim_entity_positions_json` | JSON array | save Lua/scmap props | no | Exact parsed reclaim object positions where extractable. |
| `reclaim_entity_type_counts_json` | JSON object | save Lua/scmap props | yes | Example groups: trees, rocks, wrecks, civilian structures. |
| `reclaim_mass_per_player` | float/null | derived | yes | |
| `reclaim_energy_per_player` | float/null | derived | yes | |

### Marker Layer Export

`supmapai.tools.marker_layers` writes one row per spawn, mex, and hydro marker.

| Field | Type | Source | Notes |
| --- | --- | --- | --- |
| `map_dir` | string | derived | Canonical map folder. |
| `kind` | enum | save Lua | `spawn`, `mex`, or `hydro`. |
| `name` | string | save Lua | Marker name, such as `ARMY_1` or `Mass 01`. |
| `x` | float | save Lua | Raw map x coordinate. |
| `y` | float | save Lua | Raw marker height/elevation coordinate. |
| `z` | float | save Lua | Raw map z coordinate. |
| `playable_x` | float | derived | `x - playable_x0`. |
| `playable_z` | float | derived | `z - playable_z0`. |
| `norm_x` | float | derived | Playable-area normalized x, 0-1. |
| `norm_z` | float | derived | Playable-area normalized z, 0-1. |
| `in_playable_area` | bool | derived | False if marker lies outside the current playable rectangle. |

Marker previews use red for spawns, yellow for mexes, and cyan for hydros.

### Reclaim And Civilian Entity Layer Export

`supmapai.tools.entity_layers` writes one row per parsed reclaim/civilian object and a QA preview per map. When `--scmap-props-jsonl` is supplied, it also includes dense `.scmap` natural props such as trees, rocks, and boulders.

| Field | Type | Source | Notes |
| --- | --- | --- | --- |
| `map_dir` | string | derived | Canonical map folder. |
| `source` | enum | derived | `save_lua` or `scmap`. |
| `kind` | enum | save Lua/scmap | `reclaim`, `civilian_unit`, `civilian_building`, `tree`, `rock`, or `boulder`. |
| `name` | string | save Lua | Unit/table name, usually `UNIT_*`. |
| `blueprint` | string | save Lua | Unit or prop blueprint ID. |
| `army` | string | save Lua | Enclosing army when parseable. |
| `group_path` | string | save Lua | Slash-separated enclosing GROUP names. |
| `x` | float | save Lua | Raw map x coordinate. |
| `y` | float | save Lua | Raw object height/elevation coordinate. |
| `z` | float | save Lua | Raw map z coordinate. |
| `playable_x` | float | derived | `x - playable_x0`. |
| `playable_z` | float | derived | `z - playable_z0`. |
| `norm_x` | float | derived | Playable-area normalized x, 0-1. |
| `norm_z` | float | derived | Playable-area normalized z, 0-1. |
| `in_playable_area` | bool | derived | False if object lies outside the current playable rectangle. |

Entity previews use orange for save-Lua reclaim, violet for civilian units, magenta squares for civilian buildings, green dots for trees, and gray/tan dots for rocks and boulders.

### Civilian And Enemy Civilian Content

| Field | Type | Source | Required | Notes |
| --- | --- | --- | --- | --- |
| `civilian_unit_count` | int | save Lua | yes | Neutral/civilian units. |
| `civilian_unit_positions_json` | JSON array | save Lua | no | Exact parsed civilian unit positions. |
| `civilian_building_count` | int | save Lua | yes | Civilian structures. |
| `civilian_building_positions_json` | JSON array | save Lua | no | Exact parsed civilian structure positions. |
| `enemy_civilian_unit_count` | int | save Lua | yes | If owner/army can distinguish enemy civilian. |
| `civilian_type_counts_json` | JSON object | save Lua | yes | Blueprint/type to count. |
| `has_civilian_base` | bool | derived | yes | True if meaningful structure cluster exists. |

### Terrain From `.scmap`

| Field | Type | Source | Required | Notes |
| --- | --- | --- | --- | --- |
| `height_min` | float/null | scmap | yes | Requires heightmap decoding. |
| `height_max` | float/null | scmap | yes | |
| `height_mean` | float/null | scmap | no | |
| `height_std` | float/null | scmap | no | |
| `playable_area_source` | enum | save Lua/derived | yes | `save_lua_area_1` when `AREA_1` is used, otherwise `full_map`. |
| `playable_x0` | int | save Lua/derived | yes | Playable crop lower x cell. |
| `playable_z0` | int | save Lua/derived | yes | Playable crop lower z cell. |
| `playable_x1` | int | save Lua/derived | yes | Playable crop upper x cell. |
| `playable_z1` | int | save Lua/derived | yes | Playable crop upper z cell. |
| `playable_width` | int | save Lua/derived | yes | Width of terrain used for metrics/previews. |
| `playable_height` | int | save Lua/derived | yes | Height of terrain used for metrics/previews. |
| `water_level` | float/null | scmap | yes | If present in format. |
| `water_level_source` | enum/null | scmap/derived | yes | `waterramp_block_elevation` when parsed from the water block; `height_histogram_fallback_uncertain` when guessed. |
| `water_percent` | float/null | scmap derived | yes | Terrain cells at/below water level. |
| `shallow_water_percent` | float/null | derived | no | Water cells with 0-2 height units of water depth. |
| `medium_water_percent` | float/null | derived | no | Water cells with 2-8 height units of water depth. |
| `deep_water_percent` | float/null | derived | no | Water cells deeper than 8 height units. |
| `water_depth_max` | float/null | derived | no | Maximum depth over water cells only. |
| `water_depth_mean` | float/null | derived | no | Mean depth over water cells only. |
| `water_depth_p50` | float/null | derived | no | Median depth over water cells only. |
| `water_depth_p95` | float/null | derived | no | 95th percentile depth over water cells only. |
| `water_body_count` | int | derived | yes | Connected water components after cleanup/filtering. |
| `largest_water_body_percent` | float | derived | yes | Largest water component area as percent of playable terrain. |
| `largest_water_body_depth_mean` | float | derived | yes | Mean depth inside largest water body. |
| `largest_water_body_depth_max` | float | derived | yes | Maximum depth inside largest water body. |
| `water_bodies_json` | JSON array | derived | yes | Largest connected bodies with area, bbox, depth mean/p50/p95/max. |
| `water_artifact_removed_cells` | int | derived | yes | Count of water cells removed by the corner-artifact cleanup. |
| `water_artifact_removed_percent` | float | derived | yes | Removed cells as percent of playable terrain cells. |
| `water_artifact_rule` | string | derived | yes | Rule identifier, currently corner-confined components. |
| `water_noise_removed_cells` | int | derived | yes | Count of tiny water components removed when water level was uncertain. |
| `water_noise_removed_percent` | float | derived | yes | Removed tiny uncertain-water cells as percent of playable terrain. |
| `water_noise_rule` | string | derived | yes | Rule identifier and current minimum component size. |
| `land_percent` | float/null | derived | yes | `100 - water_percent`. |
| `buildable_percent` | float/null | derived | yes | Flat enough and non-water unless we decide naval factories count separately. |
| `non_buildable_slope_percent` | float/null | derived | yes | Sloped but possibly passable. |
| `pathblocking_steep_percent` | float/null | derived | yes | Very steep terrain where land units likely cannot pass. |
| `land_unit_passable_percent` | float/null | derived | yes | Non-water terrain below the pathblocking slope threshold. |
| `land_unit_unpassable_percent` | float/null | derived | yes | Water plus steep/pathblocking terrain for normal land units. |
| `land_unit_blocked_by_water_percent` | float/null | derived | yes | Water-blocked portion of playable terrain. |
| `land_unit_blocked_by_steep_percent` | float/null | derived | yes | Steep-land blocked portion of playable terrain. |
| `passable_land_component_count` | int | derived | yes | Connected passable-land regions after water/steep blocking. |
| `largest_passable_land_percent` | float | derived | yes | Largest passable-land component as percent of playable terrain. |
| `passable_land_components_json` | JSON array | derived | no | Largest passable-land components with area and bbox. |
| `flat_height_mode_percent` | float/null | derived | no | Percent near the most common height band. |
| `slope_mean` | float/null | derived | no | |
| `slope_p95` | float/null | derived | no | |

V1 terrain thresholds should be configurable. Initial defaults:

- `buildable`: slope below a conservative low threshold and above water.
- `non_buildable_slope`: slope above buildable threshold but below pathblocking threshold.
- `pathblocking_steep`: slope above high threshold.

The pathability preview uses green for land-unit-passable terrain, blue for water-blocked terrain, and red for steep/pathblocking terrain. This is still a terrain-derived approximation, not the final game path graph.

These thresholds should be validated visually against known maps before being trusted.

Terrain metrics should be computed on playable terrain cells, not directly on raw heightmap vertices. FA `.scmap` heightmaps contain one more vertex than the map cell width/height; isolated border vertices can create fake one-pixel water artifacts that are not visible or playable in-game.

An earlier decoder version missed the 16-byte prefix before the heightmap block. That made terrain appear horizontally shifted and created false edge/corner artifacts. Corner cleanup remains an optional audit switch, but it should stay disabled unless a separate artifact is proven after the heightmap alignment is correct.

Some maps declare a playable rectangle in `_save.lua`, usually as `AREA_1`. Terrain previews and metrics should use that rectangle when present. This matters for maps like Dual Gap, where the full `.scmap` is square but the in-game playable area is rectangular.

When no explicit water block is found, the water level is inferred from height distribution and should be treated as uncertain. In that case only, V1 removes tiny connected water components below a configurable cell-count threshold. This handles maps such as Canis River where the inferred plane captures three true water bodies plus several tiny below-plane terrain specks that do not render as water in-game.

Depth should be preserved as a continuous model input, not just summarized into shallow/medium/deep bands. The PNG depth preview is for human QA and normalizes depth per map visually; the future tensor export should store numeric water depth in terrain height units, with land as 0 and a separate water mask channel.

### Symmetry

| Field | Type | Source | Required | Notes |
| --- | --- | --- | --- | --- |
| `symmetry_detected` | bool | derived | yes | Based on terrain/resources/spawns. |
| `symmetry_order` | int/null | derived | yes | `2`, `3`, `4`, etc. "Pizza slices." |
| `symmetry_label` | enum/null | derived | yes | `mirror_x`, `mirror_z`, `rotational_2`, `rotational_3`, `rotational_4`, `radial`, `asymmetric`, `unknown`. |
| `symmetry_score` | float/null | derived | yes | 0-1 confidence/fit score. |
| `symmetry_basis` | string list | derived | yes | Example: `terrain`, `spawns`, `mexes`, `hydros`. |

V1 should try simple checks first:

- compare spawn positions under 180-degree rotation
- compare mex/hydro positions under candidate rotations/reflections
- later compare terrain masks once `.scmap` decoding is reliable

### Structure Metrics

`supmapai.extract.structure_metrics` derives higher-level structural map facts from terrain,
marker, entity, and team-layout CSVs. It intentionally uses a bounded analysis grid so full
batches remain practical on Windows.

Implemented fields:

- `shoreline_length_cells` and `shoreline_length_per_10k_area`
- `structural_water_body_count`, `structural_water_body_sizes_json`, and `water_body_type_guess`
- `plateau_count`, `plateau_sizes_json`, and `largest_plateau_percent`
- `engineer_hover_region_count` and `largest_engineer_hover_region_percent`
- `transport_only_region_count` and `transport_only_area_percent`
- `water_separated_region_count` and `water_separated_area_percent`
- `base_to_base_path_exists`, path length/direct distance, straightness, min/median width, and choke count
- `early_reclaim_per_spawn_*`, `center_reclaim_percent`, `contested_reclaim_percent`
- `reclaim_cluster_count`, `reclaim_cluster_sizes_json`, `reclaim_spread_label`, and `reclaim_fairness_score`

Definitions:

- Normal land pathing treats water and steep terrain as blocked.
- Engineer-hover accessibility treats steep terrain as blocked but allows water, matching most engineers.
- Transport-only regions are engineer-hover regions isolated by steep/pathblocking terrain, not merely by water.
- Water-separated regions are normal-land regions split by water that are still connected under engineer-hover rules.
- Reclaim structure currently uses individual parsed reclaim entity counts/positions, not mass or energy weighting.

### Dataset Audit

`supmapai.tools.dataset_audit` reads completed batch feature outputs and produces a
non-destructive health report:

- `dataset_audit_summary.json`: global counts, missing stages, warning counts, batch status.
- `dataset_audit_maps.csv`: one row per map with `ready`, `review`, or `exclude_candidate`.
- `dataset_audit_outliers.csv`: robust-z outliers for terrain, resources, props, reclaim, and balance.
- `dataset_audit_warnings.csv`: warning-token frequency table.
- `dataset_audit_families.csv`: duplicate/name-family groups that must stay together in train/validation/test splits.

Readiness labels are intentionally conservative:

- `ready`: no hard parse/source issue and no gameplay-critical numeric outlier.
- `review`: likely usable, but worth checking because of odd water/buildable/pathing/resource values.
- `exclude_candidate`: missing critical files, zero spawns, zero mexes, nearly all water, almost no buildable/passable area, or parser failure warnings.

Outlier rows do not automatically mean a map is bad. High tree/rock/boulder/civilian counts are preserved as audit facts but do not by themselves downgrade readiness.

### Tensor Export V1

`supmapai.tensors.export_tensors` converts audited maps into compressed NumPy archives.
This is the bridge from parser/audit work to ML experiments.

Each exported map writes one `.npz` file with:

- `tensor`: `float32` array shaped `[channel, grid_z, grid_x]`.
- `channels`: ordered channel names.
- `map_id` and `map_dir`: identity fields for joining back to CSV metadata.

Initial V1 channel order:

1. `height_norm`
2. `water_mask`
3. `water_depth_norm`
4. `land_mask`
5. `land_passable_mask`
6. `buildable_mask`
7. `slope_norm`
8. `spawn_heatmap`
9. `mex_heatmap`
10. `hydro_heatmap`
11. `reclaim_density`
12. `civilian_structure_density`

V1 defaults to `256x256`. Terrain channels are cropped to playable area before resizing.
Marker/entity channels are drawn from normalized playable-area coordinates, so all layers are aligned.
When an audit CSV is supplied, tensor export can filter by `ready`, `review`, or any other
audit status before writing `.npz` files.

The first expected success criterion is visual QA, not training: generate contact sheets from tensor channels and confirm that terrain, water, spawns, mexes, hydros, reclaim, and civilian structures line up with existing previews.

### Dataset Splits

`supmapai.tensors.split_dataset` creates deterministic train/validation/test assignments
from `dataset_audit_maps.csv`.

Rules:

- Include `ready` and `review` maps by default.
- Exclude `exclude_candidate` maps by default.
- Keep every `duplicate_family_key` in exactly one split.
- Maps without a family key use their own map folder as the split group.
- Default ratios are 80% train, 10% validation, 10% test.

The output is `splits.csv` plus `splits_summary.json`. These split assignments should be used by tensor export and training so near-clones do not leak into validation/test.

### Texture And Visual Metadata

| Field | Type | Source | Required | Notes |
| --- | --- | --- | --- | --- |
| `texture_pack` | string/null | scmap | yes | Best-effort extracted texture set/folder. |
| `texture_names_json` | JSON array | scmap | no | Raw texture identifiers. |
| `biome_guess` | enum/null | derived | no | Rule-based from texture names only. |

Texture/biome should be displayed as machine context, not treated as truth.

### Survey Display Fields

The survey app should consume a compact subset:

| Field | Type | Notes |
| --- | --- | --- |
| `map_id` | string | Stable ID. |
| `display_name` | string | Scenario name or folder name. |
| `top_level_dir` | string | Useful for admin/debug. |
| `size_class` | string | Human-friendly size. |
| `player_slots` | int/null | |
| `mex_count` | int | |
| `hydro_count` | int | |
| `reclaim_mass_total_declared` | float/null | |
| `reclaim_entity_count` | int/null | |
| `civilian_unit_count` | int/null | |
| `civilian_building_count` | int/null | |
| `water_percent` | float/null | |
| `buildable_percent` | float/null | |
| `pathblocking_steep_percent` | float/null | |
| `symmetry_label` | string/null | |
| `symmetry_score` | float/null | |
| `team_layout_label` | string/null | |
| `spawn_geometry_label` | string/null | |
| `name_signals` | string list | `adaptive`, `gap`, `pass`, `crater`. |
| `duplicate_family_key` | string/null | |
| `structural_preview_url` | string/null | Later. |

## Explicitly Out Of V1

- AI marker analysis.
- Neural quality prediction.
- Diffusion/image generation.
- Automatic deletion of bad maps.
- Perfect terrain pathability simulation.
- Full playable-map export.

## V1 Success Criteria

- One flat `map_features_v1.csv` row per canonical top-level map.
- Reclaim totals and individual reclaim entity counts are present where extractable.
- Mex, hydro, spawn, civilian, and enemy/civilian structure counts are present.
- Terrain percentages are present for maps with decodable `.scmap`.
- Symmetry label and score exist, even if `unknown` for hard cases.
- Survey seed export contains enough context to show useful facts without overwhelming voters.
- All derived fields carry warnings/nulls when the source is missing or uncertain.
