---
name: review-agent-pr
description: >-
  Review a GitHub PR authored by an autonomous coding agent (Copilot
  coding agent, another Claude session, etc.) against this repo's
  build-and-test rigor before it's merged. Use when asked to review,
  check, or vet a PR - especially one opened by app/copilot-swe-agent or
  titled starting with "[WIP]".
---
# Reviewing an agent-authored PR

This repo has more than one autonomous agent opening PRs against it
(GitHub Copilot coding agent works roadmap issues directly; Claude Code
sessions do too). Both are expected to follow the same bar as a human
contributor would: the `feature-dev` skill's workflow
(`.claude/skills/feature-dev/SKILL.md`). Agent-authored PRs need a human
(or a Claude session acting as reviewer) to actually verify that bar was
met, not just assume it because the PR exists - an agent can produce a
plausible-looking diff that skips a step.

## What to check, in order

1. **What issue/roadmap item does this close?** Read the linked issue (PRs
   from `sync-roadmap-issues` are titled `[phase.item] ...`, e.g. `[1.2]`).
   Re-read that item's Goal/Approach/Effort in `docs/roadmap.md` and
   confirm the PR actually addresses the Goal, not just something
   adjacent to it.

2. **Is there a test that would have failed before this change?**
   `git diff <base>...<head> -- tests/` - a behavior change with no test
   diff is a red flag. Prefer a `.verse` example plus expected output for
   observable language behavior; check it actually exercises the new
   behavior rather than merely not-crashing.

3. **Does the full suite pass, not just new tests?** Check out the PR
   branch and run it yourself rather than trusting a green CI checkmark
   alone (CI here does the same `pytest`, but confirm it actually ran, not
   skipped):

   ```sh
   gh pr checkout <number>
   pip install -e ".[dev]"
   pytest
   for f in examples/*.verse; do verse run "$f" || echo "FAILED: $f"; done
   ```

4. **Were docs updated where the change requires it?**
   - `docs/differences-from-verse.md` - if a listed gap was closed or
     narrowed, its entry should be updated or removed in this PR.
   - `docs/language-reference.md`/`README.md` - if a stdlib function, CLI
     flag, or language feature was added.
   - A PR that changes observable behavior with zero docs diff is worth
     a comment even if tests pass, since a stale differences doc actively
     misleads the next contributor (agent or human).

5. **Is the diff scoped to the issue?** Flag unrelated refactors or
   cleanup bundled into the same PR - ask for them to be split out rather
   than approving scope creep, same standard as `feature-dev` step 3.

6. **Ground-rule check.** Skim for anything that would violate
   `docs/roadmap.md`'s ground rules: new runtime dependencies without
   justification (`pyproject.toml`'s `dependencies` should stay empty
   unless there's a strong reason), any UEFN/Fortnite/Epic-service
   integration (permanent non-goal), or "unofficial"/"Verse-core" framing
   getting dropped from docs/messaging.

## Reporting

Summarize per the numbered checks above - which passed, which didn't, and
for failures, exactly what's missing (not just "needs work"). If everything
checks out, say so plainly rather than manufacturing findings; an agent PR
that actually followed the rigor doesn't need artificial pushback.

If asked to also fix what's missing rather than just report it, treat that
as a `feature-dev`-governed change on top of the existing PR (same
required rigor - add the missing test/docs, rerun the full suite) rather
than merging with known gaps.
