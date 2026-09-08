#!/usr/bin/env python
"""Deterministic classification for phase-gate-uninstall: reads an adopter's own
.claude/phase-gate-install/receipt.json (and, for the hook-reference check below, their real
.claude/settings.json) and reports, for every file the receipt has ever written, whether it's
safe to delete without a fresh model re-deriving the answer from prose each time.

Never reads the phase-gate clone - by design, an uninstall must work even if the clone that
originally installed this is long gone. Everything here comes from the adopter's own repo.

Classification per receipt-tracked file (components[].files_written and repo_files, across the
receipt's ENTIRE merge-forward history, not just the most recent run - the receipt's own arrays
already accumulate that):
  - "clean"            - live LF-normalized sha256 matches the receipt's recorded content_hash.
  - "locally_modified" - hash differs. Never silently deleted - the same "installed and locally
                         modified" policy Step 6 of phase-gate-install/SKILL.md already applies
                         to a refresh, applied here to a deletion instead.
  - "already_absent"   - the file doesn't exist. A no-op, not an error (crash-recovery safety:
                         a re-run after a partial prior deletion sees this and does nothing).

Every classified file also gets "hook_referenced": true/false - true if its own basename appears
as a substring of any "command" string in the adopter's CURRENT .claude/settings.json hooks. This
is what lets phase-gate-uninstall exclude a component's files from batch deletion when the
settings-merge tracking below is incomplete, without needing the original clone to know which
files a hook fragment invokes - the adopter's own live settings.json already says so.

settings_merge tracking status (see phase-gate-uninstall/SKILL.md for how each status is handled):
  - "nothing_to_reverse" - settings_merge.wrote_changes was false; no hooks/statusLine were ever
                            merged in, so there's nothing to unmerge at all.
  - "absent"              - the receipt predates hook_entries_written/status_line_written
                            entirely (an old-shaped receipt). Automatic settings.json reversal
                            is not attempted.
  - "incomplete"          - the fields are present but hook_entries_complete is not true (this
                            receipt was merge-forwarded at some point from one that lacked the
                            fields, so its history is only partially covered).
  - "complete"            - hook_entries_written/status_line_written cover the receipt's entire
                            settings-merge history; automatic unmerge is safe.

Exit codes: 0 = classification produced (even if the receipt has zero entries). 1 = a real error
(receipt missing, receipt not valid JSON, repo_root doesn't exist).
"""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path


def lf_normalized_sha256(path: Path) -> str:
    data = path.read_bytes()
    data = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return "sha256:" + hashlib.sha256(data).hexdigest()


def classify_file(repo_root: Path, rel_path: str, recorded_hash: str) -> str:
    full = repo_root / rel_path
    if not full.exists():
        return "already_absent"
    if lf_normalized_sha256(full) == recorded_hash:
        return "clean"
    return "locally_modified"


def collect_hook_commands(settings: dict) -> list:
    """Every "command" string across every event/matcher-group/hook entry in a settings.json's
    "hooks" key, ignoring anything malformed rather than raising - this is a best-effort signal,
    not a schema validator."""
    commands = []
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return commands
    for groups in hooks.values():
        if not isinstance(groups, list):
            continue
        for group in groups:
            if not isinstance(group, dict):
                continue
            for h in group.get("hooks", []):
                if isinstance(h, dict) and isinstance(h.get("command"), str):
                    commands.append(h["command"])
    return commands


def is_hook_referenced(rel_path: str, hook_commands: list) -> bool:
    basename = Path(rel_path).name
    return any(basename in cmd for cmd in hook_commands)


def read_core_hooks_path(repo_root: Path):
    """The actual current core.hooksPath value, read-only - never set or unset here. Returns None
    if unset, or if repo_root isn't a git repo / git isn't available (never raises)."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "config", "--get", "core.hooksPath"],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None


def build_plan(repo_root: Path, receipt: dict, settings: dict) -> dict:
    hook_commands = collect_hook_commands(settings)

    components_out = []
    for comp in receipt.get("components", []):
        files_out = []
        for f in comp.get("files_written", []):
            rel_path = f.get("path")
            status = classify_file(repo_root, rel_path, f.get("content_hash", ""))
            files_out.append({
                "path": rel_path,
                "status": status,
                "hook_referenced": is_hook_referenced(rel_path, hook_commands),
            })
        components_out.append({
            "name": comp.get("name"),
            "shelf": comp.get("shelf"),
            "files": files_out,
        })

    repo_files_out = []
    for f in receipt.get("repo_files", []):
        rel_path = f.get("path")
        status = classify_file(repo_root, rel_path, f.get("content_hash", ""))
        repo_files_out.append({
            "path": rel_path,
            "status": status,
            "hook_referenced": is_hook_referenced(rel_path, hook_commands),
        })

    # Paths phase-gate writes/copies that are never receipt-tracked (a README-instructed manual
    # bootstrap copy, or hook-written runtime state) - always surfaced, existence-only, since
    # there's no recorded hash to classify against.
    always_include_candidates = [
        ".claude/skills/phase-gate-install/SKILL.md",
        ".claude/skills/phase-gate-uninstall/SKILL.md",
        ".claude/state/context-usage-nudge.json",
        ".claude/state/update-notification.json",
    ]
    always_include_out = []
    for rel_path in always_include_candidates:
        full = repo_root / rel_path
        always_include_out.append({
            "path": rel_path,
            "status": "present" if full.exists() else "absent",
            "hook_referenced": is_hook_referenced(rel_path, hook_commands),
        })

    sm = receipt.get("settings_merge", {}) or {}
    if not sm.get("wrote_changes", False):
        tracking_status = "nothing_to_reverse"
    elif "hook_entries_written" not in sm and "status_line_written" not in sm:
        tracking_status = "absent"
    elif sm.get("hook_entries_complete") is True:
        tracking_status = "complete"
    else:
        tracking_status = "incomplete"

    return {
        "adopter_repo_root": str(repo_root),
        "components": components_out,
        "repo_files": repo_files_out,
        "always_include": always_include_out,
        "settings_merge": {
            "tracking_status": tracking_status,
            "hook_entries_written": sm.get("hook_entries_written", []),
            "status_line_written": sm.get("status_line_written"),
        },
        "core_hooks_path": {
            "value": read_core_hooks_path(repo_root),
            "note": "phase-gate never sets core.hooksPath itself (README's Install step has the "
                    "adopter run this by hand) - report the current value only, never modify it.",
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("repo_root", type=Path, help="The adopter repo's root directory.")
    parser.add_argument("--receipt", type=Path, default=None, help="Override receipt.json path (default: <repo_root>/.claude/phase-gate-install/receipt.json).")
    parser.add_argument("--settings", type=Path, default=None, help="Override settings.json path (default: <repo_root>/.claude/settings.json).")
    parser.add_argument("--out", type=Path, default=None, help="Write JSON here instead of stdout.")
    args = parser.parse_args()

    repo_root = args.repo_root
    if not repo_root.exists():
        print(f"[uninstall_plan] ERROR: repo_root {repo_root} does not exist.", file=sys.stderr)
        sys.exit(1)

    receipt_path = args.receipt or (repo_root / ".claude" / "phase-gate-install" / "receipt.json")
    if not receipt_path.exists():
        print(f"[uninstall_plan] ERROR: no receipt found at {receipt_path} - nothing to uninstall.", file=sys.stderr)
        sys.exit(1)
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"[uninstall_plan] ERROR: {receipt_path} is not valid JSON: {e}", file=sys.stderr)
        sys.exit(1)

    settings_path = args.settings or (repo_root / ".claude" / "settings.json")
    settings = {}
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            settings = {}

    plan = build_plan(repo_root, receipt, settings)
    output = json.dumps(plan, indent=2, sort_keys=True) + "\n"

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(output, encoding="utf-8")
        print(f"[uninstall_plan] Wrote plan to {args.out}")
    else:
        print(output)

    sys.exit(0)


if __name__ == "__main__":
    main()
