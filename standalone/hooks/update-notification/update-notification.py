"""SessionStart hook: passively check whether phase-gate has moved past the
commit this repo was installed from, using the installer's own recorded
source_commit/source_origin. Never fetches or applies anything -- purely a
discovery nudge, printed once per new upstream commit and throttled to at
most one network check every 24h. Fails silently (exit 0, no message) on
anything it can't determine: no receipt, the check disabled, no git, no
network, no credentials, a malformed remote. See Design Docs/phase-gate-
update-notification.md (meta repo) for the full design and review history --
this script's hardening (env vars, temp-file stdout, nonzero-rc-as-failure)
exists specifically because phase-gate is still a private repo today, and a
naive `git ls-remote` against a private HTTPS remote can otherwise pop a
credential-manager GUI dialog that a timeout alone does not bound.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

THROTTLE_HOURS = 24
NETWORK_TIMEOUT_SECONDS = 5
GIT_CONNECT_TIMEOUT_SECONDS = 3

# Anchored to this script's own installed location (.claude/hooks/update-notification.py),
# never to the session's cwd -- sidesteps the subdirectory-started-session bug
# hooks-health-check.py once had (it resolved paths against cwd instead of the repo
# toplevel). Both receipt and state live under the same .claude/ this script is under,
# regardless of where the session happens to start.
SCRIPT_DIR = Path(__file__).resolve().parent
CLAUDE_DIR = SCRIPT_DIR.parent
RECEIPT_PATH = CLAUDE_DIR / "phase-gate-install" / "receipt.json"
STATE_PATH = CLAUDE_DIR / "state" / "update-notification.json"
LOCK_PATH = STATE_PATH.with_suffix(".lock")
LOCK_RETRY_ATTEMPTS = 20
LOCK_RETRY_DELAY_SECONDS = 0.05
# Same rationale as context-usage-nudge.py's identical constant: the critical section
# here is a small JSON read-modify-write, never more than a few milliseconds -- a lock
# file older than this was almost certainly abandoned by a crashed/killed process, not
# one genuinely still holding it.
STALE_LOCK_SECONDS = 30

# https://, ssh://, or git@host:path -- or an existing local filesystem path. Anything
# else is rejected before a git process is ever spawned: a source_origin value starting
# with "-" would otherwise be parsed by git as an option (e.g. --upload-pack=<cmd>
# against a local-path remote spawns arbitrary commands), the same class of risk
# verify_citations.py's own command allowlist exists to prevent elsewhere in this export.
_ALLOWED_URL_SCHEME = re.compile(r"^(https?://|ssh://|git@[^:@/]+:)")


class _StateLock:
    """Exclusive-create lockfile guarding the state read-modify-write.

    Identical pattern to context-usage-nudge.py's _StateLock -- multiple Claude Code
    sessions can run concurrently against the same repo, each firing this hook
    independently. If the lock can't be acquired within the retry budget, proceed
    unlocked rather than block a SessionStart indefinitely; worst case is a duplicate
    network check or a missed notify-once update, never a crash or corrupted file.
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


def _load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def load_state():
    return _load_json(STATE_PATH) or {}


def save_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = STATE_PATH.with_suffix(f".tmp-{os.getpid()}")
    tmp_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    os.replace(tmp_path, STATE_PATH)  # atomic - never a half-written state file


def is_update_check_enabled(receipt):
    """update_check_enabled is default-kind (see installer/variables.json) -- an
    absent entry means "use the shipped default" (true), matching every other
    default-kind variable's own resolution rule. Only an explicit false disables.
    """
    for entry in receipt.get("variables") or []:
        if entry.get("name") == "update_check_enabled":
            return entry.get("value") is not False
    return True


def strip_userinfo(url):
    """Defensive -- SKILL.md's install step already strips this at capture time, but
    an old receipt or a hand-edited one could still carry a credential-bearing URL.
    """
    return re.sub(r"^(https?://)[^/@]*@", r"\1", url)


def remote_head_sha(source_origin):
    """Returns (sha_or_None, ok). ok is False for every failure mode -- bad scheme,
    nonzero exit, timeout, exception -- deliberately made indistinguishable to the
    caller: every failure means "say nothing," never a guess.
    """
    if not _ALLOWED_URL_SCHEME.match(source_origin) and not os.path.exists(source_origin):
        return None, False

    env = dict(os.environ)
    # phase-gate is still a private repo today -- every real adopter installs from a
    # private remote, and Windows' Git Credential Manager pops a GUI dialog regardless
    # of tty when no credential is cached. These four together are what actually
    # suppress that across git's own prompt path, GCM's own UI, and SSH's prompts.
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GCM_INTERACTIVE"] = "never"
    env["GIT_ASKPASS"] = "true"  # an inert, always-available no-op; if unresolvable, git errors out non-interactively anyway - still a silent failure to us either way
    env["GIT_SSH_COMMAND"] = f"ssh -oBatchMode=yes -oConnectTimeout={GIT_CONNECT_TIMEOUT_SECONDS}"

    # stdout goes to a real temp file, never subprocess.PIPE: after a timeout kill,
    # subprocess.run's PIPE handling blocks draining the pipe until every process
    # holding its write end closes it (git's own transport child, a credential
    # helper) - which can outlive the stated timeout by a lot. A real file has no
    # such drain-on-close requirement.
    with tempfile.TemporaryFile() as out:
        try:
            proc = subprocess.run(
                [
                    "git",
                    "-c", "http.lowSpeedLimit=1000",
                    "-c", "http.lowSpeedTime=4",  # git itself gives up on a stalled connection
                    "ls-remote", "--", source_origin, "HEAD",
                ],
                stdout=out, stderr=subprocess.DEVNULL,
                env=env, timeout=NETWORK_TIMEOUT_SECONDS,
            )
        except Exception:
            return None, False
        if proc.returncode != 0:
            # Covers auth-denied/DNS-failure/not-found (all rc 128) as well as any
            # other nonzero exit - none of these raise a Python exception, so they
            # must be checked explicitly rather than relying on "except Exception".
            return None, False
        out.seek(0)
        line = out.read().decode("utf-8", errors="replace").strip()

    if not line:
        return None, False
    sha = line.split()[0]
    if len(sha) != 40 or not re.fullmatch(r"[0-9a-f]{40}", sha):
        return None, False
    return sha, True


def main():
    try:
        json.load(sys.stdin)  # drain stdin like the other bundled hooks; content unused
    except Exception:
        pass

    force = "--force" in sys.argv[1:]

    receipt = _load_json(RECEIPT_PATH)
    if not receipt:
        sys.exit(0)  # never installed via this installer, or receipt not yet written

    source_commit = receipt.get("source_commit")
    source_origin = receipt.get("source_origin")
    if not source_commit or not source_origin:
        sys.exit(0)  # an old receipt predating these fields - nothing to compare against

    if not is_update_check_enabled(receipt):
        sys.exit(0)

    source_origin = strip_userinfo(source_origin)

    with _StateLock():
        state = load_state()
        now = datetime.now(timezone.utc)

        stale = True
        if not force:
            last_checked_str = state.get("last_checked")
            if last_checked_str:
                try:
                    last_checked = datetime.fromisoformat(last_checked_str)
                    stale = (now - last_checked) >= timedelta(hours=THROTTLE_HOURS)
                except ValueError:
                    stale = True  # corrupt timestamp - treat as never checked

        if stale:
            sha, ok = remote_head_sha(source_origin)
            # Written regardless of outcome so a real failure still waits out the
            # throttle window rather than retrying every single session - but a
            # failed check stores None, which the comparison below always treats as
            # "no data, stay silent," never as "different from source_commit."
            state["last_checked"] = now.isoformat()
            state["last_remote_sha"] = sha if ok else None
            save_state(state)
        else:
            sha = state.get("last_remote_sha")

        if not sha:
            sys.exit(0)

        last_notified = state.get("last_notified_remote_sha")
        if sha != source_commit and sha != last_notified:
            state["last_notified_remote_sha"] = sha
            save_state(state)
            # Deliberately direction-neutral: a plain ls-remote can't tell "the remote
            # moved forward" from "the remote is behind what you have" (e.g. a receipt
            # captured against a local clone with unpushed commits) without a full
            # local clone to check ancestry - caught live during this component's own
            # scratch-repo install test, where the maintainer's own dev clone was
            # ahead of origin. Never assert a direction the check can't verify.
            message = (
                "phase-gate's origin is at a different commit than the one you installed "
                f"(you have `{source_commit[:7]}`, origin's `HEAD` is now `{sha[:7]}`). "
                "Worth re-running the phase-gate installer to see what changed."
            )
            print(json.dumps({"systemMessage": message}))

    sys.exit(0)


if __name__ == "__main__":
    main()
