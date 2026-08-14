#!/usr/bin/env python3
"""Parse docs/roadmap.md and ensure a GitHub issue exists for each item.

Idempotent: every issue title is prefixed with a stable ID (e.g. "[1.1]"),
and existing open/closed issues are matched by that prefix before creating
a new one, so re-running this after editing the roadmap only creates issues
for items that are new.

Usage:
    python3 sync_roadmap_issues.py            # dry run, prints the plan
    python3 sync_roadmap_issues.py --apply    # actually create issues/labels
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]  # .claude/skills/sync-roadmap-issues/scripts -> repo root
ROADMAP = REPO_ROOT / "docs" / "roadmap.md"

EFFORT_LABELS = {"S": "effort-s", "M": "effort-m", "L": "effort-l", "XL": "effort-xl"}


@dataclass
class Item:
    id: str
    title: str
    phase: str
    effort: str | None
    anchor: str
    body: str
    labels: list[str] = field(default_factory=list)

    @property
    def issue_title(self) -> str:
        return f"[{self.id}] {self.title}"


def slugify(header: str) -> str:
    # Approximates GitHub's header-to-anchor algorithm closely enough to link
    # readers back to the right spot in docs/roadmap.md.
    s = header.strip().lower()
    s = re.sub(r"[^a-z0-9 \-_]", "", s)
    s = s.replace(" ", "-")
    return s


def extract_effort(text: str) -> str | None:
    m = re.search(r"\*\*Effort:?\*\*\s*([A-Z]{1,2})", text)
    if m:
        return m.group(1)
    m = re.search(r"Effort:\s*([A-Z]{1,2})\b", text)
    return m.group(1) if m else None


def parse_phase1(lines: list[str]) -> list[Item]:
    items = []
    start = next(i for i, l in enumerate(lines) if l.startswith("## Phase 1"))
    end = next(i for i, l in enumerate(lines) if l.startswith("## Phase 2"))
    section = lines[start:end]
    header_re = re.compile(r"^### (\d\.\d+) (.+)$")
    idxs = [i for i, l in enumerate(section) if header_re.match(l)]
    for n, i in enumerate(idxs):
        m = header_re.match(section[i])
        item_id, title = m.group(1), m.group(2).strip()
        body_end = idxs[n + 1] if n + 1 < len(idxs) else len(section)
        body = "\n".join(section[i + 1 : body_end]).strip()
        items.append(
            Item(
                id=item_id,
                title=title,
                phase="phase-1",
                effort=extract_effort(body),
                anchor=slugify(f"{item_id} {title}"),
                body=body,
            )
        )
    return items


def parse_phase2a(lines: list[str]) -> list[Item]:
    items = []
    start = next(i for i, l in enumerate(lines) if l.startswith("### 2a."))
    end = next(i for i, l in enumerate(lines) if l.startswith("### 2b."))
    row_re = re.compile(r"^\|\s*(2a\.\d+)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(\S+)\s*\|\s*$")
    for l in lines[start:end]:
        m = row_re.match(l)
        if not m:
            continue
        item_id, change, why, effort = m.groups()
        items.append(
            Item(
                id=item_id,
                title=change.strip("`"),
                phase="phase-2",
                effort=effort,
                anchor="2a-incremental-stay-in-python-wins",
                body=f"**Change:** {change}\n\n**Why it helps:** {why}",
            )
        )
    return items


def parse_phase2b(lines: list[str]) -> list[Item]:
    start = next(i for i, l in enumerate(lines) if l.startswith("### 2b."))
    end = next(i for i, l in enumerate(lines) if l.startswith("## Phase 3"))
    section = lines[start:end]
    title = section[0].split(". ", 1)[1].strip() if ". " in section[0] else section[0][4:].strip()
    body = "\n".join(section[1:]).strip()
    return [
        Item(
            id="2b",
            title=title,
            phase="phase-2",
            effort=extract_effort(body),
            anchor=slugify("2b. " + title),
            body=body,
        )
    ]


def parse_phase3(lines: list[str]) -> list[Item]:
    items = []
    start = next(i for i, l in enumerate(lines) if l.startswith("## Phase 3"))
    end = next(i for i, l in enumerate(lines) if l.startswith("## Phase 4"))
    row_re = re.compile(
        r"^\|\s*\*\*([A-C])\.\s*(.+?)\*\*(.*?)\|\s*(.+?)\s*\|\s*(\S.*?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*$"
    )
    for l in lines[start:end]:
        m = row_re.match(l)
        if not m:
            continue
        letter, title, title_suffix, what, effort, speed, notes = m.groups()
        if title_suffix.strip():
            title = f"{title} {title_suffix.strip()}"
        items.append(
            Item(
                id=f"3.{letter}",
                title=title,
                phase="phase-3",
                effort=effort,
                anchor="phase-3---webassembly-target",
                body=f"**What it is:** {what}\n\n**Runtime speed:** {speed}\n\n**Notes:** {notes}",
            )
        )
    return items


def parse_phase4(lines: list[str]) -> list[Item]:
    items = []
    start = next(i for i, l in enumerate(lines) if l.startswith("## Phase 4"))
    end = next(i for i, l in enumerate(lines) if l.startswith("## Sequencing"))
    section = lines[start:end]
    bullet_re = re.compile(r"^- \*\*(.+?)\*\*:?\s*(.*)$")
    idxs = [i for i, l in enumerate(section) if bullet_re.match(l)]
    for n, i in enumerate(idxs):
        m = bullet_re.match(section[i])
        raw_title, rest = m.groups()
        title = raw_title.rstrip(":").strip()
        body_end = idxs[n + 1] if n + 1 < len(idxs) else len(section)
        body = (rest + "\n" + "\n".join(section[i + 1 : body_end])).strip()
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        items.append(
            Item(
                id=f"4.{slug}",
                title=title,
                phase="phase-4",
                effort=extract_effort(body),
                anchor="phase-4---tooling-and-ecosystem",
                body=body,
            )
        )
    return items


def parse_roadmap() -> list[Item]:
    lines = ROADMAP.read_text().splitlines()
    items = (
        parse_phase1(lines)
        + parse_phase2a(lines)
        + parse_phase2b(lines)
        + parse_phase3(lines)
        + parse_phase4(lines)
    )
    for it in items:
        it.labels = ["roadmap", it.phase]
        if it.effort in EFFORT_LABELS:
            it.labels.append(EFFORT_LABELS[it.effort])
    return items


def gh(*args: str) -> str:
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def ensure_labels(items: list[Item], apply: bool) -> None:
    wanted = {}
    for it in items:
        for label in it.labels:
            wanted.setdefault(label, "roadmap" if label == "roadmap" else "roadmap sub-area")
    colors = {
        "roadmap": "6f42c1",
        "phase-1": "0e8a16",
        "phase-2": "1d76db",
        "phase-3": "fbca04",
        "phase-4": "d93f0b",
        "effort-s": "c2e0c6",
        "effort-m": "bfd4f2",
        "effort-l": "f9d0c4",
        "effort-xl": "e99695",
    }
    for label in wanted:
        color = colors.get(label, "ededed")
        if apply:
            subprocess.run(
                ["gh", "label", "create", label, "--color", color, "--force"],
                check=True,
                capture_output=True,
                text=True,
            )
        print(f"{'[apply]' if apply else '[dry-run]'} ensure label: {label}")


def repo_slug() -> str:
    out = gh("repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner")
    return out.strip()


def existing_issue_ids() -> set[str]:
    out = gh("issue", "list", "--state", "all", "--limit", "500", "--json", "title")
    ids = set()
    for row in json.loads(out):
        m = re.match(r"^\[([^\]]+)\]", row["title"])
        if m:
            ids.add(m.group(1))
    return ids


def build_body(it: Item, repo: str) -> str:
    link = f"https://github.com/{repo}/blob/main/docs/roadmap.md#{it.anchor}"
    effort_line = f"**Effort:** {it.effort}\n\n" if it.effort else ""
    return (
        f"Synced from the roadmap: [{link}]({link})\n\n"
        f"{effort_line}"
        f"{it.body}\n\n"
        f"---\n"
        f"_This issue is auto-generated from `docs/roadmap.md` by the "
        f"`sync-roadmap-issues` skill. Edit the roadmap and re-run the skill "
        f"to keep issues in sync; avoid hand-editing the title's `[{it.id}]` prefix, "
        f"it's used to detect this issue on re-sync._"
    )


def main() -> None:
    apply = "--apply" in sys.argv
    items = parse_roadmap()
    print(f"Parsed {len(items)} roadmap items from {ROADMAP.relative_to(REPO_ROOT)}\n")

    ensure_labels(items, apply)
    print()

    try:
        existing = existing_issue_ids()
        repo = repo_slug()
    except subprocess.CalledProcessError as e:
        print(f"warning: could not query GitHub ({e}); assuming no existing issues", file=sys.stderr)
        existing, repo = set(), "OWNER/REPO"

    created, skipped = 0, 0
    for it in items:
        if it.id in existing:
            skipped += 1
            print(f"[skip] [{it.id}] {it.title} (issue already exists)")
            continue
        if apply:
            body = build_body(it, repo)
            out = subprocess.run(
                [
                    "gh", "issue", "create",
                    "--title", it.issue_title,
                    "--body", body,
                    "--label", ",".join(it.labels),
                ],
                check=True, capture_output=True, text=True,
            )
            print(f"[created] {it.issue_title} -> {out.stdout.strip()}")
        else:
            print(f"[dry-run] would create: {it.issue_title}  (labels: {', '.join(it.labels)})")
        created += 1

    print(f"\n{'Created' if apply else 'Would create'} {created}, skipped {skipped} (already exist).")
    if not apply:
        print("Re-run with --apply to actually create issues and labels.")


if __name__ == "__main__":
    main()
