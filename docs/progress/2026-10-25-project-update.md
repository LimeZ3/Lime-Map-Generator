# MapGen progress update — 25 October 2026

The [MapGen project atlas](https://mapgen-project-atlas.elven-bowl-7506.chatgpt.site) is the main project reference for status, map layers, data, selected models, experimental branches, results and open work. The project remains **experimental research software**, not a finished or competitively validated generator.

This update records progress since the initial repository snapshot. Evidence is the atlas catalog and saved receipts, refreshed 2026-10-25T12:52:30+00:00.

## Implemented and collected

### Map extraction and source representations

Terrain/water, starts, resource markers, natural energy/mass, wrecks, civilians and surface material representations have source receipts. Unknown values and unsupported runtime rules remain explicit.

Evidence: [docs/map_layers_v2.md](https://mapgen-project-atlas.elven-bowl-7506.chatgpt.site/?view=docs%2Fmap_layers_v2.html).

### Four selected generation stages

Terrain/water, resource markers, natural reclaim allocation and wreck allocation have selected checkpoints. Deterministic finishing/composition exports geometry, markers and entities.

Evidence: [docs/model-atlas/catalog.json](https://mapgen-project-atlas.elven-bowl-7506.chatgpt.site/?view=docs%2Fmodel-atlas%2Fcatalog.json).

### Dataset and texture preparation

The selected curated cohort contains 1,020 training and 97 validation maps. Texture extraction completed 1,117 maps with no decode failures; 929 albedo sources are fully resolved. Extraction success does not certify every shader’s training semantics.

Evidence: [docs/map_texture_tensors.md](https://mapgen-project-atlas.elven-bowl-7506.chatgpt.site/?view=docs%2Fmap_texture_tensors.html).

### Gameplay-analysis and annotation pipeline

Versioned route/front, resource-economy and air/drop analyses exist. The 3,108-version annotation-pool milestone reports 2,764 scored maps, 329 exclusions and 15 failures. These are heuristic 1v1 observations, not map-quality ground truth.

Evidence: [docs/map-rating-extraction/README.md](https://mapgen-project-atlas.elven-bowl-7506.chatgpt.site/?view=docs%2Fmap-rating-extraction%2FREADME.html).

### Joint source-layer experiment and diagnostics

A separate 73.3M-parameter network jointly predicts 13 source channels from noise and 12 rating controls. The 782/69 cohort and completed diagnostic arms are experimental; they do not replace the selected stages.

Evidence: [docs/joint_source_diagnostics.md](https://mapgen-project-atlas.elven-bowl-7506.chatgpt.site/?view=docs%2Fjoint_source_diagnostics.html).

### Navigable project atlas

Five exact FAF map versions, 19 comparison families, source/method links, model contracts, archived runs, global preview sliders and explicit extraction TODOs now organize the project.

Evidence: [docs/model-atlas/index.html](https://mapgen-project-atlas.elven-bowl-7506.chatgpt.site/?view=docs%2Fmodel-atlas%2Findex.html).

## Current evidence

- **4 selected trained stages**; **41 discovered checkpoint-bearing runs** are preserved as an inventory, not 41 active pipeline stages.
- **1020 train / 97 validation** in the selected curated cohort. No independent final test set is being claimed.
- **1117 texture extractions**, **929 fully resolved albedo sources**; learned painting is not selected.
- **5 exact map versions** across **19 source/derived comparison rows**.
- Separate joint experiment: **13 channels**, **782 train / 69 validation**; no selected production release.

- Selected terrain geometry and natural reclaim composition have been observed in game; resource markers were exported and playtested, with balance still unproven.
- Wreck allocation is trained and exported, but its current runtime behavior is not yet verified.
- The joint one-map baseline reproduced a spatial template (height correlation 0.9980 at update 2,365), while sparse-density totals remained badly biased (Start A integral 139.6 instead of one). This is memorization evidence, not generalization.
- The joint-source continuation ended by user request at update 22,947. The separate baseline/lower-LR/balanced one-map and lower-LR full-cohort diagnostic arms have saved completed receipts.

## Next work

- Correct DualGap Adaptive’s archived air pair (slot 12 used where the intended comparison needs slot 2).
- Improve main-base/rear/forward zoning, define contestability coherently and fill missing exact-version outputs.
- Add hover/navy battle-path comparisons and newer frontier coverage for FAF Beetles.
- Diagnose sparse-density/background errors and held-out behavior before selecting any joint-source checkpoint.
- Learned texture painting, civilian composition and spawn-layout generation remain planned or experimental, with exact boundaries in the catalog.
- Continue structuring completed work and the TODO list in this atlas; validate exports and gameplay rather than equating loss with playability.

The [maps extraction work queue](../map-extraction-todos.md) tracks known source/pairing/zoning issues and missing coverage. Reports using stock Setons/Beetles must not be presented as the selected FAF versions.

## Keeping this current

The atlas is the authoritative project index; this report is a dated snapshot. After meaningful progress, update the atlas catalog/status/work queue, refresh the saved evidence, and publish the public atlas snapshot. The ChatGPT Site checks GitHub for a newer snapshot every minute while open. This is publication-driven updating, not automatic access to uncommitted local files or a claim that training is continuously monitored. Hosting uses ChatGPT Sites, not Netlify.

Original project code is MIT licensed. Existing maps and game assets retain their respective owners; the atlas identifies their versions and treats their previews as reference material.
