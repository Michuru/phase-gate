"""PreToolUse hook: hard-block a short list of catastrophic Bash commands,
regardless of permission mode -- a technical backstop for autonomous/auto
modes, where the soft confirm-first guidance in your rules doc gets skipped
by design. Scoped deliberately narrow (a short, reviewed list, not a general
policy engine): root-path rm -rf / PowerShell Remove-Item on a drive root,
force-push to main/master, and reset --hard / clean -f only when the target
tree actually has something to lose. Anything not matched here still goes
through Claude Code's normal permission-prompt flow -- this hook only ever
adds a stricter floor, never loosens the default.

If your Bash tool is configured to route through PowerShell
(CLAUDE_CODE_USE_POWERSHELL_TOOL), both POSIX and PowerShell command shapes
are checked, so this hook works the same way on that setup as on a plain
POSIX shell.

Pattern-matched on the raw command string, not a real shell parser --
best-effort, same shape-over-exhaustiveness philosophy as a secret-shape
scanner, not a guarantee against a deliberately obfuscated command.

JSON contract: code.claude.com/docs/en/hooks.md -- exit 0 with
{"hookSpecificOutput": {"permissionDecision": "deny", ...}} on stdout blocks
the call; exit 0 with no output lets normal permission flow proceed.
"""
import json
import re
import subprocess
import sys

try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)

if data.get("tool_name") != "Bash":
    sys.exit(0)

command = (data.get("tool_input") or {}).get("command") or ""
cwd = data.get("cwd") or ""

if not command.strip():
    sys.exit(0)


def deny(reason):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))
    sys.exit(0)


def run_git(*args):
    if not cwd:
        return None
    try:
        return subprocess.run(
            ["git", "-C", cwd, *args],
            capture_output=True, text=True, timeout=5,
        )
    except Exception:
        return None


def is_dirty():
    """True (fail toward caution) when the tree has uncommitted changes,
    isn't a git repo we could check, or the check itself failed."""
    result = run_git("status", "--porcelain")
    if result is None:
        return True
    if result.returncode != 0:
        return False  # not a git repo here -- nothing tracked to lose
    return bool(result.stdout.strip())


def clean_would_remove(flags):
    result = run_git("clean", f"-{flags}n")
    if result is None:
        return True
    if result.returncode != 0:
        return False
    return bool(result.stdout.strip())


# 1. rm -rf (or PowerShell Remove-Item -Recurse -Force) targeting a bare
#    filesystem root -- POSIX "/", a drive letter root ("C:\", "C:/"), or
#    the git-bash MSYS root form ("/c", "/c/"). Deliberately NOT matched
#    against any deeper path (e.g. "/c/Users/...") to avoid blocking
#    ordinary subdirectory deletions.
ROOT_PATH = r"(?:/|/\*|[A-Za-z]:[\\/]?|/[A-Za-z]/?)"
if re.search(rf"\brm\s+(?:-[a-zA-Z]*[rf][a-zA-Z]*\s+)+['\"]?{ROOT_PATH}['\"]?(?:\s|$)", command):
    deny("Blocked: rm -rf targeting a filesystem root. Run manually outside Claude Code if this was intentional.")

if re.search(
    # The path token must be preceded by whitespace (or immediately follow a quote that itself
    # follows whitespace) - without this, the bare "/" alternative inside ROOT_PATH matches the
    # trailing slash of ANY directory argument ("build/", "./", "node_modules/"), since an
    # unanchored ".*" happily consumes everything up to that slash. Confirmed false-positive
    # class in review: ordinary "Remove-Item -Recurse -Force build/" was denying before this fix.
    rf"\bRemove-Item\b(?=.*-Recurse\b)(?=.*-Force\b).*\s['\"]?{ROOT_PATH}['\"]?(?:\s|$)",
    command, re.IGNORECASE,
):
    deny("Blocked: Remove-Item -Recurse -Force targeting a filesystem root. Run manually outside Claude Code if this was intentional.")

# 2. git push --force / -f / --force-with-lease targeting main/master, or a
#    bare force-push (no explicit remote+branch) while HEAD is already on
#    main/master. main/master are checked as a blunt, literal safety
#    heuristic against the two overwhelmingly common default-branch names --
#    this is deliberately not tied to whatever your repo's actual default
#    branch is named; add your own branch name below if it differs.
force_push = re.search(r"\bgit\s+push\b.*(?:--force(?:-with-lease)?\b|(?<!\S)-f\b)", command)
if force_push:
    explicit_main = re.search(r"\bgit\s+push\b.*\b(?:origin\s+)?(?:main|master)\b", command)
    has_explicit_target = re.search(r"\bgit\s+push\b.*\S+\s+\S+", command)
    if explicit_main:
        deny("Blocked: force-push targeting main/master. Confirm with the user and run manually if intended.")
    elif not has_explicit_target:
        branch = run_git("rev-parse", "--abbrev-ref", "HEAD")
        if branch and branch.returncode == 0 and branch.stdout.strip() in ("main", "master"):
            deny("Blocked: force-push with no explicit branch while on main/master. Confirm with the user and run manually if intended.")

# 3. git reset --hard -- only when the tree actually has something to lose.
if re.search(r"\bgit\s+reset\s+--hard\b", command) and is_dirty():
    deny("Blocked: git reset --hard would discard uncommitted changes. Run `git status` and stash/commit first, or confirm with the user.")

# 4. git clean -f[d...] -- only when a dry run shows it would remove something.
clean_match = re.search(r"\bgit\s+clean\s+(-[a-zA-Z]*f[a-zA-Z]*)\b", command)
if clean_match:
    flags = clean_match.group(1).lstrip("-").replace("n", "") + "n"
    if clean_would_remove(flags):
        deny("Blocked: git clean would remove untracked files. Run `git clean -fdn` to preview, or confirm with the user.")

sys.exit(0)
