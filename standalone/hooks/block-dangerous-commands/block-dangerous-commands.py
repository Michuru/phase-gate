"""PreToolUse hook: hard-block a short list of catastrophic Bash commands,
regardless of permission mode -- a technical backstop for autonomous/auto
modes, where the soft confirm-first guidance in your rules doc gets skipped
by design. Scoped deliberately narrow (a short, reviewed list, not a general
policy engine): root-path rm -rf / PowerShell Remove-Item on a drive root,
force-push to main/master, and reset --hard / clean -f only when the target
tree actually has something to lose, plus a script passed through a Bash
heredoc. Optionally (off until you name a folder in protected-folders.json),
it also keeps Grep, Glob and shell searches out of folders you mark protected:
see protected_folder_guard.py beside this file and the README. Anything not
matched here still goes through Claude Code's normal permission-prompt flow --
this hook only ever adds a stricter floor, never loosens the default.

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
import importlib.util
import json
import os
import re
import subprocess
import sys

# The protected-folder engine is a module beside this file. Loaded by path, not through sys.path, so nothing else in this
# folder can shadow a module name. A load failure never stops the other rules below.
_pfg = None
_pfg_error = None
try:
    _spec = importlib.util.spec_from_file_location(
        "protected_folder_guard", os.path.join(os.path.dirname(os.path.abspath(__file__)), "protected_folder_guard.py"))
    _pfg = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_pfg)
except Exception as _e:
    _pfg = None
    _pfg_error = "%s: %s" % (type(_e).__name__, _e)


def _note_pfg_failure(text):
    global _pfg_error
    _pfg_error = text


try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)

tool_name = data.get("tool_name")
if tool_name not in ("Bash", "PowerShell", "Grep", "Glob"):
    sys.exit(0)

tool_input = data.get("tool_input") or {}
cwd = data.get("cwd") or ""
if tool_name in ("Grep", "Glob"):
    # The protected-folder check reads these fields as one text, and the Grep/Glob branch inside it reads them one by one.
    command = "\n".join(str(tool_input.get(k) or "") for k in ("path", "glob", "pattern"))
else:
    command = tool_input.get("command") or ""

if not command.strip():
    sys.exit(0)


def deny(reason):
    if _pfg_error and _pfg_error not in reason:
        reason += " (The protected-folder guard did not run: %s.)" % _pfg_error
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


# 0. The protected-folder guard (optional; off until protected-folders.json names a folder). The engine is
#    protected_folder_guard.py, which also holds the rules in full. It covers:
#      - any shell command, Grep or Glob call that names a protected folder (its name as a whole word, any separators)
#      - a search that starts at a directory above the folder (a drive root, an ancestor, your home directory) and
#        recurses: find, rg, tree, Get-ChildItem -Recurse, ls -R, os.walk, and the like
#      - the folder reached through a wildcard (C:\Users\me\Priv*), and drive aliases (subst, junctions) that point at a
#        directory above it
#    Text matching, so best-effort: it cannot see a path built at run time or the inside of a script file run by name.
#    Which folders: `--config <file>` on this hook's command line (a named file that is missing or broken denies), else
#    the default search described in protected_folder_guard.py. A user-level install should pass --config.


def _config_wanted():
    """True when you asked for the guard: a --config on this command, or a protected-folders.json in the default search
    places (the project's .claude folder, CLAUDE_CONFIG_DIR or ~/.claude). Used only when the module will not load, so a dead
    module never leaves a configured guard silently off."""
    if any(a == "--config" or a.startswith("--config=") for a in sys.argv[1:]):
        return True
    try:
        places = []
        if os.environ.get("CLAUDE_PROJECT_DIR"):
            places.append(os.path.join(os.environ["CLAUDE_PROJECT_DIR"], ".claude", "protected-folders.json"))
        places.append(os.path.join(os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude"),
                                   "protected-folders.json"))
        return any(os.path.isfile(p) for p in places)
    except Exception:
        return False


_NAMED_CONFIG = _config_wanted()
_FALLBACK_RECURSION = re.compile(
    r"(?i)(?<![\w.\-])(?:find|rg|fd|fdfind|tree|du|tar|7z|7za|rsync|robocopy|xcopy|ag|ack|locate|compress-archive)(?:\.exe)?(?![\w.\-])"
    r"|\s-(?=[a-z]*[rs])[a-z]{1,4}(?![\w\-])|\s-rec\w*|\s--recursive\b|\s/[srt](?![\w\-:])"      # -r -rn -lR -rf -s, -Recurse, /s /r /t
    r"|(?<![\w.\-])cp\s+(?:-[a-z]+\s+)*-[a-z]*a|\bshutil\.(?:copytree|make_archive)\b"
    r"|\bos\.walk\b|\brglob\b|\bwalk_files\b|\bget-childitem\b|\bgci\b")


def _protected_folder_reason():
    """The deny text from the protected-folder guard, or None. If the module cannot load or crashes: when you asked for the
    guard (a --config, or a protected-folders.json in the default search places) deny every Grep/Glob call and every
    statement that looks like a recursion; with no config anywhere the guard is off and the failure is reported in any deny
    this hook issues."""
    if _pfg is not None:
        try:
            return _pfg.evaluate(tool_name, tool_input, cwd, command, sys.argv[1:])
        except Exception as e:
            _note_pfg_failure("%s: %s" % (type(e).__name__, e))
    if not _NAMED_CONFIG:
        return None
    if tool_name in ("Grep", "Glob") or _FALLBACK_RECURSION.search(command):
        return ("Blocked: the protected-folder guard could not run (%s), so this Grep, Glob or recursive shell command is "
                "denied while the guard is down. Fix protected_folder_guard.py beside this hook, or run the command "
                "yourself." % _pfg_error)
    return None


_reason = _protected_folder_reason()
if _reason:
    deny(_reason)
if tool_name in ("Grep", "Glob"):
    sys.exit(0)

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

# Rule: a SCRIPT written through a Bash heredoc. A patch script passed to an interpreter
# (`python - <<'EOF'`, `node <<EOF`) or written to a code file (`cat > fix.py <<'EOF'`) can come back corrupted
# when its text holds a backslash (a `\n` inside a Python string becomes a real line break and the script dies
# with a SyntaxError; a doubled backslash is halved; an unquoted delimiter also lets the shell act on a backtick
# or a dollar sign). It happened repeatedly in the source repo even with the rule written in a notes file, so
# this hook enforces it instead.
# Denied (the original rule, "only with a backslash", was broken again twice in one session, so it was widened):
# any heredoc whose command line names an interpreter or redirects into a code file, whatever its body holds.
# The correct route is named in the message: a script file, or on Windows a PowerShell here-string piped to the
# interpreter, which passes backslashes through literally. Allowed: every other heredoc (commit messages, notes,
# markdown, JSON). Best-effort pattern matching like the rest of this file; it fails OPEN on any internal error.
HEREDOC_MSG = (
    "Blocked: a script passed through a Bash heredoc. These come back corrupted when the text holds a backslash (a "
    "backslash-n turns into a real line break, doubled backslashes are halved) and the failure is silent until the "
    "script runs. For an inline script on Windows use a PowerShell here-string piped to the interpreter (a "
    "single-quoted here-string, then `| python -`; backslashes pass through literally). For a script worth keeping, "
    "write it to a file with your editor/Write tool and run it from the file; for a one-line edit, your Edit tool. "
    "Heredocs for commit messages, notes, markdown and JSON are fine. If you truly need this exact command, run it "
    "yourself."
)
_HEREDOC = re.compile(r"<<-?[ \t]*(['\"]?)(\w+)\1([^\n]*)\n(.*?)\n[ \t]*\2[ \t]*(?:\n|$)", re.S)
# Not inside a file name (`git commit -F - -- tool.py` does not name the interpreter py); bash, sh, cmd and wsl count as
# interpreters too (`bash <<'EOF'` with a script in it).
_INTERPRETER = re.compile(r"(?<![\w.\-])(?:python3?|py|pythonw|node|nodejs|perl|ruby|pwsh|powershell|bash|sh|cmd|wsl)(?:\.exe)?\b", re.IGNORECASE)
_CODE_FILE_TARGET = re.compile(r">>?[ \t]*\S*\.(?:py|pyw|js|mjs|cjs|ts|ps1|psm1|sh|bat|cmd)\b", re.IGNORECASE)


def _has_a_heredoc_script_with_a_backslash(raw):
    for m in _HEREDOC.finditer(raw):
        line_start = raw.rfind("\n", 0, m.start()) + 1
        before = re.split(r"&&|\|\||[;|]", raw[line_start:m.start()])[-1]   # only the command that owns this heredoc
        command_line = before + m.group(3)
        if not (_INTERPRETER.search(command_line) or _CODE_FILE_TARGET.search(command_line)):
            continue
        return True   # any script through a Bash heredoc, backslash or not
    return False


try:
    _heredoc = _has_a_heredoc_script_with_a_backslash(command)
except Exception:
    _heredoc = False  # fail open
if _heredoc:
    deny(HEREDOC_MSG)

sys.exit(0)
