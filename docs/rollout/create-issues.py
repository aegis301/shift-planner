#!/usr/bin/env python3
"""Create the rollout issues in GitHub from the markdown files in docs/rollout/issues/.

Usage:
    python3 docs/rollout/create-issues.py --dry-run
    python3 docs/rollout/create-issues.py

Requires an authenticated `gh` CLI with write access to the repository.

Issue bodies reference each other by file number (`#04`). Those are placeholders: the
script creates every issue first, then rewrites the references to the real issue numbers
in a second pass. Nothing is created twice — re-running after a partial failure will
create duplicates, so check `gh issue list` first if a run aborts halfway.
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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    files = sorted(ISSUE_DIR.glob("*.md"))
    if not files:
        sys.exit(f"no issue files found in {ISSUE_DIR}")

    parsed = [(p, *parse(p)) for p in files]
    all_labels = {lbl for _, _, labels, _ in parsed for lbl in labels}

    print(f"{len(parsed)} issues, {len(all_labels)} labels")
    print("\nEnsuring labels exist...")
    ensure_labels(all_labels, args.dry_run)

    print("\nCreating issues...")
    numbers: dict[str, int] = {}
    for path, title, labels, body in parsed:
        key = path.name[:2]
        # neutralise cross-references until real numbers are known
        staged = REF.sub(r"ISSUE-\1", body)
        cmd = ["gh", "issue", "create", "--title", title, "--body", staged]
        for lbl in labels:
            cmd += ["--label", lbl]
        if args.dry_run:
            print(f"  [{key}] would create: {title}  labels={labels}")
            numbers[key] = 1000 + int(key)
            continue
        out = run(cmd).stdout.strip()
        num = int(out.rstrip("/").split("/")[-1])
        numbers[key] = num
        print(f"  [{key}] #{num}  {title}")

    print("\nRewriting cross-references...")
    for path, _title, _labels, body in parsed:
        key = path.name[:2]
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
        (ISSUE_DIR.parent / "created-issues.json").write_text(json.dumps(numbers, indent=2) + "\n")
        print("\nWrote docs/rollout/created-issues.json")

    print("\nDone.")


if __name__ == "__main__":
    main()
