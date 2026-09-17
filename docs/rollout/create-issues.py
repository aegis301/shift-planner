#!/usr/bin/env python3
"""Create the rollout issues in GitHub from the markdown files in docs/rollout/issues/.

Usage:
    python3 docs/rollout/create-issues.py --dry-run
    python3 docs/rollout/create-issues.py

Requires an authenticated `gh` CLI with write access to the repository.

Issue bodies reference each other by file number (`#04`). Those are placeholders: the
script creates the issues first, then rewrites the references to the real issue numbers
in a second pass.

Already-created issues are tracked in `created-issues.json` and are skipped, so the script
is safe to re-run after adding new issue files. Use `--only 24,25` to restrict it to
specific file prefixes. To deliberately recreate one, delete its entry from that file.

If a run aborts between creation and the rewrite pass, the map is not written — check
`gh issue list` before re-running so you do not create duplicates.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ISSUE_DIR = Path(__file__).resolve().parent / "issues"

LABEL_COLORS = {
    "rollout-r0": ("6e7781", "Gate before the compliance rollout"),
    "rollout-r1": ("0e8a16", "R1 - time axis, statutory rules, duty activity"),
    "rollout-r2": ("1d76db", "R2 - rolling fairness accounts"),
    "rollout-r3": ("8250df", "R3 - CP-SAT roster solver"),
    "rollout-r4": ("d93f0b", "R4 - shift swaps and giveaways"),
    "backend": ("5319e7", "FastAPI / SQLAlchemy backend"),
    "frontend": ("006b75", "Next.js frontend"),
    "mcp": ("bfd4f2", "FastMCP server"),
    "schema": ("b60205", "Database schema and migrations"),
    "architecture": ("fbca04", "Cross-cutting structural change"),
    "compliance": ("c2e0c6", "Working-time law and co-determination"),
    "solver": ("d4c5f9", "Optimization"),
    "ux": ("f9d0c4", "User-facing interaction design"),
    "chore": ("ededed", "Maintenance"),
    "blocker": ("e11d21", "Blocks other work"),
    "testing": ("0e8a16", "Test fixtures and coverage"),
    "spike": ("fef2c0", "Timeboxed investigation, not shipped"),
}

FRONT_MATTER = re.compile(r"^---\s*\ntitle:\s*\"(?P<title>.+?)\"\s*\nlabels:\s*(?P<labels>.*?)\s*\n---\s*\n", re.S)
REF = re.compile(r"#(\d{2})\b")


def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=check, capture_output=True, text=True)


def parse(path: Path) -> tuple[str, list[str], str]:
    raw = path.read_text()
    m = FRONT_MATTER.match(raw)
    if not m:
        sys.exit(f"{path.name}: missing or malformed front matter")
    title = m.group("title")
    labels = [x.strip() for x in m.group("labels").split(",") if x.strip()]
    body = raw[m.end():]
    return title, labels, body


def ensure_labels(labels: set[str], dry_run: bool) -> None:
    for name in sorted(labels):
        color, desc = LABEL_COLORS.get(name, ("cccccc", ""))
        cmd = ["gh", "label", "create", name, "--color", color, "--description", desc, "--force"]
        if dry_run:
            print("  would run:", " ".join(cmd))
            continue
        run(cmd)


MAP_PATH = ISSUE_DIR.parent / "created-issues.json"


def load_map() -> dict[str, int]:
    if MAP_PATH.exists():
        return {str(k): int(v) for k, v in json.loads(MAP_PATH.read_text()).items()}
    return {}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "--only",
        help="Comma-separated file prefixes to create, e.g. --only 24,25. "
        "Without it, every file not already in created-issues.json is created.",
    )
    args = ap.parse_args()

    files = sorted(ISSUE_DIR.glob("*.md"))
    if not files:
        sys.exit(f"no issue files found in {ISSUE_DIR}")

    parsed = [(p, *parse(p)) for p in files]
    numbers = load_map()
    if numbers:
        print(f"Known issues from {MAP_PATH.name}: {len(numbers)}")

    wanted = {k.strip() for k in args.only.split(",")} if args.only else None
    todo = []
    for path, title, labels, body in parsed:
        key = path.name[:2]
        if wanted is not None and key not in wanted:
            continue
        if key in numbers:
            print(f"  [{key}] already #{numbers[key]}, skipping")
            continue
        todo.append((key, path, title, labels, body))

    if not todo:
        sys.exit("\nNothing to create. Delete an entry from created-issues.json to recreate one.")

    all_labels = {lbl for _, _, _, labels, _ in todo for lbl in labels}
    print(f"\n{len(todo)} issues to create, {len(all_labels)} labels")
    print("\nEnsuring labels exist...")
    ensure_labels(all_labels, args.dry_run)

    print("\nCreating issues...")
    created: list[tuple[str, str]] = []
    for key, _path, title, labels, body in todo:
        # neutralise cross-references until real numbers are known
        staged = REF.sub(r"ISSUE-\1", body)
        cmd = ["gh", "issue", "create", "--title", title, "--body", staged]
        for lbl in labels:
            cmd += ["--label", lbl]
        if args.dry_run:
            print(f"  [{key}] would create: {title}  labels={labels}")
            numbers[key] = 1000 + int(key)
            created.append((key, body))
            continue
        out = run(cmd).stdout.strip()
        num = int(out.rstrip("/").split("/")[-1])
        numbers[key] = num
        created.append((key, body))
        print(f"  [{key}] #{num}  {title}")

    print("\nRewriting cross-references in the new issues...")
    for key, body in created:
        if not REF.search(body):
            continue

        def sub(m: re.Match) -> str:
            target = numbers.get(m.group(1))
            return f"#{target}" if target else m.group(0)

        final = REF.sub(sub, body)
        cmd = ["gh", "issue", "edit", str(numbers[key]), "--body", final]
        if args.dry_run:
            print(f"  [{key}] would rewrite references in #{numbers[key]}")
            continue
        run(cmd)
        print(f"  [{key}] #{numbers[key]} references updated")

    if not args.dry_run:
        MAP_PATH.write_text(json.dumps(dict(sorted(numbers.items())), indent=2) + "\n")
        print(f"\nUpdated {MAP_PATH.name}")

    print("\nDone.")


if __name__ == "__main__":
    main()
