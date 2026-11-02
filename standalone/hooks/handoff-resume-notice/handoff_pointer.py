#!/usr/bin/env python
"""Handoff pointers: "the window named X (ref R) wrote this primer", so the next window after a bare /clear can be offered it.

Design: Design Docs/auto-resume-handoff.md. A pointer is one small JSON file per writer session in
<claude dir>/state/handoff-pointers/ (gitignored; env HANDOFF_POINTER_DIR overrides it, for tests). Fields: name (the writer
transcript's customTitle, i.e. an owner-set /rename name), ref (the writer's six-hex ListAgents [ref], which survives a bare /clear),
session_id, transcript, primer (absolute path), written (UTC ISO time).

Commands (exit codes: 0 ok, 1 nothing to report, 2 bad arguments, 3 no owner-set name):
    write --session-id ID --transcript PATH --primer PATH --ref HEX6 [--name NAME]
          writes the pointer atomically; with no --name it reads the transcript's last custom-title record and exits 3 when there is
          none (the window was never /rename'd)
    find  --name NAME          prints the live pointers for that exact name as JSON lines
    name  --transcript PATH    prints the transcript's owner-set name, exit 1 when there is none

A pointer is live when its primer still sits at the top level of a `.claude/handoffs/` folder (liveness by directory position, the
same rule handoff_scan.py uses; nothing about the primer is judged) and it is under MAX_AGE_S old.
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

MAX_AGE_S = 2 * 3600  # a /clear normally follows a handoff within minutes
PRUNE_AGE_S = 7 * 24 * 3600
_ID_OK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,80}\Z")  # \Z, not $: `$` also matches before a trailing newline
_REF_OK = re.compile(r"^[0-9a-f]{6}\Z")


class NoOwnerName(Exception):
    """The transcript has no custom-title record: the window was never /rename'd."""


def pointer_dir() -> Path:
    env = os.environ.get("HANDOFF_POINTER_DIR")
    return Path(env) if env else Path(__file__).resolve().parent.parent / "state" / "handoff-pointers"


def custom_title(transcript) -> "str | None":
    """The last owner-set name recorded in a session transcript (a `custom-title` record), or None. Streams the file line by line,
    decoding only lines that carry the marker, so a very large transcript costs one pass and no memory."""
    last = None
    try:
        with open(transcript, "rb") as f:
            for raw in f:
                if b'"custom-title"' not in raw:
                    continue
                try:
                    obj = json.loads(raw.decode("utf-8", errors="replace"))
                except ValueError:
                    continue
                if isinstance(obj, dict) and obj.get("type") == "custom-title":
                    title = obj.get("customTitle")
                    if isinstance(title, str) and title.strip():
                        last = title.strip()
    except OSError:
        return None
    return last


def _now(now):
    return now if now is not None else datetime.now(timezone.utc)


def _prune(d: Path, now: datetime) -> None:
    cutoff = now - timedelta(seconds=PRUNE_AGE_S)
    for p in d.glob("*.json"):
        try:
            written = datetime.fromisoformat(json.loads(p.read_text(encoding="utf-8")).get("written", ""))
            if written < cutoff:
                p.unlink()
        except (OSError, ValueError, TypeError, AttributeError):
            continue  # an unreadable file is left alone: it is not ours to delete on a guess


def _supersede(d: Path, new: dict) -> None:
    """A window's newer handoff replaces its older pointers. The ListAgents [ref] survives a bare /clear, so two pointers with the
    same name AND the same ref are one window's earlier and later handoffs (the session id changed at the /clear); keeping both
    would make the hook see two matches and go silent. A different ref is a different window and is left alone, as is any file
    that cannot be read."""
    for p in d.glob("*.json"):
        if p.name == f"{new['session_id']}.json":
            continue
        try:
            e = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(e, dict) and e.get("name") == new["name"] and e.get("ref") == new["ref"]:
                p.unlink()
        except (OSError, ValueError):
            continue


def write(session_id: str, transcript: str, primer: str, ref: str, name: "str | None" = None, now=None) -> dict:
    if not _ID_OK.match(session_id or ""):
        raise ValueError(f"bad session id: {session_id!r}")
    if not _REF_OK.match(ref or ""):
        raise ValueError(f"bad ref (want six lowercase hex characters): {ref!r}")
    if not name:
        name = custom_title(transcript)
    if not name:
        raise NoOwnerName(f"{transcript} has no custom-title record")
    now = _now(now)
    entry = {
        "name": name,
        "ref": ref,
        "session_id": session_id,
        "transcript": str(transcript),
        "primer": os.path.abspath(primer),
        "written": now.isoformat(),
    }
    d = pointer_dir()
    d.mkdir(parents=True, exist_ok=True)
    dest = d / f"{session_id}.json"
    tmp = dest.with_suffix(".json.tmp")
    try:
        tmp.write_text(json.dumps(entry, indent=1), encoding="utf-8")
        os.replace(tmp, dest)
    except OSError:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
    _prune(d, now)
    _supersede(d, entry)
    return entry


def _primer_is_live(primer: str) -> bool:
    p = Path(primer)
    return p.is_file() and p.parent.name == "handoffs" and p.parent.parent.name == ".claude"


def find(name: str, now=None, max_age_s: int = MAX_AGE_S) -> list:
    """Live pointers whose name equals `name` exactly. A malformed file, a stale one, or one whose primer is gone or no longer at
    the top level of a handoffs folder is skipped, never an error."""
    now = _now(now)
    out = []
    d = pointer_dir()
    try:
        files = sorted(d.glob("*.json"))
    except OSError:
        return out
    for p in files:
        try:
            e = json.loads(p.read_text(encoding="utf-8"))
            if not isinstance(e, dict) or e.get("name") != name:
                continue
            if not (isinstance(e.get("primer"), str) and isinstance(e.get("ref"), str) and _REF_OK.match(e["ref"])):
                continue
            written = datetime.fromisoformat(e["written"])
            if written.tzinfo is None:
                written = written.replace(tzinfo=timezone.utc)
            if (now - written).total_seconds() > max_age_s or (now - written).total_seconds() < -60:
                continue
            if not _primer_is_live(e["primer"]):
                continue
            out.append(e)
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("write")
    w.add_argument("--session-id", required=True)
    w.add_argument("--transcript", required=True)
    w.add_argument("--primer", required=True)
    w.add_argument("--ref", required=True)
    w.add_argument("--name")
    f = sub.add_parser("find")
    f.add_argument("--name", required=True)
    n = sub.add_parser("name")
    n.add_argument("--transcript", required=True)
    try:
        a = ap.parse_args(argv)
    except SystemExit:
        return 2
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    if a.cmd == "write":
        try:
            e = write(a.session_id, a.transcript, a.primer, a.ref, a.name)
        except NoOwnerName as err:
            print(f"NO-OWNER-NAME: {err}")
            return 3
        except (ValueError, OSError) as err:
            print(f"ERROR: {err}")
            return 2
        print(f"WROTE {pointer_dir() / (e['session_id'] + '.json')}")
        return 0
    if a.cmd == "find":
        hits = find(a.name)
        for e in hits:
            print(json.dumps(e))
        return 0 if hits else 1
    title = custom_title(a.transcript)
    if title:
        print(title)
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
