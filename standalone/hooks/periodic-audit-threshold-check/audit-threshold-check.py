"""SessionStart hook: checks whether any registered tool in this repo, or in
any git repo nested directly one level under it, has crossed periodic-audit's
threshold - either enough commits touching its flagged surfaces, or a newly-
grown ledger entry with no matching commits yet. Read-only: never runs an
audit itself, only decides whether one is due and reports via systemMessage
(or, during the calibration period below, only logs).

Discovers repos dynamically rather than a hardcoded list - checks
CLAUDE_PROJECT_DIR itself, plus any immediate subdirectory that is its own
git root (the shape a monorepo-of-repos workspace has). If your workspace is
a single plain repo, this just checks that one repo and nothing else - no
config needed either way.

CALIBRATION_MODE ships True: a new tool's default commit_threshold of 5 can
trip immediately on a busy stretch, so nudging starts disabled and this hook
only logs what *would* have fired, to
.claude/state/audit-calibration-log.jsonl, until you've watched a real
calibration period and confirmed the threshold is sane for your own repo's
commit cadence. Flip to False once that's done.

See the periodic-audit skill's own SKILL.md for the full runbook this hook
feeds.
"""
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit_state  # noqa: E402

CALIBRATION_MODE = True
PROJECT_DIR = Path(os.environ.get("CLAUDE_PROJECT_DIR", ".")).resolve()
CALIBRATION_LOG_PATH = PROJECT_DIR / ".claude" / "state" / "audit-calibration-log.jsonl"


def discover_repos() -> dict:
    """CLAUDE_PROJECT_DIR itself, plus any immediate subdirectory that is its
    own git root. Never a fixed name list, so a workspace shaped differently
    than the one this was tested against still works with zero edits.
    """
    repos = {PROJECT_DIR.name or str(PROJECT_DIR): str(PROJECT_DIR)}
    try:
        for child in PROJECT_DIR.iterdir():
            if child.is_dir() and (child / ".git").exists():
                repos[child.name] = str(child)
    except OSError:
        pass
    return repos


REPOS = discover_repos()


def git(repo_path: str, *args):
    try:
        return subprocess.run(
            ["git", "-C", repo_path, *args],
            capture_output=True, text=True, timeout=5,
        )
    except Exception:
        return None


def ledger_path(repo_path: str, tool_key: str) -> Path:
    return Path(repo_path) / ".claude" / "audit-ledger" / f"{tool_key}.json"


def ledger_hash(repo_path: str, tool_key: str):
    p = ledger_path(repo_path, tool_key)
    try:
        data = p.read_bytes()
    except OSError:
        return None  # no ledger yet - nothing to hash, nothing to trigger on
    return hashlib.sha256(data).hexdigest()


def ledger_has_entries(repo_path: str, tool_key: str) -> bool:
    """True only if the ledger file exists AND has at least one real entry -
    a scaffolded ledger with "entries": [] must gate the same as no ledger
    file at all, not be treated as applicable.
    """
    try:
        data = json.loads(ledger_path(repo_path, tool_key).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return bool(data.get("entries"))


def check_tool(repo_key: str, repo_path: str, tool_key: str, cfg: dict) -> list[dict]:
    """Returns a list of fired-trigger dicts for this one tool."""
    findings = []
    main_file = cfg.get("main_file")
    if not main_file:
        return findings
    related = cfg.get("related_files") or []
    threshold = cfg.get("commit_threshold", 5)
    has_suite = bool(cfg.get("regression_suite"))
    files_to_track = [main_file, *related]

    for pass_name, applicable in (("coverage_gap", has_suite), ("structural", True)):
        if not applicable:
            continue  # e.g. coverage_gap needs a declared regression suite

        entry = audit_state.get_entry(repo_key, main_file).get(pass_name, {})
        last_commit = entry.get("last_audited_commit")

        if pass_name == "structural":
            # Structural pass is additionally gated on having at least one real
            # ledger ENTRY to check against - not merely a ledger file existing.
            # A scaffolded ledger with "entries": [] (a plausible interim state
            # before a first shape is confirmed) must report "not applicable",
            # the same as no ledger file at all.
            if not ledger_has_entries(repo_path, tool_key):
                continue
            lh = ledger_hash(repo_path, tool_key)
            prev_lh = entry.get("ledger_hash")
            if prev_lh is None:
                # First time this tool's ever been seen - establish the
                # baseline. Not itself a trigger (nothing to compare against
                # yet), but written now so the *next* run has one.
                audit_state.set_field(repo_key, main_file, pass_name, "ledger_hash", lh)
            elif prev_lh != lh:
                findings.append({
                    "repo": repo_key, "tool": tool_key, "pass": pass_name,
                    "reason": "ledger-growth",
                })
                # Deliberately do NOT overwrite the stored hash here. This
                # read-only hook never runs an audit - only the periodic-audit
                # skill itself, after a real pass actually completes, is
                # allowed to advance the recorded ledger_hash. Overwriting it
                # here would silently clear the crossed threshold on the very
                # next session even though nothing was ever audited.

        if last_commit is None:
            # Bootstrap: never audited before - fires regardless of commit threshold.
            findings.append({
                "repo": repo_key, "tool": tool_key, "pass": pass_name,
                "reason": "bootstrap",
            })
            continue

        args = ["log", "--oneline", f"{last_commit}..HEAD", "--", *files_to_track]
        result = git(repo_path, *args)
        if result is None or result.returncode != 0:
            # Unreachable SHA (e.g. a history-rewrite invalidated it) - treat as
            # never-audited, erring toward a false nudge over false-clean silence.
            findings.append({
                "repo": repo_key, "tool": tool_key, "pass": pass_name,
                "reason": "bootstrap (unreachable last_audited_commit)",
            })
            continue

        commit_count = len([ln for ln in result.stdout.splitlines() if ln.strip()])
        if commit_count >= threshold:
            findings.append({
                "repo": repo_key, "tool": tool_key, "pass": pass_name,
                "reason": f"file-commit-threshold ({commit_count} >= {threshold})",
            })

    return findings


def main():
    try:
        json.load(sys.stdin)  # drain stdin like the other bundled hooks; content unused
    except Exception:
        pass

    all_findings = []
    for repo_key, repo_path in REPOS.items():
        config_path = Path(repo_path) / ".claude" / "audit-config.json"
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue  # no registry for this repo yet - silent skip, by design

        for tool_key, cfg in (config.get("tools") or {}).items():
            all_findings.extend(check_tool(repo_key, repo_path, tool_key, cfg))

    if not all_findings:
        sys.exit(0)

    if CALIBRATION_MODE:
        CALIBRATION_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with CALIBRATION_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps({
                "at": datetime.now(timezone.utc).isoformat(),
                "would_have_fired": all_findings,
            }) + "\n")
        sys.exit(0)

    lines = [f"- {f['repo']}/{f['tool']} ({f['pass']}): {f['reason']}" for f in all_findings]
    message = "periodic-audit: due for a pass -\n" + "\n".join(lines)
    print(json.dumps({"systemMessage": message}))
    sys.exit(0)


if __name__ == "__main__":
    main()
