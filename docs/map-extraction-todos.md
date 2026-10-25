# Maps extraction work queue — atlas review

Open tasks from the 25 October 2026 project-atlas reviews. The current atlas
shows existing saved scientific outputs; it does not repair these data issues.
This is a handoff document for future maps extraction/analysis work, not a
scheduled job or a claim that another agent has started it.

## EXTRACT-01 DualGap air slot pair

**Open — user-visible incorrect scenario.** Exact map: DualGap Adaptive by
Robustness, `8070_26498`, `dualgap_adaptive.v0014` (2 July 2023).

The user reports that the source render is correct but the factual air-mask
render is wrong because the second player is positioned incorrectly. Inspection
confirms a mismatch between saved analysis families:

| Evidence | Slot 1 world x,z | Opposing slot and world x,z |
|---|---|---|
| Extracted markers | 112.5, 390.5 | ARMY_2: 911.4999, 390.5 |
| Historical air scenario | 112.5, 390.5 | ARMY_12: 909.5, 639.5 |
| Newer frontier scenario | 112.5, 390.5 | ARMY_2: approximately 911.5, 390.5 |

Source evidence:

- [Extracted slots](../data/processed/project_atlas_v1/8070_26498/markers.json)
- [Historical air analysis](../data/processed/strategy_collection_1v1/8070_26498/opportunities.json)
- [Historical per-side masks](../data/processed/strategy_collection_1v1/8070_26498/automatic_layers.npz)
- [Newer frontier inputs and paths](../data/processed/frontier_map_comparison/8070_26498/result.json)

TODO: trace slot selection, coordinate orientation and scenario identity through
extraction, historical analysis and rendering. Use the intended ARMY_1 vs ARMY_2
scenario consistently. Check expansion drops, offensive drops and raids, and
regenerate the affected scientific outputs under an explicit new release when
that work is undertaken. Validate positions against the source map. Never move
an old mask or rename ARMY_12 to ARMY_2 to conceal the mismatch. Preserve the
old receipt as history and document whether the root cause is selection,
coordinate handling, rendering, or several of these.

The atlas currently shows both actual archived masks with an explicit warning:
orange is **slot 12**, not the requested slot 2. That is disclosure, not a fix.

## EXTRACT-02 Battle-path movement layers

**Open.** Atlas battle paths currently cover **land only**. The display now
uses both saved K3 approaches: blue slot 1, orange slot 2; separate rotational
frontier contacts are not joined. FAF Beetles uses an explicitly labeled older
whole-map route fallback, colored by endpoint side.

TODO: add hover and navy battle-path evidence for the five exact atlas versions.
Historical hover routes already exist in `strategy_collection_1v1/<key>/routes.json`;
they are not automatically the same model as newer K3 frontier paths. Define and
record the movement profile, routing method, spawn pair and settings. Locate
usable navy results or record/implement the missing stage; do not substitute
amphibious routes for navy. Keep land/hover/navy individually selectable and
label disconnected or unavailable cases. Newer frontier output for FAF Beetles
`10838_21065` is still missing from the checked comparison.

## EXTRACT-03 Main-base rear forward zoning

**Open — user reports visible errors.** Existing saved zoning is now drawn with
adjustable fill opacity (default 100%), but the extraction/definition has not been corrected.

TODO: review near-base/rear/forward definitions, source slots, reachable movement
space, boundaries, target assignments and the relationship of dense zone masks
to actual resource records. Inspect the user-visible inconsistencies before
choosing a correction; do not tune per-map thresholds merely to match an image.
Verify each new release against the saved source and selected scenario.

Existing exact-version v1.2.1 results: Canis `4617_6826`, Tabula `9675_18616`,
DualGap `8070_26498`, under
`data/processed/strategy_annotation_batch/v1.2.1/f1ae04e925f139a8/jobs/<key>/whole_economy/`.

TODO: missing exact-version whole-economy outputs for Setons FAF `8553_17709`
and FAF Beetles `10838_21065`. Stock `433_560` and `4822_7169` are different
versions and must not be substituted.

## EXTRACT-04 Contestability and resource zones

**Open — definition and implementation need work.** Explain why the current
contestable-region view differs from main-base/rear/forward resource zoning.
The current fields come from different analyses: historical air/opportunity
territory classifications versus newer whole-economy location/access roles.

TODO: establish a coherent vocabulary and explicit relationships between location
(main-base/rear/forward), accessibility, opponent response, neutral ownership and
contestability. Decide whether contestability is a separate axis or a derived
zone class; record its units, assumptions and inference-time meaning. Update
implementation and compare the same map version and spawn pair. Do not label all
forward resources contested or all rear resources safe without a definition.
Keep current masks marked provisional until reviewed.

## Accepted and presentation rules

- Walk access and access structure are accepted by the user. Preserve their
  scientific meaning; the global mask slider changes display alpha only.
- Global sidebar sliders range 0–100: background brightness defaults to 10 and
  mask opacity to 100. This supersedes the earlier fixed 50% fill rule. Layer PNGs
  have full base opacity; source tensor values and classifications stay unchanged.
- Official vault context stays separate from tensor data; its brightness is independently adjustable (default 10%).
- Each side-specific field must name its source slot. Normally blue is SLOT 1
  and orange SLOT 2. Different or incorrect archived pairs must be explicit.
