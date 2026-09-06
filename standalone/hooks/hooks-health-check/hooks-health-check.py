"""SessionStart hook: verify core.hooksPath is actually wired up in whichever
repo this session started in, and that the git hooks it points to are
tracked with git's executable mode bit set. Exists because core.hooksPath is
easy to lose silently -- a repo restructure, a fresh clone, a git filter-repo
run -- and the failure has no symptom of its own until something else
surfaces it. This catches that failure class at session start instead of by
accident. Reports via systemMessage only; never blocks anything.
"""
import json
import subprocess
import sys

# ---------------------------------------------------------------------------
# CONFIGURE ME
# ---------------------------------------------------------------------------
# EXPECTED_HOOKS_PATH is the core.hooksPath value your repo expects (relative,
# so it survives being cloned to any location). REQUIRED_HOOK_FILES are the
# filenames (relative to that path) that must be present and tracked.
#
# Defaults below match this export's own .githooks/ convention. Change them
# if your repo uses a different hooks directory or a different set of files.
# ---------------------------------------------------------------------------
EXPECTED_HOOKS_PATH = ".githooks"
REQUIRED_HOOK_FILES = ("pre-commit", "pre-push", "scan-secrets.sh")

try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)

cwd = data.get("cwd") or (data.get("workspace") or {}).get("current_dir") or ""
if not cwd:
    sys.exit(0)


def git(*args, root=None):
    try:
        return subprocess.run(
            ["git", "-C", root or cwd, *args],
            capture_output=True, text=True, timeout=5,
        )
    except Exception:
        return None


toplevel = git("rev-parse", "--show-toplevel")
if not toplevel or toplevel.returncode != 0:
    sys.exit(0)  # not a git repo -- nothing to check

problems = []

hooks_path_result = git("config", "--get", "core.hooksPath")
configured = hooks_path_result.stdout.strip() if hooks_path_result and hooks_path_result.returncode == 0 else ""
if configured != EXPECTED_HOOKS_PATH:
    problems.append(
        f"core.hooksPath is {configured!r}, expected {EXPECTED_HOOKS_PATH!r} -- "
        f"run `git config core.hooksPath {EXPECTED_HOOKS_PATH}` (doesn't survive a fresh clone or a git filter-repo run)"
    )
else:
    # core.fileMode is commonly false on Windows/NTFS, where there's no real
    # POSIX executable bit to track -- the check below reads it live rather
    # than assuming, and only enforces the exec-bit check when core.fileMode
    # is actually true.
    filemode_result = git("config", "--get", "core.fileMode")
    filemode = filemode_result.stdout.strip() if filemode_result and filemode_result.returncode == 0 else ""
    check_exec_bit = filemode == "true"

    for name in REQUIRED_HOOK_FILES:
        # Pathspec is relative to the repo root, not wherever the session started - resolve it
        # against `toplevel`, not `cwd`, or this silently reports "missing" for any session
        # started in a subdirectory even though the hook is tracked correctly.
        staged = git("ls-files", "--stage", f"{EXPECTED_HOOKS_PATH}/{name}", root=toplevel.stdout.strip())
        out = staged.stdout.strip() if staged and staged.returncode == 0 else ""
        if not out:
            problems.append(
                f"{EXPECTED_HOOKS_PATH}/{name} is missing from the index -- "
                f"run `git add {EXPECTED_HOOKS_PATH}/{name}` and commit it"
            )
        elif check_exec_bit and not out.startswith("100755"):
            problems.append(f"{EXPECTED_HOOKS_PATH}/{name} is tracked without the executable bit ({out.split()[0]})")

if problems:
    message = "Hooks health check found issues:\n- " + "\n- ".join(problems)
    print(json.dumps({"systemMessage": message}))

sys.exit(0)
