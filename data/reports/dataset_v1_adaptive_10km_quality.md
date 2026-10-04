# dataset_v1_adaptive_10km Quality Report

Created UTC: `2026-07-12T15:08:49.171589+00:00`

## Snapshot

- maps: `293`
- missing split rows: `0`
- missing tensor files: `0`
- family split leaks: `0`

## Split Counts

- `train`: `222`
- `val`: `44`
- `test`: `27`

## Numeric Summary

- `player_slots`: min `2.0`, median `12.0`, mean `11.426621`, p95 `16.0`, max `16.0`
- `spawn_count`: min `2.0`, median `12.0`, mean `11.426621`, p95 `16.0`, max `16.0`
- `mex_count`: min `30.0`, median `118.0`, mean `118.904437`, p95 `165.4`, max `256.0`
- `hydro_count`: min `0.0`, median `14.0`, mean `13.911263`, p95 `22.0`, max `44.0`
- `water_percent`: min `0.0`, median `12.1861`, mean `21.409062`, p95 `65.92832`, max `93.7182`
- `buildable_percent`: min `1.2501`, median `55.92`, mean `52.208648`, p95 `78.19318`, max `85.3134`
- `height_min`: min `0.0`, median `10.492188`, mean `18.064606`, p95 `56.858203`, max `121.460938`
- `height_max`: min `16.0`, median `44.115234`, mean `50.626807`, p95 `92.626563`, max `160.0`

## Team Settings

- `6v6`: `96`
- `5v5`: `77`
- `8v8`: `44`
- `7v7`: `20`
- `4v4`: `19`
- `3v3`: `11`
- `2v2`: `9`
- `4v4v4v4`: `5`
- `1v1v1v1_or_2v2`: `4`
- `2v2v2v2v2v2v2v2`: `2`
- `2v2v2v2`: `2`
- `3v3v3v3`: `2`
- `2v2v2v2v2v2`: `1`
- `1v1`: `1`

## Family Split Audit

No family/duplicate split leakage detected in this subset.

## Inputs

- `tensor_manifest`: `data\tensors\v1_adaptive_10km\tensor_manifest.csv`
- `tensor_manifest_sha256`: `3efd209bfaaaf63e8278adc95551dda6d7aafbf9ea73b7cee67c0a07567b688d`
- `splits_csv`: `data\splits\v1_current\splits.csv`
- `splits_csv_sha256`: `828a62581540ed050dc6564ae18f0e706c8d53fd42938f18cc86537e862634ba`
- `audit_maps_csv`: `data\audit\v1_current\dataset_audit_maps.csv`
- `audit_maps_csv_sha256`: `2acad300dc9c9d5fbffea320de955ed6954bb022090e4d41d4d13743c32b79cf`
