# Atlas publication and maintenance

The atlas under `docs/model-atlas` is the project's main source of truth. The
public address is https://mapgen-project-atlas.elven-bowl-7506.chatgpt.site .
ChatGPT Sites hosts the portal; the `codex/atlas-live` branch of the project GitHub
repository holds immutable, sanitized public snapshots and `latest.json`.
The portal checks that pointer every 60 seconds while open, on returning to the
tab, or when Check updates is pressed. It has a bundled initial fallback. It
never reads uncommitted desktop files or infers progress from a running process.

## Record and publish meaningful progress

1. Update the atlas catalog/control registry, method/work notes and
   `docs/map-extraction-todos.md` as appropriate. Preserve exact checkpoint and
   map identities; record completed, active, experimental and planned separately.
2. Refresh the offline model reference using project GPU Python, metadata only:
   `$env:PYTHONPATH='src'; .venv/Scripts/python.exe -m supmapai.tools.build_model_atlas`.
3. Run `node tools/refresh_project_status.mjs` to refresh the structured progress
   page and dated GitHub report from atlas receipts and saved supervisor states.
   Check wording before publication, especially a running/paused/completed state.
4. Run `node tools/publish_project_atlas.mjs --push`. This builds a public snapshot
   and pushes only the dedicated `codex/atlas-live` publication branch. It does not
   stage or commit the research checkout or modify `main`. Git write access is
   required; failures must not be reported as published. Verify the remote pointer
   after a push. No Site deployment is needed for a data/content update.
5. Commit reviewed source documentation/progress changes to the research branch
   through the normal GitHub workflow. Keep a dated report as history; the current
   atlas status is authoritative. Update the local offline reference too.

A content publisher must run after meaningful recorded progress. The minute
browser check does **not** itself turn local edits into public updates. This
workflow is agent-driven/event-driven publication, not an unattended training
monitor, and creates no recurring tasks or Netlify deployment.

## Public packaging boundaries

The publisher includes reviewed atlas images/scripts, rendered project notes and
selected small source/evidence snapshots. It scrubs machine-specific absolute
paths. It excludes checkpoints, full raw tensor archives, private response exports,
portfolio drafts and local review applications; links become explanatory evidence
pages rather than broken file URLs. It must never upload credentials or expand
an excluded artifact merely because a document links to it.

A public snapshot has a content digest, immutable release directory, recorded
source timestamp and per-file hashes. The version pointer advances only after
its snapshot is uploaded in the same Git push. GitHub retains prior versions.
The Site portal embeds only this fixed project's owner-published source; it does
not allow arbitrary remote document origins.

## Portal/code updates

Site identity is in `sites/mapgen-project-atlas/.openai/hosting.json`. Reuse it.
Use the Sites skill's source helper and native save/deploy workflow for changes
to the portal itself, preserving public access. Do not deploy to Netlify. Source
credentials belong only in session memory/stdin. The initial bundled fallback is
packaged under `sites/mapgen-project-atlas/dist`; newer content comes from GitHub.

The Markdown renderer uses the bundled `marked` dependency. Set
`ATLAS_MARKED_MODULE` to its absolute module path when a runtime bundle moves.
