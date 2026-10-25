# Lime Map Generator (MapGen)

An open-source study project for the AI Systems course at Fontys in the Netherlands, exploring neural networks for Supreme Commander: Forged Alliance map generation. The tooling is Windows-first.

**Status: experimental research software, not a finished or competitively validated map generator.**

**[MapGen project atlas — live project status](https://mapgen-project-atlas.elven-bowl-7506.chatgpt.site)** is now the main source of truth for map layers, data, selected models, experiments, results and next work. It is hosted with ChatGPT Sites and reads versioned public snapshots from this GitHub repository.

Read the [25 October 2026 progress update](docs/progress/2026-10-25-project-update.md), the [maps extraction work queue](docs/map-extraction-todos.md), and the [publication/update workflow](docs/atlas-publication.md). The atlas checks for new published snapshots every minute; uncommitted local files are not monitored.

The recorded progress includes four selected trained stages, a 1,020 train / 97 validation curated cohort, 1,117 texture extractions, and separate joint-generation/diagnostic experiments. These are experimental results, with unproven balance and explicit runtime/data limitations. No experimental joint checkpoint is promoted to a selected release by this update.

## Who is building this, and how?

I am a mechatronics student with student-level C++ experience. My current Python and general software development skills are not sufficient to build this entire project independently, so I rely heavily on AI coding agents for implementation. I guide that work through development strategy and planning informed by my course. Learning to direct, inspect, and evaluate AI-assisted development is part of the study project.

I remain responsible for what I publish. AI-generated implementation is not evidence of correctness; the documentation distinguishes experimental tools, recorded results, and work that still needs validation.

I have more than ten years of gaming experience and intend to continue playing and developing this project beyond the course. Progress will depend on study and other commitments; the repository is intended to make the work and next steps visible.

## Why investigate neural networks?

Perlin noise can generate terrain variation, while procedural generators add rules for layout, resources, and playability. This project investigates whether a neural network can learn useful relationships between terrain, starting positions, resources, reclaim, and access routes from existing maps. Community annotations may eventually help describe and condition gameplay styles.

This is a hypothesis, not a demonstrated advantage over established generators such as Neroxis. Learned models can reproduce poor patterns or familiar layouts. Deterministic checks and in-game playtesting remain necessary, and terrain similarity alone does not establish gameplay quality.

This is a new project, not a fork of `FAForever/Neroxis-Map-Generator`. The first goal is not to produce beautiful final maps. The first goal is to find out whether neural networks can learn useful SupCom map structure from real map data.

## Direction

The intended pipeline is:

```text
existing maps
-> dataset extractor
-> normalized tensor representation
-> ML model
-> generated tensor map
-> deterministic decoder/validator
-> eventual playable map export
```

The project should train on structural layers, not preview images alone:

- heightmap
- land/water masks
- slope/buildable/passable masks where recoverable
- spawn heatmaps
- mex heatmaps
- hydro heatmaps
- reclaim density
- metadata such as map size, player count, quality tier, symmetry, and style labels

## Current Status

The repository contains implementations for:

- map inventory, terrain and entity extraction, and structural metrics
- dataset audits, tensor preparation, and map-family-aware splits
- experimental autoencoder, channel predictor, VAE, and diffusion training/sampling
- rule-based placement, structural validation, and experimental FAF export
- a React community annotation app with local review and hosted collection modes

The existence of these tools does not mean their outputs are balanced or ready for competitive play. Passability and buildability masks are estimates rather than authoritative game-engine results. See [the focused dataset snapshot](docs/dataset_v1_adaptive_10km_snapshot.md) for recorded experiment context.

Next steps are to collect community feedback, evaluate generated structure against procedural baselines, and test exported maps in-game before making quality claims.

## Repository contents and licensing

Original project code is available under the [MIT License](LICENSE). This license does not grant rights to third-party maps, game assets, dependencies, or community submissions. Existing map names, metadata, and derived previews identify source material belonging to its respective creators; they are not maps generated by this project.

Raw maps, trained weights, local inventories, participant-response exports, and private study drafts are excluded. The annotation app includes generated map catalog data, not collected player responses. To reproduce extraction or training, obtain the required maps separately and follow the commands below; a source checkout alone does not contain the training dataset.

## Windows Environment

Use Python 3.11 or 3.12 for PyTorch. The default Python on this machine may be newer than PyTorch supports, so install Python 3.12 if needed from:

https://www.python.org/downloads/windows/

During install, enable **Add python.exe to PATH**, or use the Windows `py` launcher.

### Option A: uv

If `uv` is installed:

```powershell
uv venv --python 3.12
.\.venv\Scripts\Activate.ps1
uv pip install -e .
uv pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
```

Check the current PyTorch Windows CUDA install selector if you want a newer CUDA wheel:

https://pytorch.org/get-started/locally/

### Option B: venv and pip

If `uv` is not installed:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
python -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
```

If `py -3.12` is not found, install Python 3.12 first or use Python 3.11:

```powershell
py -3.11 -m venv .venv
```

## CUDA Smoke Test

After installing PyTorch, run:

```powershell
python -m supmapai.tools.cuda_check
```

The script reports:

- Python version
- PyTorch version
- whether CUDA is available
- CUDA runtime version exposed by PyTorch
- detected GPU names
- a tiny tensor operation on the CUDA device when available

## Inventory A Map Dataset

Point the inventory tool at a folder containing extracted SupCom map folders:

```powershell
python -m supmapai.extract.inventory --maps-root "D:\Path\To\Maps" --out data\manifests\inventory.json
```

The tool scans recursively and groups likely map files by directory:

- `.scmap`
- `_scenario.lua`
- `_save.lua`
- preview-like images

Generated manifests under `data\manifests\*.json` are gitignored by default because they may contain local paths. Keep raw map data under `data\raw\` or another ignored folder.

For FAF downloads, use the canonical inventory as the main source for survey/training data. It treats each immediate folder under the FAF maps root as one map and selects the best internal version when backup/version folders are present:

```powershell
python -m supmapai.extract.canonical_inventory --maps-root "C:\Program Files (x86)\Steam\steamapps\common\FAF_modsmaps\maps" --out data\manifests\faf_modsmaps_canonical_inventory.json
```

Create a human-editable label sheet from the inventory:

```powershell
python -m supmapai.extract.labels_from_inventory --inventory data\manifests\inventory.json --out data\labels\map_labels.csv
```

Extract first-pass metadata for survey display and dataset filtering:

```powershell
python -m supmapai.extract.metadata_from_inventory --inventory data\manifests\faf_modsmaps_canonical_inventory.json --out data\interim\faf_modsmaps_canonical_metadata.csv
```

Extract detailed Lua entities and a flat summary:

```powershell
python -m supmapai.extract.lua_entities --inventory data\manifests\faf_modsmaps_canonical_inventory.json --out data\interim\faf_modsmaps_lua_entities.jsonl --summary-out data\interim\faf_modsmaps_lua_entities_summary.csv
```

Decode terrain metrics for one `.scmap` at a time. This command is intentionally guarded by `--max-maps 1` by default:

```powershell
python -m supmapai.extract.scmap_terrain --inventory data\manifests\faf_modsmaps_canonical_inventory.json --map-dir "setons_clutch_-_faf_version.v0004" --out data\interim\terrain_setons.csv --preview-dir data\interim\structural_previews
```

Find likely duplicate, version, and variant families by normalized map names:

```powershell
python -m supmapai.extract.name_families --metadata data\interim\faf_modsmaps_canonical_metadata.csv --out data\interim\faf_modsmaps_canonical_name_families.csv --summary-out data\interim\faf_modsmaps_canonical_name_families_summary.json
```

Build the first flat V1 feature table and survey seed:

```powershell
python -m supmapai.extract.features_v1 --metadata data\interim\faf_modsmaps_canonical_metadata.csv --entities data\interim\faf_modsmaps_lua_entities.jsonl --name-families data\interim\faf_modsmaps_canonical_name_families.csv --out data\processed\features_v1\map_features_v1.csv --survey-out apps\crowd-labeler\src\data\maps.generated.json
```

Infer likely team layouts from spawn positions and per-spawn resource assignment:

```powershell
python -m supmapai.extract.team_layout --markers data\interim\batches\batch_0018\batch_0018_markers.csv --resource-balance data\interim\batches\batch_0018\batch_0018_resource_balance.csv --out data\interim\batches\batch_0018\batch_0018_team_layout.csv --summary-out data\interim\batches\batch_0018\batch_0018_team_layout_summary.json
```

This is a heuristic, not truth data. It compares plausible layouts such as `1v1v1v1`, `2v2v2`, `4v4`, and `5v5` by grouping spawns and checking whether team-level mex, hydro, and reclaim totals become more balanced than per-spawn totals.

The team-layout output includes `predicted_team_setting`, a survey-friendly field that may contain flexible settings such as `1v1v1v1_or_2v2` when an all-vs-all spawn pattern can reasonably morph into a team game.

Extract Structure Metrics V1 for water bodies, shoreline, plateau/access regions, base-to-base land paths, and reclaim distribution:

```powershell
python -m supmapai.extract.structure_metrics --inventory data\manifests\batches_250_no_neroxis\batch_0018_inventory.json --terrain data\interim\batches\batch_0018\batch_0018_terrain.csv --markers data\interim\batches\batch_0018\batch_0018_markers.csv --entities data\interim\batches\batch_0018\batch_0018_entities.csv --team-layout data\interim\batches\batch_0018\batch_0018_team_layout.csv --out data\interim\batches\batch_0018\batch_0018_structure_metrics.csv --max-maps 250
```

To carry team and structure fields into the flat feature table and survey seed, pass both CSVs:

```powershell
python -m supmapai.extract.features_v1 --metadata data\interim\batches\batch_0018\batch_0018_metadata.csv --entities data\interim\batches\batch_0018\batch_0018_lua_entities.jsonl --name-families data\interim\batches\batch_0018\batch_0018_name_families.csv --terrain data\interim\batches\batch_0018\batch_0018_terrain.csv --scmap-props-summary data\interim\batches\batch_0018\batch_0018_scmap_props_summary.csv --team-layout data\interim\batches\batch_0018\batch_0018_team_layout.csv --structure-metrics data\interim\batches\batch_0018\batch_0018_structure_metrics.csv --out data\interim\batches\batch_0018\batch_0018_map_features_v1.csv --survey-out data\interim\batches\batch_0018\batch_0018_maps.generated.json
```

Audit completed batch outputs for readiness, warnings, duplicate/name-family groups, and statistical outliers:

```powershell
python -m supmapai.tools.dataset_audit --batches-root data\interim\batches --out-dir data\audit\v1_current
```

The audit writes `dataset_audit_summary.json`, `dataset_audit_maps.csv`, `dataset_audit_outliers.csv`, `dataset_audit_warnings.csv`, and `dataset_audit_families.csv`. It is non-destructive: `exclude_candidate` means “do not feed to training automatically,” not “delete this map.”

Export a small ML-ready tensor smoke-test set:

```powershell
python -m supmapai.tensors.export_tensors --inventory data\manifests\batches_250_no_neroxis\batch_0024_inventory.json --features data\interim\batches\batch_0024\batch_0024_map_features_v1.csv --markers data\interim\batches\batch_0024\batch_0024_markers.csv --entities data\interim\batches\batch_0024\batch_0024_entities.csv --audit-maps data\audit\v1_current\dataset_audit_maps.csv --audit-status ready --audit-status review --out-dir data\tensors\v1_smoke\batch_0024 --manifest-out data\tensors\v1_smoke\batch_0024_manifest.csv --max-maps 2 --grid-size 256
```

Render tensor channel contact sheets for visual QA:

```powershell
python -m supmapai.tensors.contact_sheet --manifest data\tensors\v1_smoke\batch_0024_manifest.csv --out-dir data\tensors\v1_smoke\qa --max-maps 2
```

Each `.npz` contains a `tensor` array shaped `[channels, 256, 256]` plus channel names. V1 channels are height, water, water depth, land/passable/buildable masks, slope, spawn/mex/hydro heatmaps, reclaim density, and civilian structure density.

Create family-safe train/validation/test splits from the audit:

```powershell
python -m supmapai.tensors.split_dataset --audit-maps data\audit\v1_current\dataset_audit_maps.csv --out data\splits\v1_current\splits.csv --summary-out data\splits\v1_current\splits_summary.json
```

Export all `ready` + `review` tensors batch-by-batch:

```powershell
python -m supmapai.tensors.export_tensor_batches --batch-manifest data\manifests\batches_250_no_neroxis\batch_manifest.json --audit-maps data\audit\v1_current\dataset_audit_maps.csv --out-root data\tensors\v1 --combined-manifest data\tensors\v1\tensor_manifest.csv --logs-dir data\tensors\v1\logs --grid-size 256 --continue-on-failure
```

Compute tensor channel statistics:

```powershell
python -m supmapai.tensors.tensor_stats --manifest data\tensors\v1\tensor_manifest.csv --out data\tensors\v1\tensor_stats.csv --summary-out data\tensors\v1\tensor_stats_summary.json
```

Create a focused tensor manifest for a narrow experiment:

```powershell
python -m supmapai.tensors.filter_manifest --manifest data\tensors\v1\tensor_manifest.csv --out data\tensors\v1_adaptive_10km\tensor_manifest.csv --summary-out data\tensors\v1_adaptive_10km\summary.json --size-class 10km --audit-status ready --name-regex adapt
```

Create a focused dataset quality report and split/family audit for the adaptive 10km subset:

```powershell
python -m supmapai.tools.dataset_quality_report --tensor-manifest data\tensors\v1_adaptive_10km\tensor_manifest.csv --splits-csv data\splits\v1_current\splits.csv --audit-maps data\audit\v1_current\dataset_audit_maps.csv --dataset-name dataset_v1_adaptive_10km --json-out data\reports\dataset_v1_adaptive_10km_quality.json --csv-out data\reports\dataset_v1_adaptive_10km_quality.csv --md-out data\reports\dataset_v1_adaptive_10km_quality.md
```

Train the first tiny autoencoder baseline:

```powershell
python -m supmapai.ml.train_autoencoder --tensor-manifest data\tensors\v1\tensor_manifest.csv --splits-csv data\splits\v1_current\splits.csv --out-dir data\models\autoencoder_v1 --epochs 10 --batch-size 8 --max-train-maps 1000 --max-val-maps 200 --device cuda
```

Train the terrain-to-gameplay predictor baseline:

```powershell
python -m supmapai.ml.train_channel_predictor --tensor-manifest data\tensors\v1\tensor_manifest.csv --splits-csv data\splits\v1_current\splits.csv --out-dir data\models\channel_predictor_v1 --epochs 10 --batch-size 8 --max-train-maps 1000 --max-val-maps 200 --device cuda
```

Train the first terrain/water generator baseline:

```powershell
python -m supmapai.ml.train_terrain_vae --tensor-manifest data\tensors\v1\tensor_manifest.csv --splits-csv data\splits\v1_current\splits.csv --out-dir data\models\terrain_vae_v0 --epochs 10 --batch-size 8 --max-train-maps 1000 --max-val-maps 200 --sample-count 8 --device cuda
```

For the current best pre-labeling terrain experiment, train on ready 10km adaptive maps only:

```powershell
python -m supmapai.ml.train_terrain_vae --tensor-manifest data\tensors\v1_adaptive_10km\tensor_manifest.csv --splits-csv data\splits\v1_current\splits.csv --out-dir data\models\terrain_vae_adaptive_10km_v0 --epochs 30 --batch-size 8 --kl-weight 0.001 --sample-count 12 --device cuda
```

Render and evaluate terrain/water samples:

```powershell
python -m supmapai.ml.generated_sheet --input-dir data\models\terrain_vae_v0\samples --out-dir data\models\terrain_vae_v0\sample_sheets --max-items 8
python -m supmapai.ml.evaluate_terrain_samples --samples-dir data\models\terrain_vae_v0\samples --out data\models\terrain_vae_v0\sample_metrics.csv --summary-out data\models\terrain_vae_v0\sample_metrics_summary.json
```

Sample terrain variants by perturbing encoded real-map latents:

```powershell
python -m supmapai.ml.sample_terrain_vae --checkpoint data\models\terrain_vae_v0\best.pt --tensor-manifest data\tensors\v1\tensor_manifest.csv --splits-csv data\splits\v1_current\splits.csv --split val --out-dir data\models\terrain_vae_v0\encoded_samples_noise025 --mode encoded --sample-count 8 --noise-scale 0.25 --device cuda
```

Train the first tiny terrain/water DDPM baseline:

```powershell
python -m supmapai.ml.train_terrain_ddpm --tensor-manifest data\tensors\v1_adaptive_10km\tensor_manifest.csv --splits-csv data\splits\v1_current\splits.csv --out-dir data\models\terrain_ddpm_adaptive_10km_v0 --epochs 50 --batch-size 8 --diffusion-steps 100 --sample-count 8 --device cuda
python -m supmapai.ml.sample_terrain_ddpm --checkpoint data\models\terrain_ddpm_adaptive_10km_v0\best.pt --out-dir data\models\terrain_ddpm_adaptive_10km_v0\best_samples --sample-count 8 --device cuda
```

Place first-pass deterministic gameplay points and reclaim on one generated terrain:

```powershell
python -m supmapai.ml.rule_place_points --input data\models\terrain_vae_v0\encoded_samples_noise025\terrain_sample_0001.generated.npz --out data\outputs\generated_v0\terrain_sample_0001.points.npz --metadata-out data\outputs\generated_v0\terrain_sample_0001.points.json --preview-out data\outputs\generated_v0\terrain_sample_0001.points.png --players 4 --mex-per-spawn 4 --center-mexes 4 --hydros-per-spawn 1
python -m supmapai.ml.rule_place_reclaim --input data\outputs\generated_v0\terrain_sample_0001.points.npz --point-metadata data\outputs\generated_v0\terrain_sample_0001.points.json --out data\outputs\generated_v0\terrain_sample_0001.full.npz --metadata-out data\outputs\generated_v0\terrain_sample_0001.reclaim.json --preview-out data\outputs\generated_v0\terrain_sample_0001.reclaim.png
python -m supmapai.ml.generated_sheet --input-dir data\outputs\generated_v0 --out-dir data\outputs\generated_v0\sheets --max-items 8
```

Export a generated structure as a local FAF map folder with generated terrain written into the `.scmap` heightmap:

```powershell
python -m supmapai.export.faf_map_v0 --generated-tensor data\outputs\generated_adaptive_10km_v0\terrain_sample_0002.full.npz --point-metadata data\outputs\generated_adaptive_10km_v0\terrain_sample_0002.points.json --reclaim-metadata data\outputs\generated_adaptive_10km_v0\terrain_sample_0002.reclaim.json --template-scmap "C:\Program Files (x86)\Steam\steamapps\common\FAF_modsmaps\Allmaps\adaptive_acid_lakes.v0005\adaptive_acid_lakes.scmap" --out-root data\exports\maps --folder-name mapgen_ml_demo_terrain.v0001 --map-name "MapGen ML Terrain Demo" --players 4 --map-size 512 --max-reclaim-units 70 --scmap-terrain generated
```

The V1 `.scmap` writer only replaces the raw heightmap vertex block. It preserves template textures, decals, props, water shader data, and embedded `.scmap` preview bytes. Use `--scmap-terrain template` to keep the older copied-template terrain behavior for comparison.

Run the basic validator by itself when you want to inspect repaired starts/resources/reclaim before export:

```powershell
python -m supmapai.export.validator --generated-tensor data\outputs\generated_adaptive_10km_v0\terrain_sample_0002.full.npz --point-metadata data\outputs\generated_adaptive_10km_v0\terrain_sample_0002.points.json --reclaim-metadata data\outputs\generated_adaptive_10km_v0\terrain_sample_0002.reclaim.json --points-out data\outputs\generated_adaptive_10km_v0\terrain_sample_0002.validated.points.json --reclaim-out data\outputs\generated_adaptive_10km_v0\terrain_sample_0002.validated.reclaim.json --report-out data\outputs\generated_adaptive_10km_v0\terrain_sample_0002.validator_report.json --preview-out data\outputs\generated_adaptive_10km_v0\terrain_sample_0002.validated.preview.png --players 4 --max-reclaim-points 70
```

The FAF exporter runs this validator by default. Pass `--no-validate-structure` only when intentionally comparing raw generated placements against repaired placements.

Verify the written terrain by decoding the exported `.scmap`:

```powershell
python -m supmapai.extract.scmap_terrain --scmap data\exports\maps\mapgen_ml_demo_terrain.v0001\mapgen_ml_demo_terrain.scmap --out data\exports\maps\mapgen_ml_demo_terrain.v0001\terrain_decode.csv --preview-dir data\exports\maps\mapgen_ml_demo_terrain.v0001\decode_previews
```

Render prediction sheets and score decoded spawn/mex/hydro placement:

```powershell
python -m supmapai.ml.reconstruction_sheet --input-dir data\models\channel_predictor_v1\predictions --out-dir data\models\channel_predictor_v1\qa --max-items 8
python -m supmapai.ml.evaluate_heatmap_points --predictions-dir data\models\channel_predictor_v1\predictions --tensor-manifest data\tensors\v1\tensor_manifest.csv --out data\models\channel_predictor_v1\point_metrics.csv --summary-out data\models\channel_predictor_v1\point_metrics_summary.json
```

This point metric is intentionally narrow. It checks whether decoded spawn, mex, and hydro heatmap peaks land close to real markers. Reclaim and civilian structures are density fields and should be evaluated separately.

See [docs/pre_labeling_ml_plan.md](docs/pre_labeling_ml_plan.md) for the baseline ML roadmap before human labels, [docs/dataset_labeling.md](docs/dataset_labeling.md) for the recommended multi-label taxonomy, [docs/deduplication_policy.md](docs/deduplication_policy.md) for clone/version handling, [docs/dataset_v1_adaptive_10km_snapshot.md](docs/dataset_v1_adaptive_10km_snapshot.md) for the current focused dataset snapshot, [docs/windows_environment.md](docs/windows_environment.md) for Windows environment notes, and [docs/crowd_labeling_app_spec.md](docs/crowd_labeling_app_spec.md) for the public questionnaire app plan.

For the concrete V1 map-processing contract, see [docs/map_processing_v1.md](docs/map_processing_v1.md).

## Crowd Labeling App

The first public questionnaire MVP lives in `apps/crowd-labeler`. It imports the current label CSV as seed map data, shows one map at a time, asks a small rotating set of questions, stores append-only local response rows, and exports raw or aggregated labels.

```powershell
cd apps\crowd-labeler
npm.cmd install
npm.cmd run dev
```

The Supabase schema for the hosted version is in `apps/crowd-labeler/supabase/schema.sql`.

## Milestones

1. Inventory the good-map dataset and inspect how consistent the folder structure is.
2. Write a parser for `_scenario.lua` metadata and marker locations.
3. Decode `.scmap` heightmap and texture/resource information.
4. Convert each map into a normalized tensor bundle plus metadata JSON.
5. Train a tiny baseline model on one map size and one player-count range.
6. Build a deterministic validator before attempting playable export.
