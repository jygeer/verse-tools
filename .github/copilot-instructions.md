# Copilot instructions for versetools

`versetools` is a from-scratch Python lexer/parser/bytecode-compiler/VM/REPL
for **Verse-core**, a documented practical subset of Epic's Verse language.
It is unofficial and has no dependency on UEFN, Fortnite, or any Epic
service - never add integration with any of those, that's a permanent
non-goal, not just unimplemented. Keep the "unofficial"/"Verse-core"
framing intact in anything you write.

Full context lives in `AGENTS.md` (read it first) and
`.claude/skills/feature-dev/SKILL.md`; this file is the short version.

## Before changing anything

- Read `docs/architecture.md` for the stage you're touching
  (lexer/parser/compiler/VM/stdlib).
- Check `docs/differences-from-verse.md` - if your change closes or
  narrows a listed gap, update that doc entry in the same PR. If it's a
  deliberate divergence, don't "fix" it without updating the doc.
- If the work traces to a `docs/roadmap.md` item (issue titles here are
  prefixed `[phase.item]`, e.g. `[1.1]`), follow that item's
  Goal/Approach/Effort; call out in the PR description if you diverge from
  the suggested approach and why.

## Build and test

```sh
pip install -e ".[dev]"
pytest
```

- Add a failing test in `tests/` before implementing. Prefer a `.verse`
  example program plus expected output/error over a purely internal unit
  test for anything observable at the language level - this project's test
  suite is its executable spec, there's no other conformance authority.
- Run the **full** `pytest` suite before opening the PR, not just the new
  test - regressions in unrelated lexer/parser/VM behavior are easy to
  introduce silently here.
- Run every file in `examples/` and confirm none regress:
  `for f in examples/*.verse; do verse run "$f" || echo "FAILED: $f"; done`
- Update `docs/language-reference.md`/`README.md` for any new stdlib
  function, CLI flag, or language feature.
- Add a `.verse` example to `examples/` for any new syntax, stdlib
  function, or language feature (or extend the closest topical file, e.g.
  `control_flow.verse`) - the corpus is run on every change and is
  user-facing documentation of what's supported.

## Scope

- Implement the smallest correct change for the issue. Don't bundle
  unrelated cleanup or refactors into the same PR.
- No new runtime dependencies (`dependencies = []` in `pyproject.toml`)
  without strong justification - `pytest` is the only dev dependency today.
- A PR is not ready for review until `pytest` is fully green locally and
  the `examples/` corpus still runs clean.
