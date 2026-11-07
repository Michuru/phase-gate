"""SessionStart hook: verify core.hooksPath is actually wired up in whichever
repo this session started in, and that the git hooks it points to are
tracked with git's executable mode bit set. Exists because core.hooksPath is
easy to lose silently -- a repo restructure, a fresh clone, a git filter-repo
run -- and the failure has no symptom of its own until something else
surfaces it. This catches that failure class at session start instead of by
accident. Reports via systemMessage (shown to you) and additionalContext (shown to the model, which
matters because a drifted core.hooksPath means its own commits skip the secret guard); never blocks
anything.

It also checks the protected-folder guard's config when that guard (block-dangerous-commands) is installed beside it, and
`--report` prints a summary of that config by hand; see the README.
"""
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

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
# PROTECTED_FOLDERS_CONFIG is optional, and only matters if you installed the protected-folder guard (the
# block-dangerous-commands hook) beside this hook. If that hook's command names its config with `--config <file>`, name the
# same file here (or put the same `--config <file>` on this hook's own command line, which wins over this constant), so this
# check reads the file the guard reads. Use an ABSOLUTE path with forward slashes, such as
# "C:/Users/you/.claude/protected-folders.json" (a backslash path in a normal Python string is a syntax error that stops this
# whole hook); `~` and `$HOME` are expanded. Leave it empty and the check uses the guard's default search (the project's
# .claude folder, then CLAUDE_CONFIG_DIR or ~/.claude). With the guard absent, or no config file found, the guard is off and
# this check says nothing.
PROTECTED_FOLDERS_CONFIG = ""

REPORT = "--report" in sys.argv[1:]      # run by hand: print the protected-folders summary and exit (no payload needed)


def _config_file():
    """The config file to read, or "" for the guard's default search: `--config <file>` (or `--config=<file>`) on THIS hook's
    command line wins, so the same argument as the guard's own command can be pasted here; otherwise the constant above.
    `~` and `$HOME` are expanded, as the shell does for the guard's own command."""
    value = PROTECTED_FOLDERS_CONFIG
    args = sys.argv[1:]
    for i, a in enumerate(args):
        if a == "--config" and i + 1 < len(args):
            value = args[i + 1]
            break
        if a.startswith("--config="):
            value = a[len("--config="):]
            break
    return os.path.expanduser(os.path.expandvars(value)) if value else ""


def _project_dir_guess():
    """For a hand-run `--report` (no session, so no CLAUDE_PROJECT_DIR): the git top level of the current folder, else the
    current folder, so a project-level protected-folders.json is found as the hook would find it."""
    try:
        r = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=5)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except Exception:
        pass
    return os.getcwd()


def _load_protected():
    """(folders or None, problem, missing optional paths, counts available, error): what the guard's own loader says about the
    config, so the checks are exactly the ones the hook makes. (None, None, [], False, None) means the guard is not installed
    beside this hook."""
    guard_file = Path(os.path.abspath(__file__)).parent / "protected_folder_guard.py"
    if not guard_file.is_file():
        return None, None, [], False, None
    try:
        spec = importlib.util.spec_from_file_location("protected_folder_guard", guard_file)
        guard = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(guard)
        config = _config_file()
        argv = ["--config", config] if config else []
        env = None
        if REPORT and not os.environ.get("CLAUDE_PROJECT_DIR"):
            env = dict(os.environ, CLAUDE_PROJECT_DIR=_project_dir_guess())
        if hasattr(guard, "load_folders_ex"):
            folders, problem, missing = guard.load_folders_ex(argv, env)
            return folders, problem, missing, True, None
        folders, problem = guard.load_folders(argv, env)       # a guard from before optional entries: counts unavailable
        return folders, problem, [], False, None
    except (Exception, SystemExit) as e:
        return None, None, [], False, "the protected-folder guard could not be checked (%s: %s)" % (type(e).__name__, e)


_BROKEN = ("protected-folders config problem: %s -- the protected-folder guard denies every Grep/Glob call and every "
           "recursive shell command until it is fixed")


def protected_folders_problems():
    """Report-only, at session start: a missing or broken protected-folders config (or a required entry that is gone) means
    the guard denies every Grep and Glob call and every recursive shell command until it is fixed, so say so. A missing
    OPTIONAL entry is not a problem (it still protects by name) and is shown only by `--report`."""
    folders, problem, missing, counts, error = _load_protected()
    if error:
        return [error]
    return [_BROKEN % problem] if problem else []


def protected_folders_report():
    """Lines for `python hooks-health-check.py --report`: the entries by mode and which optional entries are missing."""
    folders, problem, missing, counts, error = _load_protected()
    if error:
        return [error]
    if folders is None:
        return ["protected-folders: the protected-folder guard is not installed beside this hook"]
    if problem:
        return [_BROKEN % problem]
    if not folders:
        return ["protected-folders: no protected folder is configured (the guard is off)"]
    if not counts:
        return ["protected-folders: the guard is from before optional entries; counts and missing optional entries are "
                "unavailable"]
    lines = ["protected-folders entries: %s" % entry_counts(folders)]
    if missing:
        lines.append("%d optional entr%s missing on disk (still protected by name; check a path is not a typo or a renamed "
                     "folder): %s" % (len(missing), "y is" if len(missing) == 1 else "ies are", "; ".join(missing)))
    else:
        lines.append("no optional entry is missing")
    return lines


def entry_counts(folders):
    """The config's entries by mode, as text. "plain" counts every entry whose tail is 1 (a string entry, or an object entry with
    no tail: an object entry is scoped, so its ancestors stop at its own parent, unlike a string entry); "path-qualified" counts
    tail above 1; "optional" counts the entries marked optional, whatever their tail."""
    total = len(folders)
    qualified = sum(1 for f in folders if f.tail > 1)
    optional = sum(1 for f in folders if f.optional)
    return "%d total, %d plain, %d path-qualified, %d optional" % (total, total - qualified, qualified, optional)


def emit(problems):
    if not problems:
        return
    message = "Hooks health check found issues:\n- " + "\n- ".join(problems)
    # systemMessage is shown to the user only; additionalContext is what reaches the model
    print(json.dumps({
        "systemMessage": message,
        "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": message},
    }))


if REPORT:
    print("\n".join(protected_folders_report()))
    sys.exit(0)

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
    emit(protected_folders_problems())
    sys.exit(0)  # not a git repo -- no git hooks to check

problems = protected_folders_problems()

hooks_path_result = git("config", "--get", "core.hooksPath")
configured = hooks_path_result.stdout.strip() if hooks_path_result and hooks_path_result.returncode == 0 else ""


def _is_expected_hooks_path(value: str) -> bool:
    """`hooks`, or an absolute path (any slash style, any case) that is this repo's own hooks folder."""
    if not value:
        return False
    if value == EXPECTED_HOOKS_PATH:
        return True
    try:
        top = Path(toplevel.stdout.strip())
        want = os.path.normcase(os.path.realpath(top / EXPECTED_HOOKS_PATH))
        got = os.path.normcase(os.path.realpath(top / value))   # an absolute `value` replaces `top`
    except Exception:
        return False
    return got == want


if not _is_expected_hooks_path(configured):
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

emit(problems)

sys.exit(0)
