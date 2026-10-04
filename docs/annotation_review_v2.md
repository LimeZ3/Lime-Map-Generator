# Annotation review version

Local implementation: `apps/crowd-labeler`. Do not deploy before the owner reviews it.

## Implemented

- Responsive map workspace using FAF vault previews exclusively, with an explicit unavailable state and zoom. Hydros, initial reclaim, dimensions, slots, mexes, water coverage, and buildable area use equal-size metric cells.
- 6,047 canonical non-Neroxis map records and extracted measurements. Stable extraction IDs replace array-position IDs for new responses.
- Provisional priority pool: 429 adaptive maps with technical audit `ready`. This is NOT an expert quality approval. Owner can replace this list with exact map folder names in Review setup.
- Profile: optional FAF name and rating, rating leaderboard, years of experience, multiple preferred modes. Each submission snapshots the profile; rating is unverified.
- Six calibration maps: Setons Clutch - FAF version v4; DualGap Adaptive v14; Adaptive Canis River v2; Adaptive Diversity v2; Adaptive Twin Rivers v2; Astro Crater Battles. Exact variants are editable.
- User-designated positive maps start with overall quality Good–Excellent, Astro with Very bad. No other trait answers are invented. Reference configuration and spawn/settings are unset pending expert review.
- The same fixed questionnaire is shown on every map: uniqueness (-1), optional unique traits (0), gameplay quality, visual appeal, land, air, navy, early/mid/late combat, eco safety, frontline openness, expansion, offensive drops, build space, terrain readability, gameplay readability, predefined roles, and biome (17). Ratings are 1–5, with 3 as average; all start at unknown. Unique traits support heuristic toggles and open text. Unknown-only submissions are allowed, including calibration. Submit is yellow for partial responses and green for all 17 numeric ratings plus a biome; optional text is excluded from completion.
- Suggestions are shown on request and never prefill answers. Their evidence and heuristic nature are visible. Whether suggestions were revealed is stored.
- Submissions retain configuration, settings, familiarity, profile snapshot, question values, notes, biome tags, time, phase, duration, and calibration revision.
- Local JSON export includes the entire profile, settings, raw submissions, and calibration status. CSV exports one row per answered question. New submissions use `scaleVersion: 5` and store literal 1–5 scores. Existing zero-based four-point submissions remain unchanged and are exported with their legacy scale identity; calibration comparison maps their old values to 1, 2, 4, 5. Stored reference bounds are migrated to that same scale. JSON includes current question definitions.

## Calibration checks

Do not equate descriptive intensity with quality. An unpleasant map can have high eco safety, high land relevance, and strong chokepoints.

Flag evaluation requires all six calibration maps to be submitted, each configured with a reference match setup and at least three acceptable answer ranges, and ten comparable answers in total. A review flag requires two or more maps with at least two out-of-range answers each and more than half of comparable answers outside the ranges. Unknowns are excluded and insufficient evidence is explicit. Flags do not delete or reject submissions. Thresholds are provisional and should be evaluated against real expert annotations.

Reference changes create a new revision; historical responses remain, but calibration is repeated against the current revision. Neither self-reported skill nor preferred mode proves reliability. Weighting should be calibrated using collected answers, and should differ for gameplay versus aesthetic labels.

## Review and release boundary

This is a functioning **local review application**, not a launched public survey. Browser storage is device-local and mutable. The owner screen is intentionally accessible for review; it is not an authenticated admin area. Reload retains submitted work, not an unsubmitted draft. Old prototype storage is not migrated or deleted.

Before public collection:

1. Confirm exact reference versions, match configurations, expert trait ranges, and the approved adaptive list.
2. Add authenticated server-side submissions, validation, participant IDs, owner access control, and durable shared storage. Keep reference answers and abuse evaluation on the server.
3. Add server-side duplicate/idempotency protection and assignment based on shared coverage; current scheduling only sees this browser's answers.
4. Review the rating/familiarity weighting policy and flag thresholds. Keep original answers and disagreement, rather than silently replacing them with weighted labels.
5. Bundle/host approved map previews for consistent availability. The interface now exclusively uses the FAF vault URL convention; it never substitutes embedded or structural previews.
6. Deploy only after user review and authorization.

The old Supabase schema and aggregation module are retained historical prototype files; they do not implement this new survey model and are not active in the review app.

## Validation

`npm test` covers catalog IDs and anchor resolution, six-map completion, pending references, unknowns, agreement/disagreement flags, priority overrides, skips, partial batches, zero/missing metric handling, and revision isolation.

Browser QA uses `?qa=1`, which isolates test submissions in a separate local-storage key. The normal URL is clean. Tested profile save, all six calibration submissions, reload persistence, a one-question partial review, suggestion reveal, collection search, real Astro vault previews, and desktop/mobile layouts. Production build succeeds.

## Testing-stage interface update

- Player settings include an EN/RU switch. Language changes apply immediately and persist on this device. Questions, explanations, answer labels, navigation, and hints are translated; stored answer keys and values remain language-independent. Browser checks confirmed reload persistence and preservation of in-progress ratings when switching languages.

- Familiarity defaults to Preview. Team configuration defaults to half the slots per team; odd counts use floor/ceil teams, and missing or invalid slot counts use Unknown / preview only. Configuration remains editable.
- Detailed and extreme-compact modes share identical questions and answers. Compact mode places each rating on one row, with numeric choices and named accessible labels/tooltips.
- Biome and extended-option disclosure state, hints visibility, and display mode persist across maps and browser reloads.
- Collection browsing uses 24 maps per page, previous/next controls and direct page selection. Search and pool changes reset pagination.
- UI checks covered yellow/green button states, full and unknown-only submissions, defaults resetting between maps while expanded panels persist, pagination, and vault images. Test-only submissions use the separate QA storage key and do not alter participant answers.
