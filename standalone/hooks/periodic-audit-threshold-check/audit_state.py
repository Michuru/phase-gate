"""Shared state/lock helper for periodic-audit's threshold hook and skill.

Uses an exclusive-create lockfile with a stale-lock age-out (a killed process
must not leave the lock behind forever — a naive lock that only unlinks on a
clean exit burns every later acquisition's full retry budget then proceeds
*unlocked*, which is tolerable for a debounce-only use but not here, where a
lost read-modify-write would silently clobber one pass's completion marker
with the other's — exactly the per-pass independence this design depends
on). No age-based pruning of old entries — a tool doesn't stop mattering
after 30 days, so history is kept indefinitely.

Used both by audit-threshold-check.py (read-only) and the periodic-audit
skill (read-write, via this module's CLI — never a free-hand edit on the
state file itself, so every writer goes through the same lock/atomic-write
path).

CLI:
    python audit_state.py get <repo> <main_file>
    python audit_state.py set <repo> <main_file> <pass> <field> <value>
        pass: coverage_gap | structural
        field: last_audited_commit | status | na_reason | ledger_hash
"""
import json
import os
import sys
import time
from pathlib import Path

# CLAUDE_PROJECT_DIR is set by Claude Code for hook invocations; falls back to
# the current working directory for a direct CLI call from the skill (which
# runs from the repo root by convention).
PROJECT_DIR = Path(os.environ.get("CLAUDE_PROJECT_DIR", ".")).resolve()
STATE_PATH = PROJECT_DIR / ".claude" / "state" / "audit-thresholds.json"
LOCK_PATH = STATE_PATH.with_suffix(".lock")
LOCK_RETRY_ATTEMPTS = 20
LOCK_RETRY_DELAY_SECONDS = 0.05
# The critical section here is a small JSON read-modify-write, never more than
# a few milliseconds - a lock file older than this was almost certainly
# abandoned by a crashed/killed process, not one genuinely still holding it.
STALE_LOCK_SECONDS = 30


class _StateLock:
    """Exclusive-create lockfile guarding the state read-modify-write, with
    a stale-lock age-out.
    """

    def __enter__(self):
        LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._fd = None
        for _ in range(LOCK_RETRY_ATTEMPTS):
            try:
                self._fd = os.open(str(LOCK_PATH), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                break
            except FileExistsError:
                try:
                    age = time.time() - LOCK_PATH.stat().st_mtime
                    if age > STALE_LOCK_SECONDS:
                        LOCK_PATH.unlink()
                        continue  # try to acquire immediately, no need to sleep first
                except OSError:
                    pass  # lock vanished between the failed open and the stat/unlink - fine, retry
                time.sleep(LOCK_RETRY_DELAY_SECONDS)
        return self

    def __exit__(self, *exc_info):
        if self._fd is not None:
            os.close(self._fd)
            try:
                LOCK_PATH.unlink()
            except OSError:
                pass


def load_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(state: dict) -> None:
    """No age-based pruning - every entry is kept indefinitely."""
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = STATE_PATH.with_suffix(f".tmp-{os.getpid()}")
    tmp_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    os.replace(tmp_path, STATE_PATH)  # atomic - never a half-written state file


def _key(repo: str, main_file: str) -> str:
    return f"{repo}/{main_file}"


def get_entry(repo: str, main_file: str) -> dict:
    """Returns the per-tool state entry, or {} if this tool has never been
    recorded (the "missing state entry" bootstrap case - callers should
    treat an empty dict as "run a one-shot bootstrap pass regardless of
    threshold", per the design's bootstrap semantics).
    """
    state = load_state()
    return state.get(_key(repo, main_file), {})


def set_field(repo: str, main_file: str, pass_name: str, field: str, value) -> None:
    """pass_name is 'coverage_gap' or 'structural' - tracked independently,
    since the two passes can complete at different times.
    """
    if pass_name not in ("coverage_gap", "structural"):
        raise ValueError(f"unknown pass_name: {pass_name!r}")
    with _StateLock():
        state = load_state()
        key = _key(repo, main_file)
        entry = state.setdefault(key, {})
        pass_entry = entry.setdefault(pass_name, {})
        pass_entry[field] = value
        save_state(state)


def _cli():
    if len(sys.argv) < 2:
        print("usage: audit_state.py get <repo> <main_file>", file=sys.stderr)
        print("       audit_state.py set <repo> <main_file> <pass> <field> <value>", file=sys.stderr)
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "get" and len(sys.argv) == 4:
        entry = get_entry(sys.argv[2], sys.argv[3])
        print(json.dumps(entry, indent=2))
    elif cmd == "set" and len(sys.argv) == 7:
        set_field(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5], sys.argv[6])
    else:
        print("bad arguments", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    _cli()
