# Pre-Labeling ML Plan

This project can still make useful progress before community labels exist. Human labels will improve style, quality, and play-feel conditioning, but the raw map files already contain enough structure for baseline learning experiments.

## Current Goal

Build a bad-but-real ML loop before human labels:

1. Export verified map tensors.
2. Train tiny baselines.
3. Decode model outputs into concrete points and masks.
4. Score the outputs with objective metrics.
5. Use the failures to choose the next model, loss, and decoder.

The target is not a playable map yet. The target is proof that the tensor representation, training split, and model QA loop are sane.

## V0 Status

The first staged generation loop now exists:

1. `train_terrain_vae` trains a small terrain/water VAE on `height_norm`, `water_mask`, and `water_depth_norm`.
2. `sample_terrain_vae` can sample either pure random latents or encoded real-map latents with noise.
3. `rule_place_points` adds deterministic spawn, mex, and hydro heatmaps to generated terrain.
4. `rule_place_reclaim` adds a deterministic reclaim-density layer.

This V0 is intentionally crude. Pure random VAE samples tend to be too flat and weakly structured; encoded-latent variants are more map-like but still closer to map mutation than true from-scratch generation. That is acceptable for this milestone because it proves the generation, decoding, QA rendering, and metric loop are wired together.

## Focused 10km Adaptive Result

The first narrower dataset slice is:

- size class: `10km`
- audit status: `ready`
- name match: `adapt`
- tensor count: 293
- split counts from the family-safe split: 222 train, 44 validation, 27 test

This focused slice trained better than the broad all-map run.

Current observations:

- The 30-epoch terrain VAE reconstructs adaptive 10km terrain/water noticeably better than the broad model.
- Pure random VAE samples are still weak and nearly dry.
- Encoded-latent VAE variants are the best current generated-terrain source: they show recognizable 10km map-like terrain and coherent water bodies.
- A tiny 50-epoch DDPM reduced training/validation loss, but generated water remains fragmented into hundreds of tiny components. It is not yet better than encoded VAE variants.

Current practical path:

1. Use encoded VAE variants for crude generated terrain experiments.
2. Use `rule_place_points` and `rule_place_reclaim` to create full structural tensors.
3. Improve DDPM separately with a better architecture/schedule before trusting it as the main generator.

## Preferred Model Strategy

Use staged generation instead of one giant all-at-once model for V1.

### Stage 1: Terrain And Water

Inputs:

- map size class
- optional player count/team setting
- optional broad style tags later

Outputs:

- normalized height
- water mask
- water depth
- slope/buildable/passable masks can be derived or predicted

Why separate it:

- terrain and water are dense continuous fields
- validation is visual and geometric
- it can be trained without needing perfect resource labels

### Stage 2: Spawn, Mex, Hydro Placement

Inputs:

- generated or real terrain/water/passability
- desired player count/team setting
- desired mex/hydro density bucket later

Outputs:

- spawn heatmap
- mex heatmap
- hydro heatmap

Decoder:

- greedily extract local maxima
- enforce minimum distances
- snap to valid land/buildable/passable cells
- enforce symmetry when requested
- enforce count constraints from conditioning

Why separate it:

- these are sparse point decisions, not images
- ordinary MSE/BCE losses tend to produce vague blobs
- point-placement metrics are easy to inspect

### Stage 3: Reclaim And Civilian Density

Inputs:

- terrain/water
- decoded spawns/resources
- desired reclaim amount/distribution bucket later

Outputs:

- reclaim density field
- civilian structure density field

Decoder:

- sample entity clusters from density
- keep early reclaim near starts and contested reclaim near center/expansion areas
- preserve total mass/energy budget buckets

Why separate it:

- reclaim is partly decorative and partly gameplay-critical
- total amount matters, but distribution matters more
- it should be constrained by spawn/resource layout

## Baseline Experiments Before Labels

### A. Reconstruction Autoencoder

Purpose:

- proves tensor channels can round-trip through a small network
- catches normalization/channel bugs
- not expected to generate useful maps

Success signal:

- height/water/passability reconstruct visibly
- sparse channels remain hard, which is expected

### B. Terrain-To-Gameplay Predictor

Purpose:

- given real terrain, predict likely spawn/mex/hydro/reclaim/civ layers
- tests whether terrain geometry contains useful gameplay-placement signal

Current observed behavior:

- prediction produces broad low-confidence blobs
- decoded ground truth has crisp points
- decoded predictions are not yet acceptable as map design

Next fixes:

- evaluate point placement numerically
- train by map size/player-count subset first
- add count/team conditioning
- use point-aware losses instead of only dense heatmap losses

### C. Terrain/Water Generator

Purpose:

- first actual generative model should produce dense geometry only
- resource placement can come from Stage 2 or deterministic rules

Recommended first scope:

- train on one size class, probably common 10km/20km maps
- output only height, water depth, land/water
- validate with water-body count, shoreline, buildable percent, passability regions

## Objective Metrics To Track

### Dense Terrain Metrics

- height mean/std/range
- water percent
- water body count and largest water body percent
- shoreline length
- buildable percent
- passable percent
- plateau/access-region count
- base-to-base path availability if spawns exist

### Point Metrics

- spawn precision/recall within radius
- mex precision/recall within radius
- hydro precision/recall within radius
- mean matched distance
- missed real points
- extra predicted points

### Resource Distribution Metrics

- mexes per player/team
- hydros per player/team
- reclaim mass near spawn
- reclaim mass near center
- contested reclaim fraction
- distribution fairness between predicted teams

## Minimum Gate Before Diffusion

Do not start a full diffusion run until:

- tensor export is stable
- family-safe train/val/test splits exist
- one baseline can train and save predictions
- point-placement evaluation exists
- terrain/water metrics can compare generated maps to real maps
- we choose one narrow subset, not all 6k maps at once

## First Diffusion Scope

The first diffusion model should probably be terrain/water only.

Recommended subset:

- one map size class
- ready maps only, or ready + carefully reviewed maps
- no known duplicate leakage
- exclude broken/outlier maps

Recommended output channels:

- height_norm
- water_depth_norm
- water_mask

Derived after generation:

- land_mask
- slope_norm
- buildable_mask
- land_passable_mask

This keeps the first diffusion target dense and visual. Sparse gameplay objects can be placed by a second model or deterministic decoder after the generated terrain is plausible.

## Role Of Human Labels Later

Community labels should become:

- filter weights: train stronger on maps people rate highly
- conditioning tags: navy-heavy, land-heavy, turtle, aggressive, beautiful, unusual
- negative examples: maps rated bad can be excluded or used to teach quality models
- survey validation: compare algorithmic guesses with human perception

Human labels are most valuable after the raw parser and baseline loop are stable, because the survey can show useful extracted facts and avoid asking players to do machine-readable bookkeeping.
