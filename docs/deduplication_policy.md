# Deduplication And Originality Policy

The dataset should keep enough information to learn from variants, but avoid letting clones, backups, old versions, and reskins dominate training.

For FAF downloads, one map means one immediate folder under:

```text
C:\Program Files (x86)\Steam\steamapps\common\FAF_modsmaps\maps
```

Nested `Backup_*` or version folders inside that folder are candidate versions of the same map, not independent maps.

## First-Pass Signals

Use name-family detection before expensive terrain similarity:

```powershell
python -m supmapai.extract.canonical_inventory --maps-root "C:\Program Files (x86)\Steam\steamapps\common\FAF_modsmaps\maps" --out data\manifests\faf_modsmaps_canonical_inventory.json
python -m supmapai.extract.metadata_from_inventory --inventory data\manifests\faf_modsmaps_canonical_inventory.json --out data\interim\faf_modsmaps_canonical_metadata.csv
```

```powershell
python -m supmapai.extract.name_families --metadata data\interim\faf_modsmaps_canonical_metadata.csv --out data\interim\faf_modsmaps_canonical_name_families.csv --summary-out data\interim\faf_modsmaps_canonical_name_families_summary.json
```

The report groups maps by a normalized name and flags:

- version tokens such as `v2`, `.v0004`, `final`
- variant tokens such as `adaptive`, `faf`, `flooded`, `winter`, `1v1`, `teamplay`
- nested backup paths
- families with different player counts or map sizes

The canonical source pass also records simple name signals for survey display and filtering:

- `adaptive`: generally a useful/generated map family signal
- `crater`: likely similar naming family, often worth quality review
- `gap`: likely similar naming family, often worth quality review
- `pass`: includes `pass` and `passage`, likely similar naming family, often worth quality review

## Recommended Handling

- **Exact old versions:** keep metadata, train on the newest/best-known version unless the old version is intentionally different.
- **Backup folders:** exclude from training by default.
- **Adaptive/AI variants:** keep as variants, but do not let them form independent train/test examples against their base map.
- **Special terrain variants:** keep if they meaningfully change gameplay, for example flooded/naval versions.
- **Reskins:** keep for visual/style studies, but avoid overcounting them for structure training.
- **Bad maps:** keep if labeled as low quality. They can be useful negative examples.

## Human Review Fields

The crowd labeling app should occasionally ask:

- Is this a clone, remake, or reskin of a better-known map?
- What map does it resemble?
- Is this the version people should usually play?
- How original is this map?

These answers should become review signals, not automatic deletion rules.

## Training Split Rule

All maps in the same duplicate/version family should stay in the same train/validation/test split. Otherwise the model can see one version during training and appear to perform well on a near-copy during validation.
