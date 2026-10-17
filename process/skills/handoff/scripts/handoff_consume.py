#!/usr/bin/env python
"""Consume a handoff primer: mark it CONSUMED, move it to `archive/`, commit that as its
own commit, and prove the marker is in the committed bytes.

Why a script: the prose procedure failed repeatedly in the repo this was built in. A
`git mv` right after an uncommitted edit can stage the pre-edit content, so the marker
never reaches the commit, and `Read`ing the file back (the working tree) hides it. This
script orders the steps so that cannot happen, then checks the real commit.

Order, by construction: `git mv` to archive/  ->  write the marker at the NEW path  ->
`git add <new>`  ->  `git commit -- <old> <new>` (a pathspec commit, so another session's
staged files never ride along)  ->  `git show HEAD:<new>` and compare the bytes.

Usage:
    python handoff_consume.py <primer.md> --reason "superseded by <path>" [options]
Options:
    --message TEXT    commit subject (default: "Archive consumed handoff primer: <file> (<reason>)")
    --trailer LINE    a trailer line for the commit body (repeatable; for example a
                      Co-Authored-By line)
    --date YYYY-MM-DD marker date (default: today)
    --dry-run         print the plan and change nothing

Exit codes:
    0  consumed, and the marker was found in `git show HEAD:<archive path>`
    1  refused, or failed and rolled back; the primer is exactly as it was
    2  the commit landed but the proof failed; do NOT report the primer consumed, a
       corrective commit is needed (the output names the commit)

Output is ASCII-only. The marker itself contains an em dash (U+2014) and is written
as UTF-8 bytes, preserving the file's line endings and any BOM.
"""
import argparse
import datetime
import os
import subprocess
import sys
from pathlib import Path

DASH = "—"
BOM = b"\xef\xbb\xbf"
EXISTING_MARKER = b"> **CONSUMED"


def marker_core(date: str, reason: str) -> str:
    return f"> **CONSUMED {date} {DASH} {reason}.**"


def _git(root, *args, text=True, check=False):
    cmd = ["git", "-C", str(root), *args]
    if text:
        return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return subprocess.run(cmd, capture_output=True)


def _say(msg):
    print(msg.encode("ascii", "replace").decode("ascii"))


def _porcelain(root, rel):
    """Return the two-letter XY status of one path, or '' when clean/untracked-absent."""
    r = _git(root, "status", "--porcelain=v1", "-z", "--", rel, text=False)
    if r.returncode != 0:
        return None
    out = r.stdout.decode("utf-8", "replace")
    entries = [e for e in out.split("\0") if e]
    if not entries:
        return ""
    return entries[0][:2]


def verify_committed(root, rel_new: str, rel_old: str, core: str, was_tracked: bool):
    """Proof step: the committed blob at rel_new starts with the marker (BOM tolerated,
    line ending ignored) and, for a tracked primer, rel_old is gone from HEAD."""
    r = _git(root, "show", f"HEAD:{rel_new}", text=False)
    if r.returncode != 0:
        return False, f"git show HEAD:{rel_new} failed"
    blob = r.stdout
    if blob.startswith(BOM):
        blob = blob[len(BOM):]
    if not blob.startswith(core.encode("utf-8")):
        return False, "marker not found at the start of the committed file"
    if was_tracked:
        gone = _git(root, "cat-file", "-e", f"HEAD:{rel_old}")
        if gone.returncode == 0:
            return False, "the old path is still present in HEAD"
    return True, ""


def _rollback(root, old: Path, new: Path, rel_old, rel_new, orig_bytes, was_tracked, made_archive):
    notes = []
    if was_tracked:
        _git(root, "reset", "-q", "HEAD", "--", rel_old, rel_new)
    else:
        # the untracked path was `git add`ed at its archive name; unstage it again
        _git(root, "rm", "--cached", "-q", "--ignore-unmatch", "--", rel_new)
    try:
        old.parent.mkdir(parents=True, exist_ok=True)
        old.write_bytes(orig_bytes)
        if new.exists():
            new.unlink()
        if made_archive:
            try:
                new.parent.rmdir()
            except OSError:
                pass
    except OSError as e:
        notes.append(f"working-tree restore failed: {e}")
    return notes


def consume(primer, reason, message=None, trailers=(), date=None, dry_run=False):
    reason = (reason or "").strip()
    if not reason or "\n" in reason:
        _say("refused: --reason must be a non-empty single line")
        return 1
    date = date or datetime.date.today().isoformat()
    old = Path(primer).resolve()
    if not old.is_file():
        _say(f"refused: not a file: {old}")
        return 1
    if old.suffix.lower() != ".md" or old.parent.name != "handoffs" or old.parent.parent.name != ".claude":
        _say("refused: not a primer path (expected <repo>/.claude/handoffs/<name>.md, top level)")
        return 1
    top = _git(old.parent, "rev-parse", "--show-toplevel")
    if top.returncode != 0:
        _say("refused: the primer is not inside a git repository")
        return 1
    root = Path(top.stdout.strip())
    rel_old = old.relative_to(root.resolve()).as_posix()
    new = old.parent / "archive" / old.name
    rel_new = new.relative_to(root.resolve()).as_posix()
    if new.exists():
        _say(f"refused: archive name already exists: {rel_new}")
        return 1

    xy = _porcelain(root, rel_old)
    if xy is None:
        _say("refused: git status failed (is another git process running?)")
        return 1
    untracked = xy == "??"
    staged_or_both = xy and xy not in (" M", "??") and (xy[0] != " ")
    if staged_or_both:
        _say(f"refused: {rel_old} shows staged state ({xy.strip() or xy}); another session may be mid-add, "
             "so it is not safe to commit it. Name it in the next primer instead.")
        return 1
    was_tracked = not untracked

    default_msg = f"Archive consumed handoff primer: {old.name} ({reason})"
    plan = [
        ("move", f"{rel_old} -> {rel_new}" + (" (plain move, primer is untracked)" if untracked else " (git mv)")),
        ("marker", marker_core(date, reason).replace(DASH, "-") + "   (written with an em dash)"),
        ("commit", (message or default_msg) + f" -- paths: {rel_new}" + ("" if untracked else f", {rel_old}")),
    ]
    if dry_run:
        for k, v in plan:
            _say(f"plan {k}: {v}")
        _say("dry run: nothing changed")
        return 0

    orig_bytes = old.read_bytes()
    made_archive = not new.parent.exists()
    new.parent.mkdir(parents=True, exist_ok=True)

    try:
        if was_tracked:
            r = _git(root, "mv", "--", rel_old, rel_new)
            if r.returncode != 0:
                if made_archive:
                    try:
                        new.parent.rmdir()
                    except OSError:
                        pass
                _say("refused: git mv failed: " + (r.stderr.strip() or r.stdout.strip()))
                return 1
        else:
            os.replace(old, new)

        data = new.read_bytes()
        bom = BOM if data.startswith(BOM) else b""
        body = data[len(bom):]
        eol = b"\r\n" if b"\r\n" in body[:4096] else b"\n"
        if body.startswith(EXISTING_MARKER):
            # a half-finished consume: the primer already carries a marker; archive it, add no second one
            core = body.split(b"\n", 1)[0].rstrip(b"\r").decode("utf-8", "replace")
        else:
            core = marker_core(date, reason)
            new.write_bytes(bom + core.encode("utf-8") + eol + eol + body)

        r = _git(root, "add", "--", rel_new)
        if r.returncode != 0:
            raise RuntimeError("git add failed: " + (r.stderr.strip() or r.stdout.strip()))

        cmd = ["commit", "-m", message or default_msg]
        if trailers:
            cmd += ["-m", "\n".join(trailers)]
        cmd += ["--", rel_new] + ([] if untracked else [rel_old])
        r = _git(root, *cmd)
        if r.returncode != 0:
            real = [ln for ln in (r.stderr + "\n" + r.stdout).splitlines()
                    if ln.strip() and not ln.startswith("warning:")]
            raise RuntimeError("git commit failed: " + (" / ".join(real[-3:])[:300] or "no reason given by git"))
    except Exception as e:  # noqa: BLE001 - every failure after the move must roll back
        notes = _rollback(root, old, new, rel_old, rel_new, orig_bytes, was_tracked, made_archive)
        _say(f"failed and rolled back, the primer is as it was: {e}")
        for n in notes:
            _say("warning: " + n)
        return 1

    head = _git(root, "rev-parse", "--short", "HEAD").stdout.strip()
    ok, why = verify_committed(root, rel_new, rel_old, core, was_tracked)
    if not ok:
        _say(f"PROOF FAILED after commit {head}: {why}. Do NOT report this primer consumed; "
             f"a corrective commit is needed for {rel_new}.")
        return 2
    _say(f"consumed: {head} {rel_new} (marker verified in git show HEAD:{rel_new})"
         + (" (the primer was untracked: plain move, then git add)" if untracked else ""))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("primer")
    ap.add_argument("--reason", required=True)
    ap.add_argument("--message")
    ap.add_argument("--trailer", action="append", default=[])
    ap.add_argument("--date")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    return consume(a.primer, a.reason, a.message, a.trailer, a.date, a.dry_run)


if __name__ == "__main__":
    sys.exit(main())
