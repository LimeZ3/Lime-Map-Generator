# Dataset V1 Adaptive 10km Snapshot

This snapshot records the first focused training subset used for the pre-labeling terrain experiments.

## Identity

- Dataset name: `dataset_v1_adaptive_10km`
- Tensor manifest: `data\tensors\v1_adaptive_10km\tensor_manifest.csv`
- Splits: `data\splits\v1_current\splits.csv`
- Audit source: `data\audit\v1_current\dataset_audit_maps.csv`
- Quality report JSON: `data\reports\dataset_v1_adaptive_10km_quality.json`
- Quality report CSV: `data\reports\dataset_v1_adaptive_10km_quality.csv`
- Quality report Markdown: `data\reports\dataset_v1_adaptive_10km_quality.md`

## Current Counts

- Maps: `293`
- Tensor grid: `256x256`
- Audit status: `ready` only
- Size class: `10km` only
- Filter logic: adaptive-map name filter over V1 tensors

## Split Counts

- Train: `222`
- Validation: `44`
- Test: `27`

## Quality Checks

- Missing split rows: `0`
- Missing tensor files: `0`
- Family split leaks: `0`
- Family groups in subset: `292`

## Distribution Notes

- Player slots median: `12`
- Water percent median: `12.1861`
- Water percent mean: `21.409062`
- Buildable percent median: `55.92`
- Mex count median: `118`
- Hydro count median: `14`

The subset is strongly skewed toward larger team-game layouts. The most common predicted team settings are `6v6`, `5v5`, and `8v8`. This is acceptable for the current adaptive 10km experiment, but it is not representative of all FAF maps or of 1v1 map design.

## Rebuild Command

```powershell
python -m supmapai.tools.dataset_quality_report --tensor-manifest data\tensors\v1_adaptive_10km\tensor_manifest.csv --splits-csv data\splits\v1_current\splits.csv --audit-maps data\audit\v1_current\dataset_audit_maps.csv --dataset-name dataset_v1_adaptive_10km --json-out data\reports\dataset_v1_adaptive_10km_quality.json --csv-out data\reports\dataset_v1_adaptive_10km_quality.csv --md-out data\reports\dataset_v1_adaptive_10km_quality.md
```

## Input Hashes

From the generated quality report:

- `tensor_manifest_sha256`: `3efd209bfaaaf63e8278adc95551dda6d7aafbf9ea73b7cee67c0a07567b688d`
- `splits_csv_sha256`: `828a62581540ed050dc6564ae18f0e706c8d53fd42938f18cc86537e862634ba`
- `audit_maps_csv_sha256`: `2acad300dc9c9d5fbffea320de955ed6954bb022090e4d41d4d13743c32b79cf`
