---
name: feature-dev
description: >-
  Rigorous build-and-test workflow for implementing a feature or fixing a bug
  in versetools. Use whenever asked to implement, add, or fix something in
  src/versetools (not for docs-only or CI-config-only changes).
---
# Feature development workflow

`versetools` is a lexer/parser/compiler/VM - a correctness-first project
where a silent behavior change is worse than a loud failure. Every feature
or fix goes through the same rigor, no shortcuts, regardless of how small it
looks.

## 1. Locate before changing

Read `docs/architecture.md` for the stage the change touches (lexer, parser,
compiler, VM, stdlib) and `docs/differences-from-verse.md` to check whether
the behavior in question is a documented, deliberate divergence from real
Verse - if it is, changing it is a docs update, not just a code change (see
step 5). If the work item traces back to `docs/roadmap.md`, re-read that
item's Goal/Approach/Effort before starting; don't improvise a different
approach without noting why.

## 2. Write the failing test first

Every behavior change needs a test in `tests/` that fails before the change
and passes after. This project's test suite is the executable spec - there
is no other conformance authority (see roadmap's "Risks and open
questions"). Prefer a `.verse` example program plus expected output/error
over a purely internal unit test when the change is observable at the
language level; that's what keeps the conformance corpus (Phase 4 of the
roadmap) meaningful.

Run it and confirm it fails for the reason you expect, not for an unrelated
reason:

```sh
pytest -k <new_test_name> -q
```

## 3. Implement the smallest correct change

Follow this repo's existing patterns (see `README.md`'s project layout and
`docs/architecture.md`) rather than introducing a new one. Don't fix
adjacent things you notice along the way - note them (or file a roadmap/
issue item) instead of scope-creeping the change.

## 4. Full local build-and-test pass before calling anything done

Run the whole suite, not just the new test - regressions in unrelated
lexer/parser/VM behavior are easy to introduce silently in this kind of
codebase:

```sh
pip install -e ".[dev]"
pytest
```

Then exercise the CLI paths a unit test won't catch, especially for
lexer/parser/compiler changes - `verse tokens`, `verse ast`, `verse dis` are
the debugging aids for exactly this:

```sh
verse run examples/hello.verse
verse tokens examples/<closest-example>.verse
verse ast examples/<closest-example>.verse
verse dis examples/<closest-example>.verse
```

If the change is in `stdlib.py`, `vm.py`, or `compiler.py`, run the full
`examples/` corpus, not just one file - it's small enough to be cheap and
those examples exist specifically to catch cross-cutting breakage:

```sh
for f in examples/*.verse; do echo "== $f =="; verse run "$f" || echo "FAILED: $f"; done
```

A change is not done until `pytest` is fully green and every example still
runs (or, if intentionally changing observable behavior, the affected
example's expected output/docs are updated to match - never left silently
stale).

## 5. Update docs in the same change

- If the change closes or narrows a gap listed in
  `docs/differences-from-verse.md`, update that entry (or remove it) in the
  same change - a stale differences doc is actively misleading.
- If the change corresponds to a `docs/roadmap.md` item, note in the PR/
  commit which item it addresses; if it only partially completes the item,
  say what's left rather than leaving the roadmap entry looking done or
  stale. If a GitHub issue tracks it (see the `sync-roadmap-issues` skill),
  reference/close that issue rather than leaving it orphaned.
- New stdlib functions, CLI flags, or language features need a mention in
  `README.md` and/or `docs/language-reference.md`.
- New syntax, stdlib functions, or language semantics also need a runnable
  example: add a `.verse` file to `examples/` (or extend the closest
  topical one, e.g. `control_flow.verse`, `arrays_and_maps.verse`) so the
  feature is exercised by the conformance corpus, not just a unit test.

## 6. Before considering the feature shippable

- `pytest` passes fully (step 4).
- The CI workflow (`.github/workflows/ci.yml`) would pass - it's the same
  `pip install -e ".[dev]" && pytest` plus a package-build check across
  Python 3.10-3.13, so if it's green locally on your Python version, spot-
  check that nothing added is version-specific.
- No example in `examples/` regressed.
- Docs affected by step 5 are updated, not just code.
- The diff is the smallest change that correctly implements the feature -
  no unrelated cleanup bundled in (split it out if it's worth doing).

Skipping any of these to "save time" is exactly how silent behavior drift
happens in an interpreter project - which is the one failure mode this
project's ground rules (`docs/roadmap.md`) explicitly call out as
unacceptable.
