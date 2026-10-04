# Crowd Labeling App Spec

## Purpose

Build a public questionnaire app that collects community judgments about FAF maps. The output should be a raw response dataset that can later be aggregated into soft labels for ML conditioning and dataset filtering.

The app is not trying to discover one final truth for each map. It should capture how different players perceive the same map, including disagreement.

## Core Principles

- Keep each session lightweight: show one map, ask 2-3 questions, submit, next map.
- Store every individual answer. Do not overwrite responses with averages.
- Treat labels as continuous or probabilistic, not hard categories.
- Ask about one concept at a time.
- Let respondents say they do not know.
- Separate gameplay, structure, quality, and aesthetics.
- Prefer repeated small judgments from many people over long expert-only forms.

## MVP User Flow

1. User opens the public page.
2. App assigns an anonymous browser ID.
3. Optional: user enters a FAF/player name.
4. App shows a map card.
5. App shows 2-3 questions selected from the question pool.
6. User answers and submits.
7. App stores raw answers.
8. App shows another map.

The page should make it easy to stop after one map. A good community tool feels like "I can do five quick ratings while waiting for a lobby."

## Map Card

The first version can show:

- map display name
- folder/version name
- map size
- player count
- available preview image, if any
- later: generated structural preview

The medium-term goal is to generate consistent previews from extracted data:

- height/water image
- spawn markers
- mex markers
- hydro markers
- reclaim density
- land/naval/amphibious path hints where available

Existing preview images should be treated as helpful UI, not training data ground truth.

## Question Types

Use compact scales. A 0-5 scale is easier than 1-10 and still expressive enough.

### Slider Questions

Question format:

- `0 = not at all`
- `5 = extremely`
- optional `I do not know`

Examples:

- How navy-heavy is this map?
- How land-focused is this map?
- How important is air control on this map?
- How turtle-friendly is this map?
- How raid-friendly is this map?
- How much does this map reward macro/eco scaling?
- How close-combat is this map?
- How beautiful is this map?
- How readable is this map during play?

### Multi-Choice Questions

Examples:

- Which modes matter on this map? `land`, `navy`, `air`, `amphibious`, `transport`, `eco`, `turtle`, `raid`
- What best describes the layout? `open`, `laned`, `chokepoint`, `island`, `ponds`, `water center`, `water sides`, `asymmetric`
- What is your familiarity with this map? `never played`, `seen it`, `played casually`, `know it well`
- Is this map generally good? `bad`, `mixed`, `good`, `excellent`, `do not know`

### Free Text

Keep free text optional and short:

- "Any short note about this map?"

Free text is useful for spotting missing categories, but it should not be required.

### Clone And Originality Questions

These questions should appear only occasionally, especially when a map is already in a name-similarity candidate family:

- Does this map feel like a clone, remake, or reskin of a better-known map?
- If yes, what map does it resemble?
- How original is this map?
- Is this the version of the map people should usually play?

Raw answers should be stored as review signals. They should not automatically delete maps from the dataset.

## Initial Question Pool

Gameplay:

- `navy_heavy`
- `land_focused`
- `air_important`
- `turtle_friendly`
- `raid_friendly`
- `macro_oriented`
- `close_combat`
- `team_role_dependent`

Structure:

- `open_layout`
- `laned_layout`
- `chokepoint_heavy`
- `island_or_water_split`
- `contested_middle`
- `safe_back_expansions`

Quality:

- `fun_to_play`
- `balanced`
- `competitive_quality`
- `readability`
- `originality`

Aesthetic:

- `beautiful`
- `natural_looking`
- `visually_noisy`

Respondent confidence:

- `familiarity`

## Response Data Model

Store responses as append-only rows.

### `maps`

```text
id
map_dir
canonical_name
version
size_x
size_z
player_count
inventory_source
preview_url
structural_preview_url
created_at
```

### `respondents`

```text
id
anonymous_key_hash
display_name
created_at
last_seen_at
```

Do not require login for MVP. If FAF OAuth or Discord login is added later, keep anonymous response support unless spam becomes unmanageable.

### `question_definitions`

```text
id
key
prompt
question_type
scale_min
scale_max
active
category
created_at
```

### `responses`

```text
id
map_id
respondent_id
question_id
numeric_value
choice_values
text_value
familiarity
client_session_id
created_at
```

### `aggregated_map_labels`

This table or view is generated from raw responses:

```text
map_id
question_key
response_count
mean
median
stddev
unknown_count
weighted_mean
updated_at
```

## Aggregation Rules

First pass:

- Average numeric responses per map/question.
- Track `response_count`, `mean`, `median`, and `stddev`.
- Keep `stddev` as signal. Disagreement is useful.
- Compute `weighted_mean` using familiarity:
  - `never played`: 0.5
  - `seen it`: 0.75
  - `played casually`: 1.0
  - `know it well`: 1.5

Later:

- Detect outliers.
- Compare casual vs experienced player labels.
- Avoid training splits where duplicate map families leak across train/test.

## Map Selection

The app should not always show the same popular maps.

MVP selection strategy:

- Prefer maps with fewer total responses.
- Prefer active questions with fewer answers for that map.
- Occasionally show known popular maps to calibrate users.
- Avoid repeating the same map to the same respondent too often.

## Abuse And Data Quality

MVP protections:

- Browser-local anonymous ID.
- One response per respondent/map/question unless explicitly updated.
- Basic rate limit by anonymous ID and IP if the backend supports it.
- Honeypot field on forms.
- Admin export includes timestamps for suspicious bursts.

Community quality controls:

- Optional FAF/player name.
- Optional "I know this map well" familiarity.
- Keep raw responses so bad batches can be removed later.

## Hosting Recommendation

MVP stack:

- Frontend: React, Vite, TypeScript
- Hosting: Vercel, Netlify, or Cloudflare Pages
- Backend/database: Supabase Postgres
- Storage: Supabase Storage for generated preview images

Why this stack:

- Quick public deployment.
- Simple database exports.
- No server maintenance.
- Good enough for friends and early community testers.

If the app later needs custom auth, moderation, or high traffic, it can move to a dedicated backend.

## Requirements

### Functional Requirements

- Import map records from the inventory/label CSV.
- Show one map at a time.
- Ask 2-3 questions per map.
- Support numeric scale questions.
- Support multi-choice questions.
- Support `I do not know`.
- Capture respondent familiarity.
- Store raw responses append-only.
- Export raw responses as CSV/JSON.
- Export aggregated labels as CSV/JSON.
- Allow an admin to activate/deactivate questions.
- Avoid repeatedly showing the same map/question pair to the same respondent.

### Non-Functional Requirements

- Public page loads quickly on desktop and mobile.
- No FAF installation required for respondents.
- No required login for MVP.
- Raw map files are never exposed publicly.
- Admin credentials and database keys are never committed.
- UI text is short and plain.
- The app remains useful even when only a preview image is available.

### Out Of Scope For MVP

- Training models inside the web app.
- Uploading arbitrary maps from users.
- Full FAF account integration.
- Perfect anti-spam.
- Rich discussion threads.
- Real-time leaderboards.

## First Build Milestones

1. Create an app folder with a local mock dataset.
2. Build a single-map rating screen.
3. Store responses locally or in a simple JSON mock.
4. Add Supabase schema and real inserts.
5. Add admin export.
6. Generate consistent structural previews from map data.
7. Invite friends to test the first 279-map dataset.
