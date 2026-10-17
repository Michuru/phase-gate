#!/usr/bin/env python
"""List the live handoff primers across your repos, for /handoff's incoming path.

Liveness is directory position only: a primer is live when it sits at the top level of
a repo's `.claude/handoffs/` (never `archive/`). File contents are read only for
display (the first heading and a CONSUMED marker); this script never judges whether a
thread is closed, never touches a file, and never consumes one.

Scope: this repo's own `.claude/handoffs/` (the repo containing the current directory),
every directory directly under it that has its own `.claude/handoffs/` (found by
directory listing, so a new nested repo needs no edit here), and EXTERNAL_REPOS below,
repos that live outside this tree and so cannot be found by listing. Add a repo to
EXTERNAL_REPOS (or pass --external) the first time a live primer turns up in one the
scan missed.

Usage:
    python handoff_scan.py                  # text, one line per live primer
    python handoff_scan.py --json           # the same rows as JSON
    python handoff_scan.py --root DIR --external DIR ...   # override the roots

Paths are printed as `os.path.abspath` strings.
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

# Repos that live outside the tree this repo sits in, one absolute path per entry. Edit this list.
EXTERNAL_REPOS = []

DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")


def _repo_root() -> Path:
    try:
        r = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip():
            return Path(r.stdout.strip())
    except OSError:
        pass
    return Path.cwd()


def _read_head(path: Path, limit: int = 4000) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read(limit)
    except OSError:
        return ""


def _first_heading(text: str) -> str:
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("#"):
            return s.lstrip("#").strip()[:110]
    for line in text.splitlines():
        s = line.strip()
        if s and not s.startswith(">"):
            return s[:110]
    return ""


def _row(repo_name: str, path: Path) -> dict:
    head = _read_head(path)
    m = DATE_RE.match(path.name)
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = 0
    first_line = head.lstrip().splitlines()[0] if head.strip() else ""
    return {
        "repo": repo_name,
        "file": path.name,
        "path": os.path.abspath(str(path)),
        "date": m.group(1) if m else "",
        "mtime": mtime,
        "heading": _first_heading(head),
        # A file that already carries the marker but still sits at the top level is a
        # half-finished consume (or a hand edit): flagged so nobody resumes it as live.
        "consumed_marker_at_top_level": "CONSUMED" in first_line,
    }


def _top_level_primers(repo_root: Path):
    d = repo_root / ".claude" / "handoffs"
    if not d.is_dir():
        return None
    return sorted(p for p in d.iterdir() if p.is_file() and p.suffix.lower() == ".md")


def scan(root: Path, external_repos):
    rows, notes = [], []
    repos = [(root.name or "repo", root)]
    try:
        for child in sorted(root.iterdir()):
            if child.is_dir() and not child.name.startswith("."):
                repos.append((child.name, child))
    except OSError as e:
        notes.append(f"cannot list {root}: {e}")
    for name, repo in repos:
        files = _top_level_primers(repo)
        if files:
            rows += [_row(name, f) for f in files]
    for ext in external_repos:
        ext = Path(ext)
        files = _top_level_primers(ext)
        if files is None:
            notes.append(f"listed external repo has no handoffs dir: {ext}")
        else:
            rows += [_row(ext.name, f) for f in files]
    rows.sort(key=lambda r: (r["mtime"], r["path"]), reverse=True)
    return rows, notes


def _format(rows, notes):
    out = []
    if not rows:
        out.append("no live primers")
    for r in rows:
        bits = [r["repo"], r["file"]]
        if r["consumed_marker_at_top_level"]:
            bits.append("CONSUMED marker at top level (half-done consume, not live)")
        bits.append(r["heading"])
        out.append(" | ".join(bits))
        out.append("    " + r["path"])
    for n in notes:
        out.append("note: " + n)
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--root", default=None, help="the repo to scan (default: the repo containing the current directory)")
    ap.add_argument("--external", action="append", default=None)
    a = ap.parse_args(argv)
    root = Path(a.root) if a.root else _repo_root()
    external = a.external if a.external is not None else EXTERNAL_REPOS
    rows, notes = scan(root, external)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    if a.json:
        print(json.dumps({"primers": rows, "notes": notes}, indent=2))
    else:
        print(_format(rows, notes))
    return 0


if __name__ == "__main__":
    sys.exit(main())
