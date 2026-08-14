---
name: sync-roadmap-issues
description: >-
  Create/update GitHub issues from docs/roadmap.md. Use when the user asks to
  sync, refresh, or turn the roadmap into GitHub issues, or after roadmap.md
  has been edited and issues should reflect it.
---
# Sync roadmap to GitHub issues

`docs/roadmap.md` is the source of truth for planned work. Every numbered/
lettered item in it (Phase 1's `1.1`-`1.9`, Phase 2a's `2a.1`-`2a.5`, `2b`,
Phase 3's `3.A`-`3.C`, and Phase 4's bullet items) should have a matching
GitHub issue so it's trackable, assignable, and closeable independently of
the doc.

A parser + sync script already does the mechanical work:
`.claude/skills/sync-roadmap-issues/scripts/sync_roadmap_issues.py`.

## How it stays idempotent

Every issue title is prefixed with a stable ID, e.g. `[1.1] Block scoping`.
On each run the script lists all existing issues (open + closed) via
`gh issue list --state all`, extracts the `[ID]` prefix from each title, and
only creates issues for IDs it hasn't seen. **Never hand-edit or remove an
issue's `[ID]` prefix** - that's the only thing preventing duplicate issues
on the next sync.

## Running it

1. Dry run first, always - it prints exactly what would be created without
   touching GitHub:

   ```sh
   python3 .claude/skills/sync-roadmap-issues/scripts/sync_roadmap_issues.py
   ```

2. Read the dry-run output. Check the parsed item count and titles look
   sane against the current `docs/roadmap.md` - if the roadmap's structure
   changed (new phase, renamed headers, a table's column order changed),
   the parser's regexes in `scripts/sync_roadmap_issues.py` may need
   updating first (see "If the roadmap format changes" below).

3. Creating issues on a real repo is visible to everyone with access to
   it - confirm with the user before applying, unless they already asked
   for this run explicitly. Then:

   ```sh
   python3 .claude/skills/sync-roadmap-issues/scripts/sync_roadmap_issues.py --apply
   ```

   This also creates/updates (`--force`) the labels it uses: `roadmap`,
   `phase-1`..`phase-4`, and `effort-s`/`effort-m`/`effort-l`/`effort-xl`.

Each created issue's body links back to the exact `docs/roadmap.md#<anchor>`
section on GitHub, includes the Goal/Approach/Effort text from the roadmap,
and is labeled with its phase and effort size.

## If the roadmap format changes

The script has one parse function per roadmap section
(`parse_phase1`, `parse_phase2a`, `parse_phase2b`, `parse_phase3`,
`parse_phase4`) because each section is formatted differently (numbered
headers vs. markdown tables vs. bullet lists). If someone restructures a
section of `docs/roadmap.md`, update the matching parse function rather than
trying to write one generic parser - the sections are genuinely
heterogeneous. After any change, re-run the dry run and sanity-check the
item count and titles before applying.

## Adding a new roadmap item later

New items just need to follow the existing formatting convention for their
section (e.g. `### 1.10 Title` under Phase 1, or a new table row under
Phase 2a/3). The next dry run will pick it up automatically as a new ID and
propose creating exactly one new issue for it - existing items are
untouched.
