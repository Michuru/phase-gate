"""Stop hook: nudge toward wrapping up as a session's context usage climbs.

Reads the hook's stdin JSON payload, finds the transcript's own last assistant
turn with a usage object, and estimates % of that turn's model's context
window. Fires a systemMessage once per debounce tier (50/60/70/80/90) per
session, never more often.
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

# A transcript below this size cannot plausibly be near even the lowest
# debounce tier (50%) for any known model's window - skip the backward scan
# entirely below it. This floor is deliberately conservative (small), not
# tuned to any one worst case.
SIZE_FLOOR_BYTES = 2_000_000

# How far back from EOF we're willing to scan looking for the last assistant
# usage line, before giving up. Bounds worst-case work on a malformed tail.
MAX_BACKWARD_SCAN_BYTES = 20_000_000
CHUNK_SIZE = 65_536

# Context-window sizes per model family - see your Claude Code version's
# model docs if these drift. Unrecognized models fall back to the smallest/
# safest known window so an unmapped future model doesn't silently suppress
# the nudge.
MODEL_CONTEXT_WINDOWS = {
    "claude-sonnet-5": 1_000_000,
    "claude-opus-5": 1_000_000,
    "claude-fable-5": 1_000_000,
    "claude-haiku-4-5": 200_000,
}
# Family-prefix fallback for a model string that isn't an exact key above (a point release like
# "claude-fable-5-1", or a bare alias like "fable"/"sonnet") - an exact-match-only lookup makes a
# 1M-window model look like it's using 5x more of its context than it really is, which is worse
# than the "unmapped model" case the exact-match default already guards against; it hits the
# nudge tiers 5x too early on every affected session, not just an unusual one.
MODEL_FAMILY_WINDOWS = {
    "sonnet": 1_000_000,
    "opus": 1_000_000,
    "fable": 1_000_000,
    "haiku": 200_000,
}
DEFAULT_CONTEXT_WINDOW = 200_000


def context_window_for(model: str) -> int:
    if model in MODEL_CONTEXT_WINDOWS:
        return MODEL_CONTEXT_WINDOWS[model]
    model_lower = (model or "").lower()
    for family, window in MODEL_FAMILY_WINDOWS.items():
        if family in model_lower:
            return window
    return DEFAULT_CONTEXT_WINDOW

TIERS = (50, 60, 70, 80, 90)
STATE_MAX_AGE_DAYS = 30

SCRIPT_DIR = Path(__file__).resolve().parent
CLAUDE_DIR = SCRIPT_DIR.parent
STATE_PATH = CLAUDE_DIR / "state" / "context-usage-nudge.json"
LOCK_PATH = STATE_PATH.with_suffix(".lock")
LOCK_RETRY_ATTEMPTS = 20
LOCK_RETRY_DELAY_SECONDS = 0.05
# The critical section this lock guards is a small JSON read-modify-write, never more than a few
# milliseconds - a lock file older than this was almost certainly abandoned by a process that
# crashed or was killed before reaching __exit__, not one genuinely still holding it. Without
# this, a single abandoned lock costs every future Stop hook the full retry budget
# (LOCK_RETRY_ATTEMPTS * LOCK_RETRY_DELAY_SECONDS, about a second) forever, with no recovery path.
STALE_LOCK_SECONDS = 30


class _StateLock:
    """Exclusive-create lockfile guarding the state read-modify-write.

    Multiple Claude Code sessions can run concurrently against the same
    machine by design, and each fires this hook independently - without a
    lock, two Stop events racing on the shared state file could silently
    drop one session's just-written debounce tier. If the lock can't be
    acquired within the retry budget, proceed unlocked rather than block a
    Stop hook indefinitely - worst case reverts to that same low-impact
    race (at most one duplicate nudge), never a crash or corrupted file.
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


def find_last_assistant_usage(transcript_path: Path):
    """Scan backward from EOF for the last {"type":"assistant", message:{usage:...}} line."""
    try:
        size = transcript_path.stat().st_size
        read_from = size
        buffer = b""
        scanned = 0

        with transcript_path.open("rb") as f:
            while read_from > 0 and scanned < MAX_BACKWARD_SCAN_BYTES:
                chunk_len = min(CHUNK_SIZE, read_from)
                read_from -= chunk_len
                f.seek(read_from)
                chunk = f.read(chunk_len)
                buffer = chunk + buffer
                scanned += chunk_len

                lines = buffer.split(b"\n")
                # The first entry may be a partial line (chunk boundary) - keep
                # its raw bytes in the buffer for the next iteration rather
                # than decoding it now. Splitting on the raw newline byte
                # before decoding (never decoding a partial chunk on its own)
                # is safe because UTF-8 continuation bytes are never 0x0A, so
                # a multi-byte character can never itself contain a line
                # break - only whole, complete lines get decoded.
                buffer = lines[0]
                candidates = lines[1:]

                for raw_line in reversed(candidates):
                    line = raw_line.strip()
                    if not line or b'"type":"assistant"' not in line.replace(b" ", b""):
                        continue
                    try:
                        obj = json.loads(line.decode("utf-8"))
                    except (ValueError, UnicodeDecodeError):
                        continue
                    if obj.get("type") != "assistant":
                        continue
                    message = obj.get("message")
                    if not isinstance(message, dict):
                        continue
                    usage = message.get("usage")
                    if isinstance(usage, dict):
                        return message.get("model"), usage
    except OSError:
        return None, None

    return None, None


def load_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(state: dict) -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=STATE_MAX_AGE_DAYS)
    pruned = {}
    for session_id, entry in state.items():
        updated = entry.get("updated")
        try:
            if updated and datetime.fromisoformat(updated) >= cutoff:
                pruned[session_id] = entry
        except ValueError:
            continue
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = STATE_PATH.with_suffix(f".tmp-{os.getpid()}")
    tmp_path.write_text(json.dumps(pruned, indent=2), encoding="utf-8")
    os.replace(tmp_path, STATE_PATH)


def highest_crossed_tier(pct: float) -> int | None:
    crossed = [t for t in TIERS if pct >= t]
    return max(crossed) if crossed else None


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return
    if not isinstance(payload, dict):
        return

    session_id = payload.get("session_id")
    transcript_path_str = payload.get("transcript_path")
    if not session_id or not transcript_path_str:
        return

    transcript_path = Path(transcript_path_str)
    try:
        if transcript_path.stat().st_size < SIZE_FLOOR_BYTES:
            return
    except OSError:
        return

    model, usage = find_last_assistant_usage(transcript_path)
    if usage is None:
        return

    total = (
        usage.get("input_tokens", 0)
        + usage.get("cache_creation_input_tokens", 0)
        + usage.get("cache_read_input_tokens", 0)
    )
    window = context_window_for(model)
    pct = (total / window) * 100 if window else 0

    tier = highest_crossed_tier(pct)
    if tier is None:
        return

    with _StateLock():
        state = load_state()
        last_tier = state.get(session_id, {}).get("last_tier", 0)
        if tier <= last_tier:
            return

        state[session_id] = {
            "last_tier": tier,
            "updated": datetime.now(timezone.utc).isoformat(),
        }
        save_state(state)

    message = (
        f"Context usage ~{pct:.0f}% (approx: {total:,} tokens / "
        f"~{window:,}-token window for {model or 'unknown model'}). "
        "Consider writing yourself a handoff/summary of where things stand, "
        "or continue if this is already a natural stopping point."
    )
    print(json.dumps({"systemMessage": message}))


if __name__ == "__main__":
    main()
