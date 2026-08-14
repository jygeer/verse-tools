# AGENTS.md

Instructions for AI coding agents (Claude Code, Codex, Cursor, etc.) working
in this repository. Human contributors may find it useful too, but it's
written for an agent picking up the repo cold.

## What this project is

`versetools` is a from-scratch lexer, parser, bytecode compiler, VM, and
REPL for **Verse-core**, a documented practical subset of Epic's Verse
language, implemented entirely in Python with no dependency on UEFN,
Fortnite, or any Epic service. See `README.md` for the pitch and
`docs/architecture.md` for how the pieces fit together.

Read before assuming anything about scope or behavior:

- `docs/differences-from-verse.md` - every place this diverges from real
  Verse, and why. Don't "fix" a documented, deliberate divergence without
  updating this doc in the same change.
- `docs/roadmap.md` - ground rules (no Epic source/spec access, never
  depend on UEFN/Fortnite, backward compatibility within Verse-core) and
  the planned direction. GitHub issues for roadmap items are tagged with
  the `roadmap` label and a `[phase.item]` ID prefix, e.g. `[1.1]`.

## Setup

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
```

## Build and test

```sh
pytest                # full test suite
pytest -k <name>       # a single test
verse run <file.verse>  # run a program
verse tokens/ast/dis <file.verse>  # lexer/parser/compiler debugging aids
```

CI (`.github/workflows/ci.yml`) runs `pytest` across Python 3.10-3.13 and
verifies the package builds (`python -m build`) on every push/PR to `main`.
Treat a local `pytest` failure or an unbuildable package as a hard blocker,
never something to route around.

**Any feature or bug-fix change in `src/versetools/` must follow the
`feature-dev` skill workflow** (`.claude/skills/feature-dev/SKILL.md`):
write a failing test first, implement the smallest correct change, run the
full test suite plus the `examples/` corpus (not just the new test), and
update `docs/differences-from-verse.md`/`docs/roadmap.md`/
`docs/language-reference.md` in the same change if the behavior or scope
they describe changed. Silent behavior drift is the one failure mode this
project's ground rules explicitly call unacceptable - an interpreter with
an out-of-date spec is worse than no spec.

## Project layout

```
src/versetools/
    tokens.py       token types
    lexer.py        source -> token stream (indentation-sensitive)
    ast_nodes.py    AST node dataclasses
    parser.py       token stream -> AST (recursive descent)
    bytecode.py     opcode set, Chunk/FunctionProto/ClassSpec containers
    compiler.py     AST -> bytecode
    values.py       runtime value types + the name-based Environment
    vm.py           the stack-based bytecode VM and task scheduler
    stdlib.py       built-in functions (Print, Length, Sqrt, ...)
    repl.py         interactive REPL
    cli.py          `verse` command-line entry point
    disasm.py       bytecode disassembler (used by `verse dis`)
examples/           runnable .verse example programs - also the closest
                    thing this project has to a conformance corpus
tests/              pytest suite (lexer, parser, VM, examples)
docs/               architecture, language reference, roadmap, differences
.claude/skills/     Claude Code skills for this repo (see below)
```

## Available Claude Code skills

- `feature-dev` - the required workflow for implementing or fixing
  anything in `src/versetools/` (see above).
- `sync-roadmap-issues` - creates/refreshes GitHub issues from
  `docs/roadmap.md`, idempotently (matches on the issue title's `[ID]`
  prefix). Run this after editing the roadmap, not manually via `gh issue
  create`, so IDs and labels stay consistent.
- `review-agent-pr` - vets a PR opened by an autonomous coding agent
  (GitHub Copilot coding agent or another Claude session) against the
  same rigor `feature-dev` requires, before it's merged.

## Working with GitHub Copilot coding agent

This repo also uses GitHub Copilot's coding agent to work roadmap issues
directly (it opens PRs from `copilot/*` branches, authored by
`app/copilot-swe-agent`). It reads `AGENTS.md` and
`.github/copilot-instructions.md` (the same rigor as `feature-dev`,
condensed) automatically, and `.github/workflows/copilot-setup-steps.yml`
pre-installs `pip install -e ".[dev]"` into its environment. Before
merging a Copilot-authored PR, run the `review-agent-pr` skill on it - an
agent PR existing and passing CI isn't the same as it having met the
test/docs bar this repo expects.

## Conventions worth knowing

- No runtime dependencies (`dependencies = []` in `pyproject.toml`); keep
  it that way unless there's a strong reason - `pytest` is the only dev
  dependency.
- Every observable language behavior should be backed by a test, ideally a
  `.verse` example plus expected output, not just an internal unit test -
  see "Risks and open questions" in `docs/roadmap.md` on why the test
  suite is treated as the executable spec here.
- A new language feature (new syntax, stdlib function, or semantics) needs
  a runnable example, not just a test: add a `.verse` file to `examples/`
  (or extend the closest topical one, e.g. `control_flow.verse`,
  `arrays_and_maps.verse`) that demonstrates it, since `examples/` is the
  corpus every change is checked against and doubles as user-facing
  documentation of what's supported.
- Don't add UEFN/Fortnite/Epic-service integration of any kind - it's an
  explicit non-goal, not just unimplemented (`docs/roadmap.md`'s ground
  rules).
- Keep "unofficial" and "Verse-core" framing intact in docs/messaging;
  this project isn't Epic software and shouldn't read like it is.
