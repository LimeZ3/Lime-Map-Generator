# Dataset Labeling

SupCom maps should be treated as multi-label examples. Do not force each map into one exclusive folder such as `naval` or `land`; maps like Seton's Clutch legitimately combine naval, air, land, expansion, choke, and team-role structure.

## Recommended Data Layout

Keep raw maps immutable and outside Git:

```text
data/
  raw/
    faf_modsmaps_snapshot_YYYY-MM-DD/
      maps/
        setons_clutch_-_faf_version.v0004/
        ...
  manifests/
    faf_modsmaps_inventory.json
  labels/
    map_labels.csv
  interim/
    parsed_lua/
    scmap_headers/
  processed/
    tensor_v001/
  exports/
    generated_maps/
```

The live Steam/FAF folder can be inventoried directly, but copy snapshots into `data/raw/` before doing repeatable experiments. This prevents a future FAF update from silently changing the training set.

## Label Axes

Use several independent label columns. Empty values are allowed at first.

### Identity

- `map_dir`
- `canonical_name`
- `version`
- `duplicate_group`
- `quality_tier`

Use `duplicate_group` for twins, remakes, or version families. Example: all Seton's variants can share a duplicate group while keeping their exact versions separate.

### Technical Metadata

Most of these can eventually be extracted automatically:

- `size_x`
- `size_z`
- `player_count`
- `has_scmap`
- `has_scenario_lua`
- `has_save_lua`
- `has_preview`

### Gameplay Labels

These are human labels and can be multi-select with `|` separators:

- `primary_modes`: `land`, `naval`, `air`, `mixed`
- `secondary_modes`: `amphibious`, `transport`, `hover`, `turtle`, `raid`, `eco`, `teamgame`, `ffa`
- `pace`: `close_combat`, `standard`, `macro`, `slow_turtle`
- `lane_structure`: `open`, `laned`, `chokepoint`, `island`, `ponds`, `water_center`, `water_sides`
- `expansion_pattern`: `linear`, `radial`, `contested_mid`, `safe_back`, `island_expansions`

### Strategic Structure

These labels are especially useful for models trained on pathing/resource layers:

- `symmetry`: `mirror_x`, `mirror_z`, `rotational`, `radial`, `asymmetric`
- `team_layout`: `1v1`, `2v2`, `3v3`, `4v4`, `ffa`, `odd`
- `spawn_roles`: `front|air|navy|eco|flex`
- `mex_pattern`: `sparse`, `standard`, `rich`, `clustered`, `contested`
- `hydro_pattern`: `none`, `near_spawn`, `contested`, `many`
- `reclaim_pattern`: `low`, `standard`, `high`, `field`, `civilian_base`

### Visual And Biome Labels

The look of the map matters, but not as the main label for the first structure-learning model.

Visual style should be separate because it mostly affects texture, decals, props, and biome priors. Gameplay structure is more about height, water, ramps, chokepoints, resources, spawn placement, and pathability.

- `biome`: `earth`, `desert`, `ice`, `lava`, `alien`, `urban`, `moon`, `mixed`
- `visual_style`: `natural`, `gpg_classic`, `faf_rework`, `high_detail`, `minimal`, `themed`
- `readability`: `clear`, `busy`, `confusing`

For early experiments, train on structure first. Later, biome/style can become conditioning metadata: "generate a Seton's-like mixed 4v4 layout, but with ice biome textures."

## Suggested Human Workflow

1. Run inventory against a map snapshot.
2. Generate or update `data/labels/map_labels.csv`.
3. Use the label CSV as an internal seed/admin table, not as the public community workflow.
4. Collect public labels through the crowd labeling app described in [crowd_labeling_app_spec.md](crowd_labeling_app_spec.md).
5. Store individual answers first, then aggregate into soft labels.
6. Use `duplicate_group` to mark map families before training splits.

## Seton's Clutch Example

```csv
map_dir,canonical_name,quality_tier,duplicate_group,primary_modes,secondary_modes,pace,lane_structure,expansion_pattern,symmetry,team_layout,spawn_roles,mex_pattern,hydro_pattern,reclaim_pattern,biome,visual_style,readability,notes
setons_clutch_-_faf_version.v0004,Setons Clutch - FAF version,S,setons_clutch,mixed,naval|air|land|teamgame,macro,laned|water_center,linear|contested_mid,rotational,4v4,front|air|navy|eco|flex,standard,near_spawn,high,earth,faf_rework,clear,popular mixed team map with navy air and land roles
```
