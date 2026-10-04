# MapGen Community Atlas

FAF map annotation app with a local review mode and a hosted collection mode.

## Hosted collection

`npm run build` produces the public survey and a Cloudflare-compatible Worker. Sites supplies the `DB` binding and applies the checked-in Drizzle migrations. The public survey has no owner setup controls. Reviews and profile snapshots are stored centrally; each browser gets a secure, HTTP-only anonymous session cookie. There is no password or cross-device account recovery in this first release. Clearing cookies starts a new participant, but already submitted reviews remain in the database.

Server saves validate map versions and five-point answers, enforce calibration completion, and deduplicate retries by review ID. Failures keep the current answers on screen. Session endpoints only return the current participant's data. Participant cookies and token hashes are excluded from all dashboard exports.

### Owner dashboard and local backups

Open `/owner` and sign in with the ChatGPT account that owns the site. Sites supplies the authenticated identity; every `/api/owner/*` request checks the server-side owner allowlist. The deployment uses `OWNER_EMAIL` from the verified Sites owner record, with a non-empty authenticated user ID required as well. `OWNER_USER_ID`, when configured, takes precedence and pins access to a site-scoped authenticated ID (not the workspace account ID). Missing configuration denies access. Both settings belong in hosted environment variables, never browser code. Recheck the allowlist if site ownership changes. Do not expose this Worker behind a proxy that lets visitors forge Sites identity headers.

- **Refresh data** loads all reviews and current participant profiles in bounded pages. Partial or failed loads cannot be exported.
- **Full dataset · JSON** downloads reviews, profiles, question definitions, the rubric and export metadata. This is the complete local backup format. Review rows have an append-only snapshot watermark; current profiles are read during the export and may reflect later profile edits.
- **All reviews · CSV** downloads one row per review, with all question scores, profile snapshots, familiarity, configuration, biome, traits and notes. CSV preserves original scale values and neutralizes spreadsheet formulas; JSON preserves unmodified text.
- Both downloads include the entire loaded dataset regardless of dashboard filters. Filenames include the snapshot timestamp. Refresh before each periodic backup.
- Map summaries display unweighted averages excluding unknowns, answer counts and rating spread. Individual reviews expose player experience and configuration so disagreement can be interpreted in context. There is no automatic expert weighting or respondent exclusion.

The public survey stays accessible without sign-in. Only the owner dashboard and dataset endpoints require owner authorization. Signed-in non-owners are denied, and unauthenticated visitors see a sign-in link. The authenticated Sites database viewer remains an alternative way to inspect stored rows.

`npm run test:server` checks the API against actual SQLite migrations, including authorization, validation, session isolation, duplicate retries, and restored responses. It uses an in-memory test database, never production data.

The six-map calibration set and provisional adaptive pool are fixed by the server's `public-v1` rubric. Expert reference scoring remains pending until the reference ranges are reviewed; no automatic respondent bans are applied. The local review controls remain available through `npm run dev` for preparing future rubric revisions.

## Run

```powershell
cd apps/crowd-labeler
npm.cmd install
npm.cmd run dev
```

Open http://127.0.0.1:5174/. `npm.cmd run build` checks TypeScript and produces the production bundle; `npm.cmd test` checks survey logic (Node with TypeScript stripping support required).

## Review workflow

1. Add your player profile.
2. Annotate the six calibration maps, including Astro Crater Battles.
3. Contribute partial reviews to the adaptive collection, then explore the full catalog.
4. Use **Review setup** to set expert reference ranges, exact map versions/configurations, and the priority list.
5. Export raw JSON or CSV. In local development, responses are saved only in this browser. The hosted build confirms saves with the central server.

The catalog contains 6,047 canonical maps and 429 provisional adaptive candidates. Technical audit readiness does not establish gameplay quality. `scripts/build-review-data.py` regenerates the catalog and accessible embedded map previews from repository extraction files (requires Python/Pillow and the source inventory). The checked-in generated catalog can be built without the raw maps. The former `generate:data` script builds the older prototype catalog and is not used by the current interface.

See `../../docs/annotation_review_v2.md` for the original local review design. The hosted behavior above supersedes its browser-only storage notes.
