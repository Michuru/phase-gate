"""SessionStart hook: after a bare /clear, offer the window the handoff primer it wrote just before.

A window that kept its /rename name across /clear (session_title in the hook input) and that wrote a primer through /handoff
(a pointer file, handoff_pointer.py) is told, through additionalContext, which primer is waiting. The model still decides nothing
alone: it checks its own ListAgents [ref] against the pointer's, then runs the handoff skill's incoming path on that one primer
when the user's first message is a go-ahead.

Acts only for source == "clear" with a session_title; silent in every other case (no title, no pointer, more than one pointer, the
primer gone or archived, older than two hours, any error). Never blocks: any error exits 0 with no output.

Wired into .claude/settings.json (see settings.fragment.json), with handoff_pointer.py installed beside it in .claude/hooks/.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

HEADING_CAP = 110


def _clean(text: str, cap: int = HEADING_CAP) -> str:
    return re.sub(r"[\x00-\x1f\x7f]+", " ", text).strip()[:cap]


def _heading(primer: str) -> str:
    """The primer's first heading, capped at 110 characters, or "" when it cannot be read."""
    try:
        text = Path(primer).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("#"):
            return _clean(s.lstrip("#"))
    return ""


def build_output(payload: dict, now=None):
    """The hook's JSON output as a dict, or None when nothing should be said."""
    if payload.get("source") != "clear":
        return None
    title = payload.get("session_title")
    if not isinstance(title, str) or not title.strip():
        return None
    import handoff_pointer

    hits = handoff_pointer.find(title, now=now)
    if len(hits) != 1:
        return None
    e = hits[0]

    heading = _heading(e["primer"])
    name = _clean(e["name"], 60)
    ref = e["ref"]
    context = (
        f"[handoff resume] This window ({name}) wrote a primer just before /clear: {e['primer']}"
        f"{' (' + heading + ')' if heading else ''}. "
        f"First run ListAgents: the first line's [ref] must be {ref}; if it is not, this primer belongs to a different window with "
        "the same name, so do not resume it (use the normal handoff scan only if the user is asking to resume). Then, when the user's "
        "first message is a plain go-ahead to resume (for example `go`, `continue`, `resume`, `yes`) or `/handoff`, run the handoff "
        "skill's incoming path on this one primer and skip the scan. The user's go-ahead is the confirmation when the closed-thread "
        "check finds no sign the thread is finished. "
        "If the first message is about something else, mention the waiting primer in one line and do that task; this line then "
        "stops governing, and a later `/handoff` after real work is an outgoing handoff as usual."
    )
    short = f"Handoff primer waiting for this window ({name}): {Path(e['primer']).name}. Say \"go\" to resume it."
    return {
        "systemMessage": short,
        "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": context},
    }


def main() -> int:
    try:
        # decode as UTF-8 explicitly: a piped stdin defaults to the locale code page (cp1252 on Windows), which would turn a
        # non-ASCII session_title into different characters than the pointer's name and silently never match
        payload = json.loads(sys.stdin.buffer.read().decode("utf-8", errors="replace"))
        if not isinstance(payload, dict):
            return 0
        out = build_output(payload)
        if out:
            try:
                sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
            print(json.dumps(out))
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
