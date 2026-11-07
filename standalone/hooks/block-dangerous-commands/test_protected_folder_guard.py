"""Tests for the protected-folder guard (protected_folder_guard.py, called from block-dangerous-commands.py) and for the
hook's other portable rules (1 to 4 and 6). This file ships with the guard: it uses a fake folder in a temp directory and a temp
config, never a real folder of yours, and runs the real hook as a subprocess, the way Claude Code does.

Run:  python -m pytest test_protected_folder_guard.py -q      (from the folder that holds the hook)
      python3 -m pytest test_protected_folder_guard.py -q     (the POSIX forms run on Linux, macOS and WSL)

The fake folder sits two levels below a fake home directory, `<tmp>/home/work/Private Notes`, so the directories above it
are a drive or filesystem root, the temp path, `home`, `work` and, through `~`, the home directory itself.
"""
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import types
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parent / "block-dangerous-commands.py"
MODULE = HOOK.with_name("protected_folder_guard.py")
WIN = os.name == "nt"
NL = chr(10)
BS = chr(92)
PS, BASH = "PowerShell", "Bash"
FOLDER_NAME = "Private Notes"

windows_only = pytest.mark.skipif(not WIN, reason="Windows path forms")
posix_only = pytest.mark.skipif(WIN, reason="POSIX path forms (run under Linux, macOS or WSL)")


# ---------------------------------------------------------------- the harness

_EMPTY_HOME = {}


@pytest.fixture(autouse=True, scope="session")
def _empty_home(tmp_path_factory):
    """Every hook run gets a home directory with no .claude folder in it unless a test sets HOME itself, so the default
    config search never reads a real one."""
    _EMPTY_HOME["dir"] = str(tmp_path_factory.mktemp("emptyhome"))


def _clean_env(extra=None):
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_PROJECT_DIR", "CLAUDE_CONFIG_DIR", "BDC_TEST_RAISE")}
    if _EMPTY_HOME:
        env["HOME"] = env["USERPROFILE"] = _EMPTY_HOME["dir"]
    env.update(extra or {})
    return env


def run_hook(tool, command="", cfg=None, cwd=None, tool_input=None, env=None, extra_args=(), hook=HOOK):
    """Run the hook once. Returns the deny text, or None when the call is let through."""
    ti = tool_input if tool_input is not None else {"command": command}
    payload = json.dumps({"tool_name": tool, "tool_input": ti, "cwd": cwd if cwd is not None else str(hook.parent)})
    args = [sys.executable, str(hook)] + (["--config", str(cfg)] if cfg is not None else []) + list(extra_args)
    res = subprocess.run(args, input=payload, capture_output=True, text=True, timeout=60, env=_clean_env(env))
    assert res.returncode == 0, res.stderr
    if not res.stdout.strip():
        return None
    out = json.loads(res.stdout)["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny"
    return out["permissionDecisionReason"]


def write_cfg(path, folders):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"protected_folders": [str(f) for f in folders]}), encoding="utf-8")
    return path


@pytest.fixture(params=["pytest-tmp", "local-app-temp"])
def fake(request, tmp_path):
    """The fake folder tree, once under pytest's temp directory and, on Windows, once more under %LOCALAPPDATA%\\Temp
    (usually on C:, a drive whose letter is also a cmd and findstr switch) when that is a different drive."""
    if request.param == "local-app-temp":
        root = os.environ.get("LOCALAPPDATA")
        if not WIN or not root or not os.path.isdir(os.path.join(root, "Temp")):
            pytest.skip("no second temp location")
        if os.path.splitdrive(os.path.join(root, "Temp"))[0].lower() == os.path.splitdrive(str(tmp_path))[0].lower():
            pytest.skip("the same drive as pytest's temp directory")
        tmp_path = Path(tempfile.mkdtemp(prefix="pfg-", dir=os.path.join(root, "Temp")))
        request.addfinalizer(lambda: shutil.rmtree(str(tmp_path), ignore_errors=True))
    home = tmp_path / "home"
    work = home / "work"
    folder = work / FOLDER_NAME
    folder.mkdir(parents=True)
    (work / "Public").mkdir()
    (home / "other").mkdir()
    (tmp_path / "elsewhere").mkdir()
    cfg = write_cfg(tmp_path / "cfg" / "protected-folders.json", [folder])
    return types.SimpleNamespace(
        tmp=tmp_path, home=home, work=work, folder=folder, other=home / "other", elsewhere=tmp_path / "elsewhere", cfg=cfg,
        env={"HOME": str(home), "USERPROFILE": str(home)},
        letter=(os.path.splitdrive(str(tmp_path))[0][:1].lower() if WIN else ""))


def msys(path):
    """C:\\Users\\me -> /c/Users/me"""
    drive, rest = os.path.splitdrive(str(path))
    return "/" + drive[:1].lower() + rest.replace("\\", "/")


def grep_tool(fake, path=None, cwd=None, pattern="notes"):
    ti = {"pattern": pattern, "output_mode": "files_with_matches"}
    if path is not None:
        ti["path"] = str(path)
    return run_hook("Grep", cfg=fake.cfg, cwd=cwd, tool_input=ti, env=fake.env)


def glob_tool(fake, pattern, path=None, cwd=None):
    ti = {"pattern": pattern}
    if path is not None:
        ti["path"] = str(path)
    return run_hook("Glob", cfg=fake.cfg, cwd=cwd, tool_input=ti, env=fake.env)


# ---------------------------------------------------------------- Windows forms

@windows_only
def test_windows_recursion_above_the_folder_is_denied(fake):
    drive = os.path.splitdrive(str(fake.tmp))[0]
    cases = [
        (PS, "Get-ChildItem %s -Recurse -Filter *.md" % fake.work),
        (PS, "Get-ChildItem %s -Recurse" % fake.home),
        (PS, "Get-ChildItem %s -Recurse" % fake.tmp),
        (PS, "Get-ChildItem %s%s -Recurse" % (drive, BS)),
        (PS, "gci %s -r" % drive),
        (PS, "dir %s /s /b" % fake.home),
        (BASH, "rg foo %s" % fake.work.as_posix()),
        (BASH, "grep -rn foo %s/" % fake.home.as_posix()),
        (BASH, "find %s -name x" % msys(fake.work)),
        (BASH, "find %s -name x" % ("/" + fake.letter)),
        (BASH, "ls -R /mnt/%s" % fake.letter),
        (BASH, "find /cygdrive/%s -name x" % fake.letter),
        (PS, 'powershell -Command "Get-ChildItem %s -Recurse"' % fake.home),
        (PS, "cmd /c dir %s /s /b" % fake.home),
        (PS, "Compress-Archive %s x.zip" % fake.work),
        (PS, "robocopy %s X:%sdump /e" % (fake.work, BS)),
    ]
    for tool, cmd in cases:
        reason = run_hook(tool, cmd, cfg=fake.cfg, env=fake.env)
        assert reason is not None, "not denied: " + cmd
        assert "drive root" in reason or str(fake.work) in reason or "searches recursively" in reason


@windows_only
def test_windows_recursion_beside_or_below_the_folder_stays_allowed(fake):
    drive = os.path.splitdrive(str(fake.tmp))[0]
    cases = [
        (PS, "Get-ChildItem %s -Recurse" % fake.other),
        (PS, "Get-ChildItem %s%sPublic -Recurse" % (fake.work, BS)),
        (PS, "Get-ChildItem %s%s -Directory" % (drive, BS)),
        (PS, "Get-ChildItem %s -Directory | ConvertTo-Json -Depth 2" % fake.home),
        (PS, "Get-ChildItem %s" % fake.work),
        (PS, "Test-Path %s%s" % (drive, BS)),
        (BASH, "rg foo %s" % fake.other.as_posix()),
        (BASH, "find %s -name x" % msys(fake.other)),
        (BASH, "find %s -maxdepth 1 -name x" % msys(fake.work)),
        (BASH, "git status"),
        (PS, "robocopy %s %s /e /j" % (fake.other, fake.elsewhere)),
        (PS, "New-PSDrive -Name M -Root %s -PSProvider FileSystem" % fake.other),
    ]
    for tool, cmd in cases:
        assert run_hook(tool, cmd, cfg=fake.cfg, env=fake.env) is None, "wrongly denied: " + cmd


@windows_only
def test_windows_the_folder_by_name_or_by_wildcard_is_denied(fake):
    cases = [
        (PS, "Get-Content '%s%sa.txt'" % (fake.folder, BS)),
        (PS, 'type "%s"' % FOLDER_NAME),
        (PS, "Get-ChildItem %s%sPriv*" % (fake.work, BS)),
        (PS, "Get-ChildItem %s%s*Notes" % (fake.work, BS)),
        (PS, "Get-ChildItem %s%sw*%sPriv*" % (fake.home, BS, BS)),
        (BASH, "ls %s/{Pri,X}*" % fake.work.as_posix()),
        (BASH, "cat %s/Priv*/x.txt" % msys(fake.work)),
        (PS, "Get-ChildItem %s%s..%swork%sPriv*" % (fake.other, BS, BS, BS)),
        (PS, "echo %s" % FOLDER_NAME.replace(" ", "_")),
        (PS, "git commit -m 'adds the private notes archive'"),
    ]
    for tool, cmd in cases:
        assert run_hook(tool, cmd, cfg=fake.cfg, env=fake.env) is not None, "not denied: " + cmd


@windows_only
def test_windows_drive_aliases_and_encoded_commands(fake):
    assert run_hook(PS, "subst X: %s" % fake.work, cfg=fake.cfg, env=fake.env) is not None
    assert run_hook(PS, "New-Item -ItemType Junction -Path C:%sx -Target %s" % (BS, fake.home), cfg=fake.cfg, env=fake.env) is not None
    assert run_hook(PS, "subst X: %s%sPublic" % (fake.work, BS), cfg=fake.cfg, env=fake.env) is None
    assert run_hook(PS, "powershell -NoProfile -EncodedCommand SQBtAHAAbwByAHQALQBNAG8AZAB1AGwAZQA=", cfg=fake.cfg, env=fake.env) is not None


@windows_only
def test_windows_home_forms_resolve_to_the_real_home_directory(fake):
    # the fake folder sits under the fake home, so the home directory is a directory above it
    for tool, cmd in [(BASH, "rg foo ~"), (BASH, "rg foo ~/"), (BASH, "rg foo $HOME"), (PS, "Get-ChildItem ~ -Recurse"),
                      (PS, "Get-ChildItem $env:USERPROFILE -Recurse"), (PS, "Get-ChildItem %USERPROFILE% -Recurse"),
                      (BASH, "find ~/work -name x"), (BASH, "find ~ -name x"), (BASH, "find ~/%s%s -name x" % ("../" * len(fake.home.parts), fake.letter)),     # up past the drive letter, to the MSYS root, and down to the drive again
                      (PS, "Get-ChildItem ~%swork -Recurse" % BS)]:
        assert run_hook(tool, cmd, cfg=fake.cfg, env=fake.env) is not None, "not denied: " + cmd
    for tool, cmd in [(BASH, "rg foo ~/other"), (PS, "Get-ChildItem ~/other -Recurse"), (BASH, "ls ~")]:
        assert run_hook(tool, cmd, cfg=fake.cfg, env=fake.env) is None, "wrongly denied: " + cmd


@windows_only
def test_windows_a_working_directory_above_the_folder_counts_when_no_path_is_named(fake):
    assert run_hook(BASH, "rg foo", cfg=fake.cfg, cwd=str(fake.work), env=fake.env) is not None
    assert run_hook(PS, "Get-ChildItem -Recurse", cfg=fake.cfg, cwd=str(fake.home), env=fake.env) is not None
    assert run_hook(PS, "Get-ChildItem -Recurse", cfg=fake.cfg, cwd=str(fake.tmp), env=fake.env) is not None
    assert run_hook(BASH, "rg foo", cfg=fake.cfg, cwd=str(fake.other), env=fake.env) is None
    assert run_hook(PS, "Get-ChildItem -Recurse", cfg=fake.cfg, cwd=str(fake.work / "Public"), env=fake.env) is None
    assert run_hook(PS, "Get-ChildItem .. -Recurse", cfg=fake.cfg, cwd=str(fake.work / "Public"), env=fake.env) is not None
    assert run_hook(PS, "cd %s; Get-ChildItem -Recurse" % fake.work, cfg=fake.cfg, cwd=str(fake.elsewhere), env=fake.env) is not None


@windows_only
def test_windows_a_drive_letter_is_not_read_out_of_cmd_and_findstr_switches(fake):
    """With C: above the folder, `/c` after cmd and `/c:` in findstr are switches, not the MSYS form of the C: drive."""
    if fake.letter not in ("c", "k"):
        pytest.skip("the fake folder is not on a drive whose letter is also a cmd switch")
    other = str(fake.other)
    cmd = "cmd /%s dir /s x.txt" % fake.letter if fake.letter == "c" else "cmd /k dir x.txt"
    assert run_hook(PS, cmd, cfg=fake.cfg, cwd=other, env=fake.env) is None
    if fake.letter == "c":
        assert run_hook(PS, 'findstr /s /c:"hello" *.txt', cfg=fake.cfg, cwd=other, env=fake.env) is None
    # and the real thing is still denied
    assert run_hook(PS, "cmd /c dir %s /s" % fake.home, cfg=fake.cfg, cwd=other, env=fake.env) is not None


@windows_only
def test_windows_grep_and_glob_tools(fake):
    assert grep_tool(fake, path=fake.work) is not None
    assert grep_tool(fake, path=fake.home) is not None
    assert grep_tool(fake, path=fake.tmp) is not None
    assert grep_tool(fake, path=fake.other) is None
    assert grep_tool(fake, path=fake.work / "Public") is None
    assert grep_tool(fake, cwd=str(fake.work)) is not None                     # no path: it searches the cwd
    assert grep_tool(fake, cwd=str(fake.other)) is None
    assert grep_tool(fake, path="%s%sPriv*" % (fake.work, BS), pattern="x") is not None
    assert glob_tool(fake, "**/*.md", path=fake.work) is not None
    assert glob_tool(fake, "**/*.md", path=fake.home) is not None
    assert glob_tool(fake, "Priv*/*.md", path=fake.work) is not None
    assert glob_tool(fake, "*.md", path=fake.work) is None                     # one level, cannot match the folder
    assert glob_tool(fake, "**/*.md", path=fake.other) is None
    assert glob_tool(fake, "Public/**", path=fake.work) is None
    assert glob_tool(fake, "../**", path=fake.work / "Public") is not None     # '..' resolved against the path
    assert glob_tool(fake, "%s/**/*.md" % fake.work.as_posix()) is not None
    assert grep_tool(fake, path=fake.other, pattern="private notes") is not None   # rule 0 reads the pattern too


# ---------------------------------------------------------------- POSIX forms

@posix_only
def test_posix_recursion_above_the_folder_is_denied(fake):
    cases = [
        (BASH, "find %s -name x" % fake.work),
        (BASH, "find %s -name x" % fake.home),
        (BASH, "find %s -name x" % fake.tmp),
        (BASH, "find / -name x"),
        (BASH, "ls -R /"),
        (BASH, "rg foo %s/" % fake.home),
        (BASH, "grep -rn foo %s" % fake.work),
        (BASH, "tar czf x.tgz %s" % fake.home),
        (BASH, "cp -r %s /tmp/dump" % fake.work),
        (BASH, "bash -c 'find %s -name x'" % fake.home),
        (BASH, "rg foo ~"), (BASH, "find ~ -name x"), (BASH, "rg foo $HOME"), (BASH, "find ~/work -name x"),
        (BASH, "find %s/../.. -name x" % fake.other),
        (BASH, "echo %s | xargs find" % fake.home),
    ]
    for tool, cmd in cases:
        assert run_hook(tool, cmd, cfg=fake.cfg, env=fake.env) is not None, "not denied: " + cmd


@posix_only
def test_posix_recursion_beside_or_below_the_folder_stays_allowed(fake):
    cases = [
        (BASH, "find %s -name x" % fake.other),
        (BASH, "find %s/Public -name x" % fake.work),
        (BASH, "ls /"), (BASH, "ls -la %s" % fake.work), (BASH, "ls ~"),
        (BASH, "find /usr -maxdepth 1 -name x"),
        (BASH, "find %s -maxdepth 1 -name x" % fake.work),
        (BASH, "rg foo ~/other"),
        (BASH, "git status"),
    ]
    for tool, cmd in cases:
        assert run_hook(tool, cmd, cfg=fake.cfg, env=fake.env) is None, "wrongly denied: " + cmd


@posix_only
def test_posix_the_folder_by_name_or_wildcard_is_denied(fake):
    for cmd in ["cat '%s/a.txt'" % fake.folder, "cat %s/Priv*/a.txt" % fake.work, "ls %s/{Pri,X}*" % fake.work,
                "ls %s/*Notes" % fake.work, "ls ~/w*/Priv*", "echo private_notes", "ls %s/other/../work/Priv*" % fake.home]:
        assert run_hook(BASH, cmd, cfg=fake.cfg, env=fake.env) is not None, "not denied: " + cmd


@posix_only
def test_posix_working_directory_and_tools(fake):
    assert run_hook(BASH, "rg foo", cfg=fake.cfg, cwd=str(fake.work), env=fake.env) is not None
    assert run_hook(BASH, "rg foo", cfg=fake.cfg, cwd=str(fake.other), env=fake.env) is None
    assert run_hook(BASH, "cd %s && find ." % fake.home, cfg=fake.cfg, cwd=str(fake.elsewhere), env=fake.env) is not None
    assert grep_tool(fake, path=fake.work) is not None
    assert grep_tool(fake, path="/") is not None
    assert grep_tool(fake, path=fake.other) is None
    assert glob_tool(fake, "**/*.md", path=fake.home) is not None
    assert glob_tool(fake, "*.md", path=fake.work) is None
    assert glob_tool(fake, "Priv*/*", path=fake.work) is not None


@posix_only
def test_posix_mnt_drive_form_of_a_windows_style_entry(fake, tmp_path):
    """/mnt/c/Users/me/secret as a configured path is the C: drive; the text forms /mnt/c and /c are both ancestors."""
    mnt = tmp_path / "mnt" / "c" / "Users" / "me" / "secret"      # not the real /mnt, only the path parse is under test
    mnt.mkdir(parents=True)
    # a real /mnt/c entry cannot exist on every machine, so only the parse is checked: it is rejected as nonexistent, by name
    cfg = write_cfg(tmp_path / "cfg2.json", ["/mnt/c/Users/me/secret"])
    reason = run_hook("Grep", cfg=cfg, tool_input={"pattern": "x", "path": str(fake.other)})
    assert reason is not None and "does not exist" in reason and str(cfg) in reason


# ---------------------------------------------------------------- the config: every way it can be wrong denies

def _bad_entries(fake):
    base = str(fake.work)
    for punctuation_only in ("---", "#@!_"):                    # real folders, so only the name rule can reject them
        (fake.work / punctuation_only).mkdir(exist_ok=True)
    entries = {
        "a relative path": "notes/private",
        "a ~ path": "~/private",
        "a trailing separator": str(fake.folder) + os.sep,
        "a bare root": os.path.splitdrive(str(fake.tmp))[0] + os.sep if WIN else "/",
        "a glob in the path": base + os.sep + "Priv*",
        "a bracket in the path": base + os.sep + "Priv[ate]",
        "a regex character in the path": base + os.sep + "a^b",
        "a path that does not exist": base + os.sep + "Missing Folder",
        "a dot-dot segment": base + os.sep + ".." + os.sep + "work" + os.sep + FOLDER_NAME,
        "a folder name with no letter or digit": base + os.sep + "---",
        "a folder name of punctuation only": base + os.sep + "#@!_",
        "an empty string": "",
        "a number": 3,
    }
    if WIN:
        entries["a bare drive letter"] = os.path.splitdrive(str(fake.tmp))[0]
        entries["a UNC path"] = "\\\\host\\share\\folder"
    return entries


def test_every_bad_config_denies_and_names_the_file(fake):
    probe = {"pattern": "x", "path": str(fake.elsewhere)}      # an unrelated folder: a broken config denies it all the same
    cases = {
        "invalid JSON": "{not json",
        "a list at the top level": "[]",
        "the key is a string, not a list": '{"protected_folders": "x"}',
        "the key is missing": '{"folders": []}',
        "an entry is not a string": '{"protected_folders": [["x"]]}',
        "the file is empty": "",
    }
    for name, text in cases.items():
        bad = fake.tmp / "bad.json"
        bad.write_text(text, encoding="utf-8")
        reason = run_hook("Grep", cfg=bad, tool_input=probe, env=fake.env)
        assert reason is not None and str(bad) in reason, name
    for name, entry in _bad_entries(fake).items():
        bad = fake.tmp / "bad.json"
        bad.write_text(json.dumps({"protected_folders": [entry]}), encoding="utf-8")
        reason = run_hook("Grep", cfg=bad, tool_input=probe, env=fake.env)
        assert reason is not None and str(bad) in reason, name
        assert "cannot be trusted" in reason, name
        if "no letter or digit" in name or "punctuation only" in name:
            assert "no letter or digit" in reason, name


def test_a_named_config_that_is_missing_denies(fake):
    gone = fake.tmp / "nope" / "protected-folders.json"
    reason = run_hook("Grep", cfg=gone, tool_input={"pattern": "x", "path": str(fake.elsewhere)}, env=fake.env)
    assert reason is not None and str(gone) in reason and "missing" in reason
    assert run_hook("Glob", cfg=gone, tool_input={"pattern": "*.md"}, env=fake.env) is not None
    assert run_hook(BASH, "git status", cfg=gone, env=fake.env) is None                    # not a recursion: allowed
    assert run_hook(BASH, "echo hello", cfg=gone, env=fake.env) is None


def test_a_config_flag_with_no_file_denies(fake):
    assert run_hook("Grep", tool_input={"pattern": "x"}, extra_args=["--config"], env=fake.env) is not None
    assert run_hook("Grep", tool_input={"pattern": "x"}, extra_args=["--config="], env=fake.env) is not None
    assert run_hook("Grep", tool_input={"pattern": "x"}, extra_args=["--config=%s" % fake.cfg], env=fake.env,
                    cwd=str(fake.elsewhere)) is None


def test_the_reach_of_a_broken_config(fake):
    bad = fake.tmp / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    for tool, cmd in [(BASH, "rg foo ."), (BASH, "find . -name x"), (BASH, "tree"), (BASH, "ls -R"), (BASH, "cp -r a b"),
                      (BASH, "tar czf x.tgz a"), (PS, "Get-ChildItem -Recurse"), (PS, "gci . -r"), (PS, "dir . /s"),
                      (BASH, "python -c \"import os; os.walk('.')\""), (BASH, 'bash -c "find . -name x"'),
                      (BASH, "echo hi; rg foo .")]:
        reason = run_hook(tool, cmd, cfg=bad, env=fake.env)
        assert reason is not None and str(bad) in reason, cmd
    assert "Read and Edit are not blocked" in run_hook("Grep", cfg=bad, tool_input={"pattern": "x"}, env=fake.env)
    for tool, cmd in [(BASH, "git status"), (BASH, "echo find"), (PS, "Get-ChildItem"), (BASH, "ls -la"), (BASH, "python -m pytest -q"),
                      (BASH, "git commit -m 'fix'")]:
        assert run_hook(tool, cmd, cfg=bad, env=fake.env) is None, "wrongly denied: " + cmd
    # Read, Edit and Write never reach the guard, so the file can be repaired
    for tool in ("Read", "Edit", "Write", "NotebookEdit"):
        assert run_hook(tool, tool_input={"file_path": str(bad), "old_string": "a", "new_string": "b"}, cfg=bad) is None


def test_two_files_one_broken_denies(fake):
    proj = fake.tmp / "proj"
    user = fake.tmp / "userdir"
    write_cfg(proj / ".claude" / "protected-folders.json", [fake.folder])
    (user).mkdir()
    (user / "protected-folders.json").write_text("{not json", encoding="utf-8")
    env = dict(fake.env, CLAUDE_PROJECT_DIR=str(proj), CLAUDE_CONFIG_DIR=str(user))
    reason = run_hook("Grep", tool_input={"pattern": "x", "path": str(fake.elsewhere)}, env=env)
    assert reason is not None and str(user / "protected-folders.json") in reason


# ---------------------------------------------------------------- the config: where it comes from

def test_no_config_found_turns_the_guard_off(fake):
    empty = fake.tmp / "emptydir"
    empty.mkdir()
    env = dict(fake.env, CLAUDE_CONFIG_DIR=str(empty))
    cmd = "Get-ChildItem %s -Recurse" % (os.path.splitdrive(str(fake.tmp))[0] + BS if WIN else "/")
    assert run_hook(PS if WIN else BASH, cmd if WIN else "find / -maxdepth 3 -name x", env=env) is None
    assert run_hook("Grep", tool_input={"pattern": "private notes", "path": str(fake.work)}, env=env) is None
    assert run_hook(BASH, "cat '%s'" % fake.folder, env=env) is None


def test_an_empty_list_turns_the_guard_off(fake):
    cfg = write_cfg(fake.tmp / "empty.json", [])
    assert run_hook("Grep", cfg=cfg, tool_input={"pattern": "private notes", "path": str(fake.work)}, env=fake.env) is None
    assert run_hook(BASH, "find %s -name x" % fake.home, cfg=cfg, env=fake.env) is None


def test_the_default_search_unions_the_project_file_and_the_user_directory(fake):
    other_folder = fake.tmp / "second" / "Hidden Reports"
    other_folder.mkdir(parents=True)
    proj = fake.tmp / "proj"
    user = fake.tmp / "userdir"
    write_cfg(proj / ".claude" / "protected-folders.json", [fake.folder])
    write_cfg(user / "protected-folders.json", [other_folder])
    env = dict(fake.env, CLAUDE_PROJECT_DIR=str(proj), CLAUDE_CONFIG_DIR=str(user))
    tool = BASH
    assert run_hook(tool, "cat '%s'" % fake.folder, env=env) is not None
    assert run_hook(tool, "cat '%s'" % other_folder, env=env) is not None
    assert run_hook(tool, "cat '%s'" % (fake.other / "x.txt"), env=env) is None
    # the user directory alone, found through CLAUDE_CONFIG_DIR; and ~/.claude when that variable is unset
    assert run_hook(tool, "cat '%s'" % other_folder, env=dict(fake.env, CLAUDE_CONFIG_DIR=str(user))) is not None
    dot_claude = fake.home / ".claude"
    write_cfg(dot_claude / "protected-folders.json", [other_folder])
    assert run_hook(tool, "cat '%s'" % other_folder, env=fake.env) is not None


def test_a_named_config_is_the_only_source(fake):
    """--config wins over the environment: a broken file in CLAUDE_CONFIG_DIR is not read, a good one is not added."""
    user = fake.tmp / "userdir"
    user.mkdir()
    (user / "protected-folders.json").write_text("{not json", encoding="utf-8")
    env = dict(fake.env, CLAUDE_CONFIG_DIR=str(user))
    assert run_hook("Grep", cfg=fake.cfg, tool_input={"pattern": "x", "path": str(fake.other)}, env=env) is None
    assert run_hook(BASH, "cat '%s'" % fake.folder, cfg=fake.cfg, env=env) is not None


def test_two_protected_folders_in_one_file(fake):
    second = fake.tmp / "elsewhere" / "Payroll"
    second.mkdir()
    cfg = write_cfg(fake.tmp / "two.json", [fake.folder, second])
    assert run_hook(BASH, "cat '%s'" % second, cfg=cfg, env=fake.env) is not None
    assert run_hook(BASH, "cat '%s'" % fake.folder, cfg=cfg, env=fake.env) is not None
    assert run_hook(BASH, "cat '%s'" % (fake.other / "x"), cfg=cfg, env=fake.env) is None
    assert run_hook("Grep", cfg=cfg, tool_input={"pattern": "x", "path": str(fake.elsewhere)}, env=fake.env) is not None   # a directory above Payroll


# ---------------------------------------------------------------- rule 0 reads a whole word, never a bare substring

def test_the_name_is_matched_as_a_whole_word(fake):
    cfg = write_cfg(fake.tmp / "short.json", [fake.work / "Public"])         # a one-word name
    assert run_hook(BASH, "cat public/x.txt", cfg=cfg, env=fake.env) is not None
    assert run_hook(BASH, "echo republic publications", cfg=cfg, env=fake.env) is None
    assert run_hook(BASH, "echo my_public_notes", cfg=cfg, env=fake.env) is not None       # _ and - are separators


def test_the_message_names_what_is_protected_and_what_is_allowed(fake):
    reason = run_hook(BASH, "cat '%s'" % fake.folder, cfg=fake.cfg, env=fake.env)
    assert str(fake.folder) in reason and "! prefix" in reason
    reason = run_hook(BASH, "find %s -name x" % fake.home, cfg=fake.cfg, env=fake.env)
    assert "names-only listing" in reason and str(fake.folder) in reason


def test_a_text_that_only_mentions_a_root_inside_a_commit_message_is_allowed(fake):
    if WIN:
        cmd = "git commit -q -F - <<'EOF'%sNo longer runs Get-ChildItem C:%s -Recurse%sEOF" % (NL, BS, NL)
    else:
        cmd = "git commit -q -F - <<'EOF'%sNo longer runs find / -name x%sEOF" % (NL, NL)
    assert run_hook(BASH, cmd, cfg=fake.cfg, env=fake.env) is None


# ---------------------------------------------------------------- failure modes

def test_an_analysis_error_denies_only_when_a_root_token_was_seen(fake):
    env = dict(fake.env, BDC_TEST_RAISE="1")
    above = "find %s -name x" % (msys(fake.home) if WIN else fake.home)
    assert run_hook(BASH, above, cfg=fake.cfg, env=env) is not None
    assert run_hook(BASH, "git status", cfg=fake.cfg, env=env) is None
    assert run_hook("Grep", cfg=fake.cfg, env=env, tool_input={"pattern": "x", "path": str(fake.other)}) is None
    assert run_hook("Grep", cfg=fake.cfg, env=env, tool_input={"pattern": "x", "path": str(fake.home)}) is not None


def test_the_error_injection_is_ignored_outside_pytest(fake):
    run_env = _clean_env(dict(fake.env, BDC_TEST_RAISE="1"))
    run_env.pop("PYTEST_CURRENT_TEST", None)             # pytest sets it for the running test; a real shell session never does
    payload = json.dumps({"tool_name": BASH, "tool_input": {"command": "find %s -name x" % fake.other.as_posix()},
                          "cwd": str(HOOK.parent)})
    res = subprocess.run([sys.executable, str(HOOK), "--config", str(fake.cfg)], input=payload, capture_output=True,
                         text=True, timeout=60, env=run_env)
    assert res.returncode == 0 and not res.stdout.strip()


def test_other_tools_and_empty_commands_are_ignored(fake):
    assert run_hook("Read", cfg=fake.cfg, tool_input={"file_path": str(fake.folder / "a.txt")}) is None
    assert run_hook("Edit", cfg=fake.cfg, tool_input={"file_path": str(fake.folder / "a.txt")}) is None
    assert run_hook(BASH, "   ", cfg=fake.cfg) is None


def _hook_without_module(tmp_path, module_text=None):
    d = tmp_path / "hookcopy"
    d.mkdir(exist_ok=True)
    shutil.copy(HOOK, d / HOOK.name)
    if module_text is not None:
        (d / MODULE.name).write_text(module_text, encoding="utf-8")
    return d / HOOK.name


@pytest.mark.parametrize("module_text", [None, "def (:\n", "raise RuntimeError('boom')\n"])
def test_a_missing_or_broken_module_never_stops_the_other_rules(fake, module_text):
    hook = _hook_without_module(fake.tmp, module_text)
    # no named config: the folder guard is off, a Grep goes through, and a deny from another rule reports the failure once
    assert run_hook("Grep", tool_input={"pattern": "x", "path": str(fake.home)}, hook=hook, env=fake.env) is None
    reason = run_hook(BASH, "rm -rf /", hook=hook, env=fake.env)
    assert reason is not None and reason.count("did not run") == 1
    reason = run_hook(BASH, "python - <<'EOF'%sprint(1)%sEOF" % (NL, NL), hook=hook, env=fake.env)
    assert reason is not None and "Write tool" in reason and reason.count("did not run") == 1
    # a named config means the owner asked for the guard: Grep, Glob and recursive commands are denied while it is down
    reason = run_hook("Grep", cfg=fake.cfg, tool_input={"pattern": "x", "path": str(fake.other)}, hook=hook, env=fake.env)
    assert reason is not None and "could not run" in reason
    assert run_hook("Glob", cfg=fake.cfg, tool_input={"pattern": "*.md"}, hook=hook, env=fake.env) is not None
    assert run_hook(BASH, "find . -name x", cfg=fake.cfg, hook=hook, env=fake.env) is not None
    assert run_hook(BASH, "git status", cfg=fake.cfg, hook=hook, env=fake.env) is None
    assert run_hook(BASH, "rm -rf /", cfg=fake.cfg, hook=hook, env=fake.env) is not None
    # no --config, but a config sits in the default search place: the guard is wanted, so the dead module denies here too
    env_default = dict(fake.env, CLAUDE_CONFIG_DIR=str(fake.cfg.parent))
    reason = run_hook("Grep", tool_input={"pattern": "x", "path": str(fake.other)}, hook=hook, env=env_default)
    assert reason is not None and "could not run" in reason
    assert run_hook(BASH, "find . -name x", hook=hook, env=env_default) is not None
    assert run_hook(BASH, "git status", hook=hook, env=env_default) is None
    # the fallback reads combined short flags, cp -a, Windows switches and Python tree copies too
    for tool, cmd in [(BASH, "rg -rn x ."), (BASH, "grep -lR x ."), (BASH, "cp -a a b"), (BASH, "cp -ra a b"),
                      (PS, "where /r . x"), (PS, "icacls . /t"), (PS, "attrib /s x"), (BASH, "ls -R"), (BASH, "tar czf x.tgz a"),
                      (BASH, "python3 -c \"import shutil; shutil.copytree('a', 'b')\""), (PS, "Copy-Item a b -Recurse"),
                      (BASH, "git status && find . -name x")]:
        assert run_hook(tool, cmd, cfg=fake.cfg, hook=hook, env=fake.env) is not None, "fallback missed: " + cmd
    for tool, cmd in [(BASH, "git commit -am 'fix'"), (BASH, "ls -la"), (PS, "Remove-Item x -Force"), (BASH, "python -m pytest -q"),
                      (PS, "Get-Content -Path x -ErrorAction Stop"), (BASH, "echo done")]:
        assert run_hook(tool, cmd, cfg=fake.cfg, hook=hook, env=fake.env) is None, "fallback over-denied: " + cmd


# ---------------------------------------------------------------- regressions found by the QA pass

@windows_only
def test_windows_device_prefix_and_file_url_spellings_in_both_slash_styles(fake):
    d = os.path.splitdrive(str(fake.tmp))[0]          # X:
    spellings = ["//?/%s/" % d, "//./%s/" % d, "//?/%s" % d.lower(), "//?/%s%s" % (d, BS), BS + BS + "?" + BS + d + BS,
                 BS + BS + "." + BS + d + BS, "file:///%s/" % d]
    for s in spellings:
        for tool, cmd in [(BASH, "rg --files %s" % s), (PS, "rg --files %s" % s), (PS, "Get-ChildItem -LiteralPath %s -Recurse" % s),
                          (BASH, "python -c \"import os; print(list(os.walk('%s')))\"" % s), (BASH, "find %s -name x" % s)]:
            assert run_hook(tool, cmd, cfg=fake.cfg, env=fake.env) is not None, "not denied: " + cmd
        if s.startswith("file:"):
            continue                                   # a file URL is only a spelling a shell command can carry, not a Grep or Glob path
        assert run_hook("Grep", cfg=fake.cfg, env=fake.env, tool_input={"pattern": "x", "path": s}) is not None, "Grep " + s
        assert run_hook("Glob", cfg=fake.cfg, env=fake.env, tool_input={"pattern": "**/*.md", "path": s}) is not None, "Glob " + s
    # the same prefix in front of a directory that is not above the folder stays allowed
    for s in ["//?/%s/" % d + str(fake.other)[len(d) + 1:].replace(BS, "/"), "//./%s/" % d + str(fake.other)[len(d) + 1:].replace(BS, "/")]:
        assert run_hook(PS, "Get-ChildItem -LiteralPath %s -Recurse" % s, cfg=fake.cfg, env=fake.env) is None, s
    # UNC admin share and the device UNC prefix in forward slashes
    assert run_hook(PS, "Get-ChildItem //localhost/%s$/ -Recurse" % d[0], cfg=fake.cfg, env=fake.env) is not None
    assert run_hook(PS, "Get-ChildItem //?/UNC/localhost/%s$/ -Recurse" % d[0], cfg=fake.cfg, env=fake.env) is not None


def _env_home(fake, home):
    return dict(fake.env, HOME=str(home), USERPROFILE=str(home))


def test_a_tilde_climb_is_read_both_ways(fake):
    """~ is the real home for Bash and cmdlets, but cmd.exe and Windows PowerShell 5.1 hand it to a native program
    literally, so a .. climb counts from the working directory. A deny when either reading lands above the folder."""
    h2 = fake.elsewhere / "home2"
    h2.mkdir()
    env = _env_home(fake, h2)                          # the real home is harmless: beside the folder, not above it
    work = str(fake.work)
    # the literal reading: <work>/~/.. is <work>, an ancestor
    for tool, cmd in [(BASH, "find ~/.. -name x"), (PS, "cmd /c dir ~/.. /s"), (PS, "Get-ChildItem ~/.. -Recurse"),
                      (BASH, "rg foo ~/../.."), (PS, "Start-Process cmd -ArgumentList '/c dir ~/.. /s'")]:
        assert run_hook(tool, cmd, cfg=fake.cfg, cwd=work, env=env) is not None, "not denied: " + cmd
    # both readings harmless: the home itself, a sibling folder's climb, a search below the folder's parent's sibling
    other = str(fake.other)
    for tool, cmd in [(BASH, "find ~ -name x"), (PS, "cmd /c dir ~ /s"), (BASH, "rg foo ~/other"), (PS, "Get-ChildItem ~ -Recurse"),
                      (BASH, "find ~/.. -name x")]:
        assert run_hook(tool, cmd, cfg=fake.cfg, cwd=other, env=env) is None, "wrongly denied: " + cmd
    # Grep and Glob: the same two readings
    assert run_hook("Grep", cfg=fake.cfg, cwd=work, env=env, tool_input={"pattern": "x", "path": "~/.."}) is not None
    assert run_hook("Glob", cfg=fake.cfg, cwd=work, env=env, tool_input={"pattern": "**/*.md", "path": "~/.."}) is not None
    assert run_hook("Grep", cfg=fake.cfg, cwd=other, env=env, tool_input={"pattern": "x", "path": "~"}) is None


@windows_only
def test_windows_an_msys_program_started_from_powershell_climbs_out_of_the_home(fake):
    """Under Git Bash the home is /c/Users/me and a .. climb out of it passes the drive letter to the MSYS root, where /x is the
    drive again. From PowerShell a native program receives C:\\Users\\me and the climb clamps at the drive root, so the same
    climb does NOT reach another drive there; the guard reads it the Git Bash way for the PowerShell tool as well, a
    conservative over-deny that this test pins (it keeps the denies, it does not claim they are needed)."""
    n = len(fake.home.parts)                           # parts include the drive anchor: n .. climbs reach the MSYS root
    climb = "/".join([".."] * n)
    for tool in (BASH, PS):
        for text in ["~/%s/%s" % (climb, fake.letter), "$HOME/%s/%s" % (climb, fake.letter),
                     "$env:USERPROFILE%s%s" % ("".join(BS + ".." for _ in range(n)), BS + fake.letter)]:
            assert run_hook(tool, "find %s -name x" % text, cfg=fake.cfg, env=fake.env) is not None, (tool, text)
        assert run_hook("Grep", cfg=fake.cfg, env=fake.env, tool_input={"pattern": "x", "path": "~/%s/%s" % (climb, fake.letter)}) is not None


def test_home_forms_beyond_tilde(fake):
    me = fake.home / "me"
    me.mkdir()
    env = _env_home(fake, me)                          # home is <home>/me, beside <home>/work: ~work is the folder's parent
    for tool, cmd in [(BASH, "find ~work -name x"), (PS, "Get-ChildItem ~work -Recurse"), (BASH, "rg foo ~work/.."),
                      (BASH, "rg foo $USERPROFILE/.."), (BASH, "rg foo ${USERPROFILE}/.."), (BASH, "rg foo ${HOME}/.."),
                      (BASH, "find $HOME/../work -name x")]:
        assert run_hook(tool, cmd, cfg=fake.cfg, env=env) is not None, "not denied: " + cmd
    assert run_hook(BASH, "find ~other -name x", cfg=fake.cfg, env=env) is None          # <home>/other: a sibling, not above the folder
    assert run_hook(BASH, "rg foo $USERPROFILE", cfg=fake.cfg, env=env) is None          # the home itself is below <home>
    if WIN:
        drive = os.path.splitdrive(str(fake.tmp))[0]
        env2 = _env_home(fake, fake.home)              # home is above the folder
        for tool, cmd in [(PS, "rg foo $env:HOMEDRIVE$env:HOMEPATH"), (PS, "Get-ChildItem %HOMEDRIVE%%HOMEPATH% -Recurse"),
                          (PS, "Get-ChildItem $env:HOMEDRIVE%s -Recurse" % BS), (PS, "rg foo %HOMEDRIVE%" + BS)]:
            run_env = dict(env2, HOMEDRIVE=drive, HOMEPATH=str(fake.home)[len(drive):])
            assert run_hook(tool, cmd, cfg=fake.cfg, env=run_env) is not None, "not denied: " + cmd


@windows_only
def test_windows_switches_of_native_tools_are_not_drive_letters(fake):
    """/t /c /s /r /d after icacls, forfiles, attrib, takeown, findstr, where, dir, tree are switches, whatever the drive's letter."""
    other = str(fake.other)
    L = fake.letter
    for tool, cmd in [(PS, "icacls x /t /%s" % L), (PS, 'forfiles /s /%s "cmd /c echo @file"' % L), (PS, "attrib /s /%s x" % L),
                      (PS, "takeown /r /%s /f x" % L), (PS, "dir /s /%s" % L), (PS, "tree /%s" % L), (PS, "where /r . /%s x" % L)]:
        assert run_hook(tool, cmd, cfg=fake.cfg, cwd=other, env=fake.env) is None, "wrongly denied: " + cmd
    # a directory above the folder named in the same statement is still caught
    assert run_hook(PS, "icacls %s /t" % fake.home, cfg=fake.cfg, cwd=other, env=fake.env) is not None
    assert run_hook(PS, "attrib /s %s%s*" % (fake.home, BS), cfg=fake.cfg, cwd=other, env=fake.env) is not None


@windows_only
def test_git_bash_doubled_slash_switches_are_recursion_markers(fake):
    """Under Git Bash a Windows switch is written with a doubled slash (//s, //t, //r) so MSYS leaves it alone; the guard
    reads it as the single-slash switch, so a recursive command above a protected folder is still denied."""
    home, other = str(fake.home).replace(BS, "/"), str(fake.other).replace(BS, "/")
    for cmd in ["dir //s %s", "attrib //s %s/*", "icacls %s //t", "takeown //r //f %s", "findstr //s //c:hello %s/*",
                "where //r %s x"]:
        assert run_hook(BASH, cmd % home, cfg=fake.cfg, cwd=str(fake.other), env=fake.env) is not None, "not denied: " + cmd
        assert run_hook(BASH, cmd % other, cfg=fake.cfg, cwd=str(fake.other), env=fake.env) is None, "wrongly denied: " + cmd
    # grep and rg take no slash switches: a pattern such as //go:build is a pattern, so the path after it is still judged
    for cmd in ["grep -rn //go:build %s", "rg //go %s", "rg -n //go %s", "grep -r //fix %s"]:
        assert run_hook(BASH, cmd % home, cfg=fake.cfg, cwd=str(fake.other), env=fake.env) is not None, "not denied: " + cmd
        assert run_hook(BASH, cmd % other, cfg=fake.cfg, cwd=str(fake.other), env=fake.env) is None, "wrongly denied: " + cmd


@windows_only
def test_combined_switches_and_cmd_double_slash_wrapper_are_seen(fake):
    """bf1c655b: switches run together (dir /s/b, dir /b/s, attrib /s/d, Git Bash dir //s//b) are recursion markers, and
    `cmd //c <command>` (Git Bash's form of cmd /c) is a wrapper, so the inner command is judged."""
    home, other = str(fake.home).replace(BS, "/"), str(fake.other).replace(BS, "/")
    for tool, cmd in [(BASH, "dir //s//b %s"), (BASH, "dir //b//s %s"), (BASH, "attrib //s//d %s/*"),
                      (PS, "dir /s/b %s"), (PS, "dir /b/s %s"), (PS, "attrib /s/d %s/*"),
                      (BASH, "cmd //c dir /s/b %s"), (BASH, "cmd //c dir //s %s"), (BASH, 'cmd //c "dir /s /b %s"'),
                      (PS, "cmd /c dir /s/b %s")]:
        assert run_hook(tool, cmd % home, cfg=fake.cfg, cwd=str(fake.other), env=fake.env) is not None, "not denied: " + cmd
        assert run_hook(tool, cmd % other, cfg=fake.cfg, cwd=str(fake.other), env=fake.env) is None, "wrongly denied: " + cmd
    # a plain path made of short pieces is not split into switches
    assert run_hook(BASH, "ls /usr/bin", cfg=fake.cfg, cwd=str(fake.other), env=fake.env) is None
    # QA finding 2: a minus or colon inside a run-together switch (/a-d, /o-d, /a:d) is still one switch
    for tool, cmd in [(PS, "dir /s/b/a-d %s"), (PS, "dir /b/s/a-d %s"), (PS, "dir /a-d/s %s"), (PS, "dir /s/o-d %s"),
                      (PS, "dir /a:d/s %s"), (BASH, "dir //s//b//a-d %s"), (BASH, 'cmd //c "dir /s/b/a-d %s"')]:
        assert run_hook(tool, cmd % home, cfg=fake.cfg, cwd=str(fake.other), env=fake.env) is not None, "not denied: " + cmd
        assert run_hook(tool, cmd % other, cfg=fake.cfg, cwd=str(fake.other), env=fake.env) is None, "wrongly denied: " + cmd
    # QA finding 1: no path argument, cwd above the protected folder: the combined form is judged like the separated one
    for tool, cmd in [(PS, "dir /s/b"), (PS, "dir /b/s"), (PS, "attrib /s/d"), (PS, "cmd /c dir /s/b"), (PS, "icacls * /t/c"),
                      (BASH, "dir //s//b"), (BASH, "cmd //c dir /s/b"), (BASH, "icacls * //t//c")]:
        assert run_hook(tool, cmd, cfg=fake.cfg, cwd=str(fake.home), env=fake.env) is not None, "not denied at ancestor cwd: " + cmd
        assert run_hook(tool, cmd, cfg=fake.cfg, cwd=str(fake.other), env=fake.env) is None, "wrongly denied below: " + cmd
    assert run_hook(BASH, "cd %s && cmd //c dir /s/b" % home, cfg=fake.cfg, cwd=str(fake.other), env=fake.env) is not None
    # QA finding 3: findstr with run-together switches keeps its pattern, so a root-looking pattern is not read as a path
    for tool, cmd in [(PS, "findstr /s/i J:/ %s/*"), (PS, "findstr /s/i %s %s/*"), (BASH, "findstr //s//i J:/ %s/*")]:
        n = cmd.count("%s")
        assert run_hook(tool, cmd % ((other,) * n), cfg=fake.cfg, cwd=str(fake.other), env=fake.env) is None, "wrongly denied: " + cmd
    assert run_hook(PS, "findstr /s/i foo *", cfg=fake.cfg, cwd=str(fake.home), env=fake.env) is not None
    assert run_hook(PS, "findstr /s/c:foo %s/*" % home, cfg=fake.cfg, cwd=str(fake.other), env=fake.env) is not None


def test_findstr_c_gives_the_pattern_so_the_next_word_is_a_path(fake):
    if not WIN:
        pytest.skip("findstr is Windows-only")
    other = str(fake.other)
    assert run_hook(PS, 'findstr /s /c:"hello" %s%s*' % (fake.home, BS), cfg=fake.cfg, cwd=other, env=fake.env) is not None
    assert run_hook(PS, 'findstr /s /c:"hello" %s%s*' % (fake.other, BS), cfg=fake.cfg, cwd=str(fake.home), env=fake.env) is None


@posix_only
def test_posix_a_lone_slash_anywhere_in_a_recursive_command_is_the_root(fake):
    for cmd in ["tar czf x.tgz /", "cp -r / /tmp/dump", "zip -r x.zip /", "rg foo -g '*.md' /", "grep -rn foo -i /",
                "python3 -c \"import os; print(list(os.walk('/')))\""]:
        assert run_hook(BASH, cmd, cfg=fake.cfg, cwd=str(fake.elsewhere), env=fake.env) is not None, "not denied: " + cmd
    for cmd in ["find . -name x | awk '{print $1 / 2}'", "echo $((4 / 2))", "ls | wc -l", "rg foo . | sed 's/a/b/'", "tr '/' '_' < x.txt",
                "cp a.txt b.txt", "cp -r a b", "python3 -c \"print(4 / 2)\"", "tar czf x.tgz a b"]:
        assert run_hook(BASH, cmd, cfg=fake.cfg, cwd=str(fake.elsewhere), env=fake.env) is None, "wrongly denied: " + cmd


# ---------------------------------------------------------------- rules 1 to 4 and 6 (the portable part of the hook)

def test_rule_1_a_filesystem_root_removal_is_denied():
    assert run_hook(BASH, "rm -rf /") is not None
    assert run_hook(BASH, "rm -rf /c") is not None
    assert run_hook(PS, "Remove-Item -Recurse -Force C:%s" % BS) is not None
    assert run_hook(BASH, "rm -rf build/") is None
    assert run_hook(BASH, "rm -rf /c/Users/me/old") is None
    assert run_hook(PS, "Remove-Item -Recurse -Force build/") is None


def test_rule_2_a_force_push_to_main_is_denied():
    assert run_hook(BASH, "git push --force origin main") is not None
    assert run_hook(BASH, "git push -f origin master") is not None
    assert run_hook(BASH, "git push --force-with-lease origin main") is not None
    assert run_hook(BASH, "git push origin main") is None
    assert run_hook(BASH, "git push --force origin feature") is None


def _repo(tmp_path):
    if not shutil.which("git"):
        pytest.skip("git is not installed")
    repo = tmp_path / "repo"
    repo.mkdir()
    for args in (["init", "-q"], ["config", "user.email", "t@example.com"], ["config", "user.name", "t"]):
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)
    (repo / "a.txt").write_text("a", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "a.txt"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "init"], check=True, capture_output=True)
    return repo


def test_rule_3_reset_hard_only_when_there_is_something_to_lose(tmp_path):
    repo = _repo(tmp_path)
    assert run_hook(BASH, "git reset --hard", cwd=str(repo)) is None                 # clean tree
    (repo / "a.txt").write_text("changed", encoding="utf-8")
    assert run_hook(BASH, "git reset --hard", cwd=str(repo)) is not None            # dirty tree


def test_rule_4_clean_only_when_it_would_remove_something(tmp_path):
    repo = _repo(tmp_path)
    assert run_hook(BASH, "git clean -fd", cwd=str(repo)) is None
    (repo / "junk.txt").write_text("x", encoding="utf-8")
    assert run_hook(BASH, "git clean -fd", cwd=str(repo)) is not None


def heredoc(head, body, delimiter="EOF", quote="'"):
    return head + " <<" + quote + delimiter + quote + NL + body + NL + delimiter


HEREDOC_DENY = {
    "python with a regex and a joined newline":
        heredoc("python - ", "import re" + NL + "s = re.sub(r\"" + BS + "d+\", \"\", t)" + NL + "out = \"" + BS + "n\".join(x)", "PYEOF"),
    "python, unquoted delimiter, backslash": heredoc("python3 -", "print(\"a" + BS + "nb\")", quote=""),
    "python, unquoted delimiter, a dollar sign": heredoc("python -", "x = '$HOME'", quote=""),
    "python, a backtick": heredoc("python -", "print('use `grep`')", quote=""),
    "node with a backslash": heredoc("node -", "console.log(\"a" + BS + "nb\")"),
    "an interpreter named with a path and .exe": heredoc("C:/Python312/python.exe -", "print(\"a" + BS + "tb\")"),
    "a script file written by cat": heredoc("cat > /tmp/fix.py", "print(\"a" + BS + "nb\")"),
    "a script file appended by tee": heredoc("cat >> patch.js", "const s = 'a" + BS + "nb';"),
    "the heredoc is not on the first line": "cd /tmp" + NL + heredoc("python -", "print(\"a" + BS + "nb\")"),
    "a python script with no backslash at all": heredoc("python -", "import json" + NL + "print(json.dumps({'a': 1}))"),
    "an unquoted python heredoc with nothing special": heredoc("python -", "print('plain')", quote=""),
    "bash given a script": heredoc("bash", "echo hi"),
}


@pytest.mark.parametrize("name", list(HEREDOC_DENY))
def test_rule_6_a_heredoc_script_is_denied(name):
    reason = run_hook(BASH, HEREDOC_DENY[name])
    assert reason is not None, "not denied: " + HEREDOC_DENY[name]
    assert "Write tool" in reason                     # it says what to do instead


HEREDOC_ALLOW = {
    "a commit message with a backslash": heredoc("git commit -q -F -", "Fix the " + BS + "n handling in the parser"),
    "a markdown note with a backslash, written by cat": heredoc("cat >> notes.md", "paths look like C:" + BS + "Work " + BS + "n"),
    "a json file written by cat": heredoc("cat > config.json", "{\"path\": \"C:" + BS + BS + "x\"}"),
    "an unquoted commit message with a dollar sign": heredoc("git commit -q -F -", "costs $5", quote=""),
    "a backslash in the command line but not in the heredoc body": "python -c \"print(1)\" && " + heredoc("cat", "plain text"),
    "a script run from a file": "python " + BS + "tmp" + BS + "fix.py",
    "a commit whose file list names a .py file": heredoc("git commit -q -F - -- tool.py README.md", "the root walk"),
}


@pytest.mark.parametrize("name", list(HEREDOC_ALLOW))
def test_rule_6_other_heredocs_stay_allowed(name):
    assert run_hook(BASH, HEREDOC_ALLOW[name]) is None, "wrongly denied: " + HEREDOC_ALLOW[name]


def test_rule_6_applies_to_powershell_too_and_an_unterminated_heredoc_is_left_alone():
    assert run_hook(PS, HEREDOC_DENY["node with a backslash"]) is not None
    assert run_hook(BASH, "python - <<'EOF'") is None


def test_ordinary_commands_pass_untouched(fake):
    for tool, cmd in [(BASH, "ls -la"), (BASH, "python -m pytest -q"), (PS, "Get-ChildItem | Select-Object Name")]:
        assert run_hook(tool, cmd, cfg=fake.cfg, env=fake.env, cwd=str(fake.elsewhere)) is None


# ---------------------------------------------------------------- third review (2026-10-24): escaped names, Monitor, mutants

def _above(fake):
    """The fake work folder (the folder's parent) spelled the way the Bash tool reads it."""
    return msys(fake.work) if WIN else fake.work.as_posix()


ESCAPED_NAMES = {
    "a Git Bash backslash-escaped space": (BASH, "Private" + BS + " Notes"),
    "a PowerShell backtick-escaped space": (PS, "Private` Notes"),
    "a cmd caret-escaped space": (PS, "Private^ Notes"),
    "a double-quote pair around the space": (BASH, 'Private" "Notes'),
    "a single-quote pair around the space": (BASH, "Private' 'Notes"),
}


@pytest.mark.parametrize("label", list(ESCAPED_NAMES))
def test_the_folder_name_with_an_escaped_or_quoted_space_is_denied(fake, label):
    tool, name = ESCAPED_NAMES[label]
    for cmd in ("ls %s", "cat %s/x.txt", "ls %s/*", "Get-ChildItem %s", "dir %s"):
        assert run_hook(tool, cmd % name, cfg=fake.cfg, env=fake.env, cwd=str(fake.work)) is not None, "not denied: " + cmd % name
    for tool2, cmd in [(BASH, "ls Private"), (BASH, "ls Notes"), (BASH, "echo Private" + BS + " things"), (PS, "Get-ChildItem Public")]:
        assert run_hook(tool2, cmd, cfg=fake.cfg, env=fake.env, cwd=str(fake.work)) is None, "wrongly denied: " + cmd


DECODED_NAMES = {
    "Bash ANSI-C quoted space between the words": (BASH, "ls Private$' 'Notes"),
    "Bash ANSI-C hex space": (BASH, "cat Private$'" + BS + "x20'Notes/x.txt"),
    "Bash ANSI-C octal space": (BASH, "cat Private$'" + BS + "040'Notes/x.txt"),
    "Bash ANSI-C unicode space": (BASH, "cat Private$'" + BS + "u0020'Notes/x.txt"),
    "Bash whole name inside one ANSI-C string": (BASH, "ls $'Private" + BS + "x20Notes'"),
    "Bash ANSI-C letter in the name": (BASH, "ls $'" + BS + "x50'rivate' 'Notes"),
    "PowerShell backtick-u space": (PS, "Get-Content Private`u{20}Notes" + BS + "x.txt"),
    "PowerShell backtick-u letter": (PS, "Get-ChildItem `u{50}rivate` Notes"),
}


@pytest.mark.parametrize("label", list(DECODED_NAMES))
def test_the_folder_name_spelled_with_a_shell_escape_sequence_is_denied(fake, label):
    tool, cmd = DECODED_NAMES[label]
    assert run_hook(tool, cmd, cfg=fake.cfg, env=fake.env, cwd=str(fake.work)) is not None, "not denied: " + cmd
    assert run_hook("Monitor", cmd, cfg=fake.cfg, env=fake.env, cwd=str(fake.work)) is not None or tool == PS, "Monitor: " + cmd


def test_a_drive_root_spelled_with_an_ansi_c_escape_is_denied(fake):
    cmd = "find $'" + BS + "x2f'" + _above(fake)[1:] + " -name x"
    assert run_hook(BASH, cmd, cfg=fake.cfg, env=fake.env) is not None, "not denied: " + cmd


def test_ordinary_escape_sequences_stay_allowed(fake):
    for tool, cmd in [(BASH, "echo $'a" + BS + "tb'"), (BASH, "printf '%s' $'x'"), (BASH, "cat $'notes.txt'"),
                      (BASH, "git log --format=$'%h" + BS + "n'"), (BASH, "echo `date`"), (BASH, "echo $'Private' Notes2"),
                      (PS, "Write-Output `u{41}"), (PS, "Write-Output \"a`tb\""), (PS, "Get-ChildItem `Public")]:
        assert run_hook(tool, cmd, cfg=fake.cfg, env=fake.env, cwd=str(fake.elsewhere)) is None, "wrongly denied: " + cmd


QUOTE_REMOVED_NAMES = {
    "a backslash inside a word": "ls P" + BS + "rivate Notes",
    "an empty single-quote pair inside a word": "ls Pri''vate Notes",
    "a double-quoted piece inside a word": 'ls Pri"va"te Notes',
    "a quoted word and a quoted space": "ls \"Pri\"vate' 'Notes",
    "an escaped space and an empty pair": "ls Pr''ivate" + BS + " Notes",
}


@pytest.mark.parametrize("label", list(QUOTE_REMOVED_NAMES))
def test_the_folder_name_with_shell_quote_removal_inside_a_word_is_denied(fake, label):
    cmd = QUOTE_REMOVED_NAMES[label]
    assert run_hook(BASH, cmd, cfg=fake.cfg, env=fake.env, cwd=str(fake.work)) is not None, "not denied: " + cmd


def test_an_earlier_dollar_quote_in_a_single_quoted_string_does_not_hide_a_real_escape(fake):
    """'x$' is a grep anchor, not an ANSI-C opener; the decoder must still find the real $'\\x20' after it."""
    for cmd in ["grep -n 'x$' a.txt; ls Private$'" + BS + "x20'Notes",
                "grep 'x$' a.txt 'y$' b.txt && ls Private$' 'Notes",
                "grep -n 'x$' a.txt; find $'" + BS + "x2f'" + _above(fake)[1:] + " -name x"]:
        assert run_hook(BASH, cmd, cfg=fake.cfg, env=fake.env, cwd=str(fake.elsewhere)) is not None, "not denied: " + cmd


def test_dollar_quote_inside_other_quotes_is_not_decoded_into_a_false_deny(fake):
    """Bash does not decode $' inside single or double quotes; a command that only holds such text must keep its raw verdict."""
    cases = [(BASH, "grep -l 'foo$' notes.md 'bar'"), (BASH, "grep -c 'a$' x 'b$' y"), (BASH, "echo \"cost $'5' here\""),
             (PS, "git commit -m \"fix the `notes` handling\""), (PS, "Write-Output 'a$' 'b'"),
             (BASH, "git commit -m 'anchor x$ and the folder list'")]
    if WIN:
        cases.append((BASH, "grep -l 'foo$' C:" + BS + "notes" + BS + "x.md 'bar'"))
    for tool, cmd in cases:
        assert run_hook(tool, cmd, cfg=fake.cfg, env=fake.env, cwd=str(fake.work)) is None, "wrongly denied: " + cmd


def test_a_decode_failure_never_changes_the_raw_verdict(fake, monkeypatch):
    """The decoded view is an addition: when decoding raises, the raw text is still judged and no error escapes."""
    spec = importlib.util.spec_from_file_location("pfg_decode_probe", MODULE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "_decode_shell_escapes", lambda text, tool: 1 / 0)
    assert mod.evaluate(BASH, {"command": "ls Private Notes"}, str(fake.work), "ls Private Notes", ["--config", str(fake.cfg)],
                        env=fake.env) is not None
    assert mod.evaluate(BASH, {"command": "git status"}, str(fake.work), "git status", ["--config", str(fake.cfg)],
                        env=fake.env) is None


def test_monitor_is_screened_like_bash(fake):
    """Monitor starts a shell command in tool_input.command, so every rule that applies to Bash applies to it."""
    assert run_hook("Monitor", "find %s -name x" % _above(fake), cfg=fake.cfg, env=fake.env) is not None
    assert run_hook("Monitor", "ls Private" + BS + " Notes", cfg=fake.cfg, env=fake.env, cwd=str(fake.work)) is not None
    assert run_hook("Monitor", "rm -rf /", cfg=fake.cfg, env=fake.env) is not None
    for cmd in ("git status", "find %s -maxdepth 1 -name x" % _above(fake), "tail -f build.log"):
        assert run_hook("Monitor", cmd, cfg=fake.cfg, env=fake.env, cwd=str(fake.elsewhere)) is None, "wrongly denied: " + cmd


def test_find_maxdepth_is_a_limit_only_at_0_and_1(fake):
    for n in ("2", "3", "5", "10"):
        cmd = "find %s -maxdepth %s -name x" % (_above(fake), n)
        assert run_hook(BASH, cmd, cfg=fake.cfg, env=fake.env) is not None, "not denied: " + cmd
    for n in ("0", "1"):
        cmd = "find %s -maxdepth %s -name x" % (_above(fake), n)
        assert run_hook(BASH, cmd, cfg=fake.cfg, env=fake.env) is None, "wrongly denied: " + cmd


def test_cp_with_a_recursive_flag_over_the_folder_is_denied(fake):
    for flag in ("-r", "-R", "-a", "-ra", "-rf", "-aT"):
        cmd = "cp %s %s /tmp/dump" % (flag, _above(fake))
        assert run_hook(BASH, cmd, cfg=fake.cfg, env=fake.env) is not None, "not denied: " + cmd
    other = msys(fake.other) if WIN else fake.other.as_posix()
    for flag in ("-r", "-a"):
        cmd = "cp %s %s /tmp/dump" % (flag, other)
        assert run_hook(BASH, cmd, cfg=fake.cfg, env=fake.env) is None, "wrongly denied: " + cmd


@windows_only
def test_grep_and_glob_path_in_the_admin_share_form_is_denied(fake):
    drive = fake.letter.upper()
    rest = os.path.splitdrive(str(fake.home))[1].lstrip(BS)
    other = os.path.splitdrive(str(fake.other))[1].lstrip(BS)
    for p in (BS * 2 + "localhost" + BS + drive + "$", BS * 2 + "localhost" + BS + drive + "$" + BS + rest,
              "//localhost/%s$/%s" % (drive, rest.replace(BS, "/"))):
        assert grep_tool(fake, path=p) is not None, "Grep not denied: " + p
        assert glob_tool(fake, "**/*.md", path=p) is not None, "Glob not denied: " + p
    p = BS * 2 + "localhost" + BS + drive + "$" + BS + other
    assert grep_tool(fake, path=p) is None, "wrongly denied: " + p


# ---------------------------------------------------------------- fourth round (2026-10-25): the third review's findings 3 to 7
# Spellings used in the cases below: @A@ is the fake work folder (the folder's parent) the way the Bash tool reads it, @AP@ with
# forward slashes (what a Python or Node string holds), @AN@ native (what PowerShell is given); @O@ @OP@ @ON@ are the same for the
# unrelated folder beside it, which must stay allowed.

def _spell(fake, cmd):
    work, other = fake.work, fake.other
    pairs = {"@A@": _above(fake), "@AP@": work.as_posix(), "@AN@": str(work),
             "@O@": msys(other) if WIN else other.as_posix(), "@OP@": other.as_posix(), "@ON@": str(other)}
    for k, v in pairs.items():
        cmd = cmd.replace(k, v)
    return cmd


def _denied(fake, tool, cmd, cwd=None):
    return run_hook(tool, _spell(fake, cmd), cfg=fake.cfg, env=fake.env, cwd=str(cwd or fake.elsewhere))


# finding 3: an if/while/until statement that holds a brace is a Bash condition here, not a PowerShell script block
BRACE_DENY = [
    (BASH, "if find @A@ -name '{x}'; then echo hit; fi"),
    (BASH, "if find @A@ -name x -exec ls {} +; then echo hit; fi"),
    (BASH, "while find @A@ -name '*.{pdf,docx}'; do break; done"),
    (BASH, "until find @A@ -iname '*.{pdf,docx}' -print -quit | grep -q .; do break; done"),
]
BRACE_ALLOW = [
    (BASH, "if [ -d @A@ ]; then echo hit; fi"),
    (BASH, "if find @O@ -name '{x}'; then echo hit; fi"),
    (BASH, "if find @O@ -name x -exec ls {} +; then echo hit; fi"),
    (PS, "if (Test-Path '@AN@') { Get-ChildItem '@ON@' -Recurse }"),
    (PS, "foreach ($d in '@ON@') { Get-ChildItem $d -Recurse }"),
]


@pytest.mark.parametrize("tool,cmd", BRACE_DENY, ids=[c for _, c in BRACE_DENY])
def test_a_brace_in_an_if_or_while_condition_does_not_hide_a_recursion_over_the_folders_parent(fake, tool, cmd):
    assert _denied(fake, tool, cmd) is not None, "not denied: " + _spell(fake, cmd)


@pytest.mark.parametrize("tool,cmd", BRACE_ALLOW, ids=[c for _, c in BRACE_ALLOW])
def test_a_brace_in_a_condition_stays_allowed_when_nothing_walks_into_the_folder(fake, tool, cmd):
    assert _denied(fake, tool, cmd) is None, "wrongly denied: " + _spell(fake, cmd)


# finding 4: a root held in a variable, a loop variable or a splat, then recursed
VARIABLE_DENY = [
    (PS, "$p='@AN@'; Get-ChildItem $p -Recurse"),
    (PS, "$p = \"@AN@\"; Get-ChildItem -Path $p -Recurse"),
    (PS, "$p='@AN@'" + NL + "Get-ChildItem -Path $p -Recurse"),
    (PS, "$a=@{Path='@AN@';Recurse=$true}; Get-ChildItem @a"),
    (PS, "$p='@AN@'; $q=$p; Get-ChildItem $q -Recurse"),
    (PS, "foreach ($d in '@AN@') { Get-ChildItem $d -Recurse }"),
    (BASH, "d=@A@; find $d -name x"),
    (BASH, "export d=@A@; find \"$d\" -name x"),
    (BASH, "d=@A@; e=$d; find ${e} -name x"),
    (BASH, "for d in @A@; do find $d -name x; done"),
    (BASH, "d=@A@; cd $d; find . -name x"),
    # QA of the fourth round: a list variable, a value set from itself, Bash case, ${d%/}, assignments in other places
    (PS, "$dirs = '@AN@'; foreach ($d in $dirs) { Get-ChildItem $d -Recurse }"),
    (PS, "$dirs = '@AN@','@ON@'; foreach ($d in $dirs) { Get-ChildItem $d -Recurse }"),
    (PS, "$dirs = @('@AN@'); foreach ($d in $dirs) { Get-ChildItem $d -Recurse }"),
    (PS, "foreach ($d in @('@AN@')) { Get-ChildItem $d -Recurse }"),
    (PS, "$all = @(); $all += Get-ChildItem '@AN@' -Recurse"),
    (PS, "$p = '@AN@'; $p += ''; Get-ChildItem $p -Recurse"),
    # second QA pass: a comma list with spaces, foreach over itself, the loop variable's old value, quoted pieces, appends, typed and scoped names
    (PS, "$dirs = '@ON@', '@AN@'; foreach ($d in $dirs) { Get-ChildItem $d -Recurse }"),
    (PS, "$d='@AN@'; foreach ($d in $d) { Get-ChildItem $d -Recurse }"),
    (PS, "$d='@ON@'; foreach ($d in '@AN@') { Get-ChildItem $d -Recurse }"),
    (PS, "[string]$p = '@AN@'; Get-ChildItem $p -Recurse"),
    (PS, "$script:p = '@AN@'; Get-ChildItem $script:p -Recurse"),
    (BASH, "d=\"@A@\"/; find $d -name x"),
    (BASH, "d='@A@'/; find $d -name x"),
    (BASH, "d=@A@; d+=''; find $d -name x"),
    (BASH, "d=@A@; (d=@O@); find $d -name x"),
    (PS, "$p='@AN@'; $p = \"$p\"; Get-ChildItem $p -Recurse"),
    (PS, "$p='@AN@'; $p = $p; Get-ChildItem $p -Recurse"),
    (PS, "$env:P = '@AN@'; Get-ChildItem $env:P -Recurse"),
    (BASH, "d=@A@; for d in $d; do find $d -name x; done"),
    (BASH, "d=@A@; D=@O@; find $d -name x"),
    (BASH, "d=@A@; find ${d%/} -name x"),
    (BASH, "d=@A@; find \"${d:-/tmp}\" -name x"),
    (BASH, "d=@A@ e=1; find $d -name x"),
    (BASH, "if true; then d=@A@; fi; find $d -name x"),
    (BASH, "for i in 1; do d=@A@; done; find $d -name x"),
    (BASH, "d=@A@ # a note" + NL + "find $d -name x"),
]
VARIABLE_ALLOW = [
    (PS, "$p='@ON@'; Get-ChildItem $p -Recurse"),
    (PS, "$p='@AN@'; Get-ChildItem $p -Directory"),
    (PS, "$p='@AN@'; Write-Output $p"),
    (PS, "$p='@AN@'; $p='@ON@'; Get-ChildItem $p -Recurse"),
    (PS, "foreach ($d in '@ON@') { Get-ChildItem $d -Recurse }"),
    (BASH, "d=@O@; find $d -name x"),
    (BASH, "d=@A@; echo $d"),
    (BASH, "d=@A@; d=@O@; find $d -name x"),
    (BASH, "for d in @O@; do find $d -name x; done"),
    (BASH, "d=@A@; ls $d"),
    (BASH, "D=@A@; d=@O@; find $d -name x"),
    (BASH, "d=@A@; d=$(mktemp -d); find $d -name x"),
    (BASH, "d=@A@; unset d; find $d -name x"),
    (PS, "$ds = Get-ChildItem '@ON@'; foreach ($d in $ds) { Get-ChildItem $d.FullName }"),
    (PS, "$dirs = '@ON@'; foreach ($d in $dirs) { Get-ChildItem $d -Recurse }"),
    (PS, "$d='@AN@'; foreach ($d in '@ON@') { Get-ChildItem $d -Recurse }"),
    (BASH, "n=$(ls @A@ | wc -l); for i in $n; do echo $i; done"),
    (PS, "$p = '@AN@'; $p = '@ON@'; $p += '/Public'; Get-ChildItem $p -Recurse"),
    (PS, "$p = '@AN@'; Remove-Variable p; Get-ChildItem $p -Recurse"),
    (PS, "$p = '@AN@'; Remove-Variable q,p; Get-ChildItem $p -Recurse"),
    (BASH, "ls @A@ | wc -l | while read n; do echo $n; done"),
    (PS, "$p = '@AN@'; $p += 'x'; $p = '@ON@'; Get-ChildItem $p -Recurse"),
]


@pytest.mark.parametrize("tool,cmd", VARIABLE_DENY, ids=[c.replace(NL, " / ") for _, c in VARIABLE_DENY])
def test_a_root_held_in_a_variable_is_read_when_it_is_recursed_in_the_next_statement(fake, tool, cmd):
    assert _denied(fake, tool, cmd) is not None, "not denied: " + _spell(fake, cmd)


@pytest.mark.parametrize("tool,cmd", VARIABLE_ALLOW, ids=[c for _, c in VARIABLE_ALLOW])
def test_a_variable_that_does_not_hold_a_root_or_is_not_recursed_stays_allowed(fake, tool, cmd):
    assert _denied(fake, tool, cmd) is None, "wrongly denied: " + _spell(fake, cmd)


# finding 5: recursive calls inside embedded scripts
EMBEDDED_DENY = [
    (BASH, "python -c \"import os; [print(r) for r in os.fwalk('@AP@')]\""),
    (BASH, "python -c \"from pathlib import Path; [print(p) for p in Path('@AP@').walk()]\""),
    (BASH, "python -c \"import glob; print(glob.glob('@AP@/**', recursive=True))\""),
    (BASH, "python -c \"import glob; g = glob.glob('@AP@/**', recursive=True)\""),
    (BASH, "node -e \"require('fs').readdir('@AP@',{recursive:true},(e,f)=>console.log(f))\""),
    (BASH, "node -e \"console.log(require('fs').globSync('**',{cwd:'@AP@'}))\""),
    (PS, "[IO.Directory]::GetFiles('@AN@','*',1)"),
    (PS, "(New-Object IO.DirectoryInfo '@AN@').EnumerateFiles('*',1)"),
    (BASH, "python -c \"from pathlib import Path; last = Path('@AP@'); print(list(last.walk()))\""),
    (PS, "[IO.Directory]::GetFiles('@AN@','*',[IO.EnumerationOptions]@{RecurseSubdirectories=$true})"),
    (PS, "[IO.Directory]::EnumerateFiles('@AN@','*',[IO.SearchOption]::AllDirectories)"),
]
EMBEDDED_ALLOW = [
    (BASH, "python -c \"import os; [print(r) for r in os.fwalk('@OP@')]\""),
    (BASH, "python -c \"import glob; print(glob.glob('@OP@/**', recursive=True))\""),
    (BASH, "python -c \"import os; print(os.listdir('@AP@'))\""),
    (BASH, "python -c \"import ast; print(os.path.isdir('@AP@'), list(ast.walk(ast.parse('1'))))\""),
    (BASH, "python -c \"import glob; print(glob.glob('@AP@/*.md'))\""),
    (BASH, "node -e \"console.log(require('fs').readdirSync('@AP@'))\""),
    (BASH, "node -e \"console.log(require('fs').globSync('**',{cwd:'@OP@'}))\""),
    (PS, "[IO.Directory]::GetFiles('@AN@','*',0)"),
    (PS, "[IO.Directory]::GetFiles('@ON@','*',1)"),
]


@pytest.mark.parametrize("tool,cmd", EMBEDDED_DENY, ids=[c for _, c in EMBEDDED_DENY])
def test_a_recursive_call_inside_an_embedded_script_over_the_folders_parent_is_denied(fake, tool, cmd):
    assert _denied(fake, tool, cmd) is not None, "not denied: " + _spell(fake, cmd)


@pytest.mark.parametrize("tool,cmd", EMBEDDED_ALLOW, ids=[c for _, c in EMBEDDED_ALLOW])
def test_an_embedded_script_that_does_not_recurse_over_the_folders_parent_stays_allowed(fake, tool, cmd):
    assert _denied(fake, tool, cmd) is None, "wrongly denied: " + _spell(fake, cmd)


# finding 6: list the parent, then open each entry
LIST_THEN_DESCEND_DENY = [
    (BASH, "find @A@ -maxdepth 1 | xargs ls"),
    (BASH, "find @A@ -maxdepth 1 -type d | while read d; do cat \"$d/x\"; done"),
    (BASH, "ls @A@ | while read d; do ls \"@A@/$d\"; done"),
    (BASH, "for d in $(ls @A@); do ls \"@A@/$d\"; done"),
    (BASH, "for d in `ls @A@`; do ls \"@A@/$d\"; done"),
    (PS, "foreach ($d in Get-ChildItem '@AN@' -Directory) { Get-ChildItem $d.FullName }"),
    (PS, "foreach ($d in (Get-ChildItem '@AN@')) { Get-Content $d.FullName }"),
    (PS, "$ds = Get-ChildItem '@AN@' -Directory; foreach ($d in $ds) { Get-ChildItem $d.FullName }"),
    (BASH, "ds=$(ls @A@); for d in $ds; do ls \"@A@/$d\"; done"),
    # third QA pass: a loop after then/do, a backtick-newline in Bash, a loop in a group after the listing
    (BASH, "if true; then for d in $(ls @A@); do ls \"@A@/$d\"; done; fi"),
    (BASH, "while true; do for d in $(ls @A@); do cat \"@A@/$d/x\"; done; done"),
    (BASH, "x=`ls @A@`" + NL + "for d in $x; do ls \"@A@/$d\"; done"),
    (BASH, "for d in `ls @A@`" + NL + "do ls \"@A@/$d\"" + NL + "done"),
    (BASH, "ls @A@ | (while read d; do cat \"@A@/$d\"; done)"),
    (BASH, "ls @A@ | { while read d; do cat \"@A@/$d\"; done; }"),
]
LIST_THEN_DESCEND_ALLOW = [
    (BASH, "ls @A@ | head -3"),
    (BASH, "find @A@ -maxdepth 1 | sort"),
    (BASH, "ls @A@ | wc -l"),
    (BASH, "ls @A@ | xargs echo"),
    (BASH, "for d in $(ls @A@ | wc -l); do echo $d; done"),
    (PS, "foreach ($d in (Get-ChildItem '@AN@' | Measure-Object)) { Write-Output $d.Count }"),
    (BASH, "ls @O@ | while read d; do ls \"@O@/$d\"; done"),
    (BASH, "for d in $(ls @O@); do ls \"@O@/$d\"; done"),
    (PS, "foreach ($d in Get-ChildItem '@ON@' -Directory) { Get-ChildItem $d.FullName }"),
    (PS, "Get-ChildItem '@AN@' -Directory | Select-Object Name"),
]


@pytest.mark.parametrize("tool,cmd", LIST_THEN_DESCEND_DENY, ids=[c for _, c in LIST_THEN_DESCEND_DENY])
def test_listing_the_folders_parent_and_then_opening_each_entry_is_denied(fake, tool, cmd):
    assert _denied(fake, tool, cmd) is not None, "not denied: " + _spell(fake, cmd)


@pytest.mark.parametrize("tool,cmd", LIST_THEN_DESCEND_ALLOW, ids=[c for _, c in LIST_THEN_DESCEND_ALLOW])
def test_a_names_only_listing_and_other_folders_entries_stay_allowed(fake, tool, cmd):
    assert _denied(fake, tool, cmd) is None, "wrongly denied: " + _spell(fake, cmd)


# finding 7: a drive alias aimed at a folder above the protected one, written with a .. climb or a relative target
ALIAS_DENY = [
    (PS, "subst X: @AN@" + BS + "..", None),
    (PS, "New-PSDrive -Name X -PSProvider FileSystem -Root @AN@" + BS + "..", None),
    (PS, "cmd /c mklink /J C:" + BS + "tmp" + BS + "q @AN@" + BS + "..", None),
    (PS, "New-Item -ItemType Junction -Path C:" + BS + "tmp" + BS + "q -Target @AN@" + BS + "..", None),
    (PS, "subst X: .", "work"),
    (PS, "New-Item -ItemType SymbolicLink -Path C:" + BS + "tmp" + BS + "q -Target ..", "work"),
]
ALIAS_ALLOW = [
    (PS, "subst X: @ON@", None),
    (PS, "subst X: .", "other"),
    (BASH, "git grep mklink -- ..", "other"),
    (BASH, "git grep -n subst -- .", "work"),
    (PS, "New-PSDrive -Name X -PSProvider FileSystem -Root @ON@", None),
    (PS, "cmd /c mklink /J C:" + BS + "tmp" + BS + "q @ON@", None),
]


def _alias_cwd(fake, which):
    return {None: fake.elsewhere, "work": fake.work, "other": fake.other}[which]


@pytest.mark.parametrize("tool,cmd,cwd", ALIAS_DENY, ids=[c for _, c, _ in ALIAS_DENY])
def test_a_drive_alias_or_junction_aimed_above_the_folder_is_denied_however_the_target_is_spelled(fake, tool, cmd, cwd):
    assert _denied(fake, tool, cmd, cwd=_alias_cwd(fake, cwd)) is not None, "not denied: " + _spell(fake, cmd)


@pytest.mark.parametrize("tool,cmd,cwd", ALIAS_ALLOW, ids=[c for _, c, _ in ALIAS_ALLOW])
def test_a_drive_alias_aimed_somewhere_that_cannot_reach_the_folder_stays_allowed(fake, tool, cmd, cwd):
    assert _denied(fake, tool, cmd, cwd=_alias_cwd(fake, cwd)) is None, "wrongly denied: " + _spell(fake, cmd)


def _fresh_module(name):
    spec = importlib.util.spec_from_file_location(name, MODULE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_a_variable_value_is_kept_only_when_it_is_short_plain_text():
    mod = _fresh_module("pfg_values")
    assert mod._bash_value("x" * 1100) is None and mod._bash_value("a" * 1000) == "a" * 1000
    for bad in ("a&b", "a|b", "a;b", "a$(x)", "a`x`", "a{b}", "a(b)", "a<b"):
        assert mod._bash_value(bad) is None, bad
    assert mod._bash_value("\"/c/x y\"/z") == "/c/x y/z"
    assert mod._ps_value("'" + "x" * 1100 + "'") is None
    for bad in ("'a;b'", "'a&b'", "\"a$b\"", "'a','b;c'", "Get-Item x", "(Get-Location).Path"):
        assert mod._ps_value(bad) is None, bad
    assert mod._ps_value("'C:\\x', 'D:\\y'") == "'C:\\x','D:\\y'" and mod._ps_value("'C:\\x'") == "C:\\x"


def test_the_expansions_of_one_command_share_one_budget_and_past_it_the_command_is_denied(fake):
    """A harmless command that expands 1 KB values 12 times (12 KB, past the 8 KB budget) is not read and is denied; 6 times is fine.
    Fourth QA pass: heredoc bodies and the decoded view of the same call draw on the same budget, they do not start a new one."""
    mod = _fresh_module("pfg_budget")
    argv = ["--config", str(fake.cfg)]
    cmd = lambda n: "p=" + "x" * 1000 + "; " + "; ".join(["echo $p"] * n)
    assert mod.evaluate(BASH, {"command": cmd(12)}, str(fake.elsewhere), cmd(12), argv, env=fake.env) is not None
    assert mod.evaluate(BASH, {"command": cmd(6)}, str(fake.elsewhere), cmd(6), argv, env=fake.env) is None
    body = lambda n: "bash <<E%d\np=%s; %s\nE%d\n" % (n, "x" * 1000, "; ".join(["echo $p"] * 5), n)
    two = body(1) + body(2)                             # 5 KB per body: each fits, together they do not
    assert mod.evaluate(BASH, {"command": two}, str(fake.elsewhere), two, argv, env=fake.env) is not None
    assert mod.evaluate(BASH, {"command": body(1)}, str(fake.elsewhere), body(1), argv, env=fake.env) is None
    # a padding statement ahead of the real one must not switch the variable tracking off for the rest of the command
    pad = "p=" + "x" * 1000 + "; " + "; ".join(["echo $p"] * 40) + "; a=@A@; find $a -name x"
    assert _denied(fake, BASH, pad) is not None


def test_a_short_command_that_expands_a_long_value_many_times_is_denied_quickly(fake):
    """Fourth QA pass: a 1,020 character value used 12 times inside heredoc bodies (13 KB, judged inline) took 85 s; one statement
    with nested $( ) took 28 s. Now the expansions share an 8 KB budget and a call over 2 KB that uses a variable is judged by the
    child process, so the call is denied well inside the hook's timeout."""
    import time
    value = ("for d in " * 120)[:1020]
    bodies = "".join("bash <<E%d\na=\"%s\"; echo %s\nE%d\n" % (i, value, "$a" * 31, i) for i in range(12))
    one = "a=\"%s\"; echo $(echo $(echo $(echo %s))); echo $'\\x41'" % (value, "$a" * 32)
    for cmd in (bodies + "find @A@ -name x", one + "; find @A@ -name x"):
        start = time.time()
        assert _denied(fake, BASH, cmd) is not None
        assert time.time() - start < 25, "took %.1f s" % (time.time() - start)


def test_a_value_made_of_shell_syntax_cannot_make_the_analysis_quadratic(fake):
    """QA of the fourth round (second pass): b0="x&x&...x&" re-parsed as commands took 89 s for 1.3 KB; such a value is not kept."""
    import time
    value = "x&" * 500
    cmd = "b0=\"%s\"; echo %s; echo %s; echo %s; find @A@ -name x" % (value, "$b0" * 32, "$b0" * 32, "$b0" * 32)
    start = time.time()
    assert _denied(fake, BASH, cmd) is not None
    assert time.time() - start < 15, "took %.1f s" % (time.time() - start)


@pytest.mark.parametrize("cmd", ["for d in x" + " " * 90000 + "y; do :; done; find @A@ -name x",
                                 "$a = x" + " " * 90000 + "y; Get-ChildItem '@AN@' -Recurse"],
                         ids=["bash-for-loop", "powershell-assignment"])
def test_a_long_run_of_spaces_in_a_loop_or_assignment_does_not_stall_the_hook(fake, cmd):
    import time
    start = time.time()
    assert _denied(fake, PS if cmd.startswith("$") else BASH, cmd) is not None
    assert time.time() - start < 15, "took %.1f s" % (time.time() - start)


def test_a_call_the_guard_cannot_read_in_time_is_denied_not_left_to_the_hook_timeout(fake):
    """Third QA pass: text matching has shapes that run for minutes inside one regex call, and a hook that times out lets the
    call through. A big call is judged by a child process that is killed at the budget; the call is then denied."""
    import time
    mod = _fresh_module("pfg_budget_child")
    mod._CHILD_ABOVE, mod._ANALYSIS_BUDGET_S = 0, 3.0
    argv = ["--config", str(fake.cfg)]
    slow = "a=1; " + "${a " * 6000                     # an unclosed bracket per command position: quadratic, about 9 s on its own
    start = time.time()
    verdict = mod.evaluate(BASH, {"command": slow}, str(fake.elsewhere), slow, argv, env=fake.env)
    assert verdict is not None and "could not finish reading" in verdict
    assert time.time() - start < 12, "took %.1f s" % (time.time() - start)


@windows_only
def test_the_child_process_dies_with_a_hook_that_is_killed(fake):
    """Fourth QA pass: a hook killed mid-call (an interrupt, the harness's own timeout) left its --judge child running for minutes.
    On Windows the child is put in a job object that is closed with the hook."""
    import time
    slow = "a=1; " + "${a " * 15000                                   # about 60 KB and 50 s of analysis: the child is still busy at 4 s
    payload = json.dumps({"tool_name": BASH, "tool_input": {"command": slow}, "cwd": str(fake.elsewhere)})
    hook = subprocess.Popen([sys.executable, str(HOOK), "--config", str(fake.cfg)], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=_clean_env(fake.env))
    hook.stdin.write(payload.encode())
    hook.stdin.close()
    time.sleep(4)
    query = "(Get-CimInstance Win32_Process -Filter 'ParentProcessId=%d').ProcessId" % hook.pid
    kids = subprocess.run(["powershell", "-NoProfile", "-Command", query], capture_output=True, text=True).stdout.split()
    try:
        assert kids, "the hook had no child process after 4 s (the call was not routed to the child)"
        hook.kill()
        hook.wait()
        time.sleep(2)
        alive = subprocess.run(["tasklist", "/FI", "PID eq %s" % kids[0], "/NH"], capture_output=True, text=True).stdout
        assert "python" not in alive.lower(), "the child outlived the hook: " + alive
    finally:
        hook.kill()
        for pid in kids:
            subprocess.run(["taskkill", "/PID", pid, "/T", "/F"], capture_output=True)


def test_a_big_call_gets_the_same_verdict_from_the_child_process_as_inline(fake):
    mod = _fresh_module("pfg_child_same")
    argv = ["--config", str(fake.cfg)]
    pad = " " * 20000
    for cmd, denied in [("find %s -name x%s-print" % (_above(fake), pad), True), ("echo hello%sworld" % pad, False),
                        ("ls Private Notes%s", True)]:
        cmd = cmd % pad if "%s" in cmd else cmd
        inline = mod._evaluate_inner(BASH, {"command": cmd}, str(fake.elsewhere), cmd, argv, fake.env)
        via_child = mod.evaluate(BASH, {"command": cmd}, str(fake.elsewhere), cmd, argv, env=fake.env)
        assert (inline is not None) == denied == (via_child is not None), cmd[:60]
        assert inline == via_child


@pytest.mark.parametrize("make", [lambda n: ("ls @A@|" * n) + "cat", lambda n: "find @A@ -name x" + " " * (n * 4) + "-print"],
                         ids=["many-pipe-segments", "denied-command-padded-with-spaces"])
def test_long_padded_calls_are_denied_quickly_through_the_hook(fake, make):
    """Third QA pass: a rooted listing rescanned every later pipe segment, and the comment strip was quadratic on a run of
    spaces; 130 KB or 260 KB of padding then outlasted the hook's timeout, which lets the call through."""
    import time
    start = time.time()
    assert _denied(fake, BASH, make(20000)) is not None
    assert time.time() - start < 20, "took %.1f s" % (time.time() - start)


@pytest.mark.parametrize("tool", [BASH, PS])
def test_variables_that_grow_ten_fold_per_step_cannot_stall_the_hook(fake, tool):
    """QA of the fourth round: b1=$b0 x10 ... b6=$b5 x10 is about 370 characters and expands to 10^7 if every level is built; the
    hook has a 60 second timeout that lets the command through. Values are capped, so the command is judged in well under that."""
    import time
    if tool == BASH:
        steps = ["b0=xxxxxxxxxx"] + ["b%d=%s" % (i, "$b%d" % (i - 1) * 10) for i in range(1, 7)]
        cmd = "; ".join(steps) + "; c=" + "$b6" * 6 + "; find @A@ -name x"
    else:
        steps = ["$b0='xxxxxxxxxx'"] + ["$b%d=\"%s\"" % (i, "$b%d" % (i - 1) * 10) for i in range(1, 7)]
        cmd = "; ".join(steps) + "; $c=\"" + "$b6" * 6 + "\"; Get-ChildItem '@AN@' -Recurse"
    start = time.time()
    verdict = _denied(fake, tool, cmd)
    assert time.time() - start < 15, "took %.1f s" % (time.time() - start)
    assert verdict is not None, "not denied: " + _spell(fake, cmd)


# ---------------------------------------------------------------- path-qualified entries, optional paths, 8.3 short names
# A config entry may be {"path": ..., "tail": N, "optional": true} (path-qualified entries).

def _entry(path, tail=None, optional=None):
    e = {"path": str(path)}
    if tail is not None:
        e["tail"] = tail
    if optional is not None:
        e["optional"] = optional
    return e


def _write_raw_cfg(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _forms_of(p):
    p = Path(p)
    out = [str(p), p.as_posix()]
    if WIN:
        out += [msys(p), "/mnt" + msys(p)]
    return out


class _PQ(object):
    """Fresh engine module plus a fake `Claude/personal/...` tree and a config of five object entries."""

    def __init__(self, tmp):
        self.mod = _fresh_module("pfg_pq_%s" % abs(hash(str(tmp))))
        self.tmp = tmp
        self.root = tmp / "Claude"
        self.personal = self.root / "personal"
        self.elsewhere = tmp / "elsewhere"
        self.elsewhere.mkdir()
        for d in ("app-one/work", "app-two/work/companion", "app-two/companion", "app-three/work",
                  "app-three/other", "app-four/work/exports"):
            (self.personal / d).mkdir(parents=True)
        (self.personal / "app-three/work/token.txt").write_text("x")
        (self.root / "work").mkdir()
        (self.root / "slm-eval" / "work").mkdir(parents=True)
        p = self.personal
        self.entries = [_entry(p / "app-two/work/companion", 2), _entry(p / "app-one/work", 2),
                        _entry(p / "app-three/work/token.txt", 3),
                        _entry(p / "app-four/work/events.jsonl", 3, True),
                        _entry(p / "app-four/work/token.txt", 3, True)]
        self.cfg = _write_raw_cfg(tmp / "cfg" / "protected-folders.json", json.dumps({"protected_folders": self.entries}))
        self.argv = ["--config", str(self.cfg)]

    def ev(self, tool, cmd, cwd=None):
        return self.mod.evaluate(tool, {"command": cmd}, str(cwd or self.elsewhere), cmd, self.argv, {})

    def grep(self, path=None, cwd=None, pattern="foo"):
        ti = {"pattern": pattern, "output_mode": "files_with_matches"}
        if path is not None:
            ti["path"] = str(path)
        command = "\n".join(str(ti.get(k) or "") for k in ("path", "glob", "pattern"))
        return self.mod.evaluate("Grep", ti, str(cwd or self.elsewhere), command, self.argv, {})

    def glob(self, pattern, path=None, cwd=None):
        ti = {"pattern": pattern}
        if path is not None:
            ti["path"] = str(path)
        command = "\n".join(str(ti.get(k) or "") for k in ("path", "glob", "pattern"))
        return self.mod.evaluate("Glob", ti, str(cwd or self.elsewhere), command, self.argv, {})


@pytest.fixture
def pq(tmp_path):
    return _PQ(tmp_path)


# ---- config parsing
def _problem(mod, tmp_path, text):
    cfg = _write_raw_cfg(tmp_path / "bad" / "protected-folders.json", text)
    folders, problem = mod.load_folders(["--config", str(cfg)], {})
    return folders, problem, cfg


def test_object_entries_load_with_their_tail_optional_and_scoped_flags(pq):
    folders, problem = pq.mod.load_folders(pq.argv, {})
    assert problem is None and len(folders) == 5
    assert [f.tail for f in folders] == [2, 2, 3, 3, 3]
    assert [f.optional for f in folders] == [False, False, False, True, True]
    assert all(f.scoped for f in folders)
    folders, problem, missing = pq.mod.load_folders_ex(pq.argv, {})
    assert problem is None and len(missing) == 2
    assert all("events.jsonl" in m or "token.txt" in m for m in missing)


def test_a_string_entry_is_unchanged_tail_one_required_and_not_scoped(fake):
    mod = _fresh_module("pfg_strings")
    folders, problem = mod.load_folders(["--config", str(fake.cfg)], {})
    assert problem is None and len(folders) == 1
    f = folders[0]
    assert (f.tail, f.optional, f.scoped) == (1, False, False)
    assert mod.Folder("x", "j:", ("a",)).tail == 1          # every old three-field construction still works


@pytest.mark.parametrize("text", [
    '{"protected_folders": [{"path": "@P@", "color": "red"}]}',                                  # unknown key
    '{"protected_folders": [{"path": "@P@", "tail": 1, "tail": 2}]}',                            # duplicate key in an entry
    '{"protected_folders": [], "protected_folders": ["@P@"]}',                                  # duplicate top-level key
    '{"protected_folders": ["@P@"], "protected_folders": []}',                                  # a second, empty list turns the guard off
    '{"protected_folders": [{"path": "@P@", "optional": false, "optional": true}]}',
    '{"protected_folders": [{"path": "@P@", "tail": true}]}',                                    # bool is an int in Python
    '{"protected_folders": [{"path": "@P@", "tail": 0}]}',
    '{"protected_folders": [{"path": "@P@", "tail": 99}]}',                                      # more than the path has
    '{"protected_folders": [{"path": "@P@", "tail": 1.5}]}',
    '{"protected_folders": [{"path": "@P@", "tail": "2"}]}',
    '{"protected_folders": [{"tail": 1}]}',                                                      # missing path
    '{"protected_folders": [{"path": 5}]}',                                                      # non-string path
    '{"protected_folders": [{"path": ""}]}',
    '{"protected_folders": [5]}',                                                                # neither a string nor an object
    '{"protected_folders": [["@P@"]]}',
    '{"protected_folders": [null]}',
    '{"protected_folders": [{"path": "@P@", "optional": "yes"}]}',
    '{"protected_folders": [{"path": "@P@", "optional": 1}]}',
    '{"protected_folders": [{"path": "relative/dir"}]}',                                         # the old path checks still apply to objects
    '{"protected_folders": [{"path": "@P@-missing"}]}',                                          # required and absent
])
def test_a_bad_entry_is_a_config_problem_that_names_the_file(pq, tmp_path, text):
    target = json.dumps(str(pq.personal / "app-one" / "work"))[1:-1]
    folders, problem, cfg = _problem(pq.mod, tmp_path, text.replace("@P@", target))
    assert problem is not None, text
    assert str(cfg) in problem
    assert folders == []


def test_an_optional_entry_that_is_missing_is_accepted_and_a_required_one_is_not(pq, tmp_path):
    gone = json.dumps(str(pq.personal / "nope" / "work" / "x.txt"))[1:-1]
    _, problem, _ = _problem(pq.mod, tmp_path, '{"protected_folders": [{"path": "%s", "tail": 3, "optional": true}]}' % gone)
    assert problem is None
    _, problem, _ = _problem(pq.mod, tmp_path, '{"protected_folders": [{"path": "%s", "tail": 3}]}' % gone)
    assert problem is not None and "does not exist" in problem


# ---- rule 0 for a tail-qualified entry
RULE0_DENY = [
    "cat personal/app-two/work/companion/x",
    "cat work/companion/identity.md",
    "cat app-two/work/companion",
    'type "work\\companion"',
    "cat 'work\\companion\\x'",
    "cat work\\companion/x",
    "cat work/./companion/x",
    "cat work\\x\\..\\companion",
    "cat work//companion/x",
    "cat WORK/Companion/x",
    "cat app-one/work/x",
    "cat personal/app-one/work",
    "cat app-three/work/token.txt",
    "cat app-four/work/events.jsonl",
    "cat app-four/work/token.txt",
    "cat $'work\\x2fcompanion/x'",
    "cat work/companion-v2",                    # a name that merely begins with the tail matches, as the last-name rule always did
    "cat app-three/work/token.txt.example",
]
RULE0_ALLOW = [
    "cat slm-eval/work/x",
    "cat personal/app-two/companion/loop.py",
    'git commit -m "work on companion"',
    "echo work",
    "echo companion",
    "ls work",
    "cat app-four/work/exports/x.json",
    "cat other-tool/work/token.txt",
    "cat token.txt",
]


@pytest.mark.parametrize("cmd", RULE0_DENY)
def test_a_tail_entry_is_denied_by_name_in_every_common_spelling(pq, cmd):
    assert pq.ev(BASH, cmd) is not None, "not denied: " + cmd


@pytest.mark.parametrize("cmd", RULE0_ALLOW)
def test_a_tail_entry_leaves_look_alikes_and_bare_words_alone(pq, cmd):
    assert pq.ev(BASH, cmd) is None, "wrongly denied: " + cmd


def test_a_tail_entry_is_denied_by_its_absolute_path_in_every_slash_style(pq):
    for p in (pq.personal / "app-two/work/companion", pq.personal / "app-one/work",
              pq.personal / "app-three/work/token.txt"):
        for form in _forms_of(p):
            assert pq.ev(BASH, "cat %s/x" % form) is not None, form
            assert pq.ev(PS, "Get-Content '%s'" % form) is not None, form
    for form in _forms_of(pq.root / "work") + _forms_of(pq.root / "slm-eval" / "work"):
        assert pq.ev(BASH, "ls %s" % form) is None, form


def test_the_name_rule_of_a_tail_entry_reads_a_grep_pattern_and_a_glob_like_any_other_text(pq):
    assert pq.grep(pattern="app-two/work/companion") is not None
    assert pq.grep(pattern="work") is None
    assert pq.glob("**/work/companion/*") is not None


# ---- optional entries still protect by name
def test_an_optional_entry_protects_by_name_while_its_path_is_missing(pq):
    assert not (pq.personal / "app-four/work/events.jsonl").exists()
    assert pq.ev(BASH, "cat personal/app-four/work/events.jsonl") is not None
    assert pq.ev(BASH, "mkdir -p x/app-four/work && cat x/app-four/work/token.txt") is not None
    assert pq.ev(BASH, "cat personal/app-four/work/exports/a.json") is None


# ---- ancestors stop at the entry's own parent (S1)
ANCESTOR_ALLOW = [
    (BASH, "rg -n foo"), (BASH, "find . -name x"), (BASH, "grep -rn foo . --include=*.md"), (BASH, "ls -R"),
    (PS, "Get-ChildItem -Recurse"), (PS, "gci . -r"), (BASH, "git status"),
]


@pytest.mark.parametrize("where", ["root", "personal"])
@pytest.mark.parametrize("tool,cmd", ANCESTOR_ALLOW, ids=[c for _, c in ANCESTOR_ALLOW])
def test_a_recursive_search_from_far_above_a_tail_entry_is_allowed(pq, where, tool, cmd):
    cwd = pq.root if where == "root" else pq.personal
    assert pq.ev(tool, cmd, cwd=cwd) is None, "wrongly denied: %s in %s" % (cmd, cwd)


@pytest.mark.parametrize("where", ["root", "personal"])
def test_grep_and_glob_from_far_above_a_tail_entry_are_allowed(pq, where):
    cwd = pq.root if where == "root" else pq.personal
    assert pq.grep(cwd=cwd) is None
    assert pq.grep(path=cwd, cwd=pq.elsewhere) is None
    for pattern in ("**/*.md", "**/NOTES.md", "*.md", "**/*.py"):
        assert pq.glob(pattern, cwd=cwd) is None, pattern
        assert pq.glob(pattern, path=cwd, cwd=pq.elsewhere) is None, pattern


def test_recursion_from_far_above_by_absolute_path_is_allowed(pq):
    for base in (pq.root, pq.personal):
        for form in _forms_of(base):
            assert pq.ev(BASH, "find %s -name x" % form) is None, form
            assert pq.ev(BASH, "rg -n foo %s" % form) is None, form
        assert pq.ev(PS, "Get-ChildItem %s -Recurse" % base) is None


RECURSE_DENY = [
    ("app-one", BASH, "rg -n foo"), ("app-one", BASH, "find . -name x"), ("app-one", PS, "Get-ChildItem -Recurse"),
    ("app-one", BASH, "grep -rn foo . --include=*.md"),
    ("app-two/work", BASH, "rg -n foo"),                 # the parent of app-two/work/companion
    ("app-three/work", BASH, "find . -name x"),   # the parent of the file entry
]


@pytest.mark.parametrize("sub,tool,cmd", RECURSE_DENY, ids=["%s %s" % (s, c) for s, _, c in RECURSE_DENY])
def test_recursion_from_the_entrys_own_parent_is_still_denied(pq, sub, tool, cmd):
    assert pq.ev(tool, cmd, cwd=pq.personal / sub) is not None


def test_grep_and_glob_from_the_entrys_own_parent_are_still_denied(pq):
    parent = pq.personal / "app-one"
    assert pq.grep(cwd=parent) is not None
    assert pq.grep(path=parent) is not None
    assert pq.glob("**/*.md", cwd=parent) is not None
    assert pq.glob("**/*.md", path=parent) is not None
    assert pq.grep(path=pq.personal / "app-two/work") is not None


def test_an_object_entry_with_tail_one_is_scoped_too(fake):
    mod = _fresh_module("pfg_obj_tail1")
    cfg = _write_raw_cfg(fake.tmp / "cfg2" / "protected-folders.json", json.dumps({"protected_folders": [_entry(fake.folder)]}))
    argv = ["--config", str(cfg)]

    def grep(path):
        ti = {"pattern": "x", "path": str(path)}
        return mod.evaluate("Grep", ti, str(fake.elsewhere), "\n".join([str(path), "", "x"]), argv, {})
    assert grep(fake.work) is not None                     # the parent
    assert grep(fake.home) is None and grep(fake.tmp) is None      # above the parent: not an ancestor of a scoped entry
    assert mod.evaluate(BASH, {"command": "ls Private Notes"}, str(fake.elsewhere), "ls Private Notes", argv, {}) is not None


# ---- containment (S2)
def _cwd_cases(pq):
    p = pq.personal
    return [
        (p / "app-two/work", BASH, "cat companion/identity.md"),
        (p / "app-one", BASH, "cat work/token.txt"),
        (p / "app-one", BASH, "ls work"),
        (p / "app-one", PS, "Get-Content work\\x.txt"),
        (p / "app-three", BASH, "cat work/token.txt"),
        (p / "app-three/work", BASH, "cat token.txt"),
        (pq.root, BASH, "cd personal/app-one && ls work"),
        (pq.root, BASH, "cd personal/app-one/work; cat x"),
        (p / "app-one/work", BASH, "cat x.txt"),
        (p / "app-two/work/companion", BASH, "cat identity.md"),
        (p / "app-one", BASH, "cat ./work/x"),
        (p / "app-one/work", BASH, "cat ../work/x"),
        (p / "app-one", PS, "cd work; Get-Content x"),
        (p / "app-one", BASH, "bash -c 'cat work/x'"),
    ]


def test_a_relative_word_that_lands_inside_a_tail_entry_is_denied(pq):
    for cwd, tool, cmd in _cwd_cases(pq):
        assert pq.ev(tool, cmd, cwd=cwd) is not None, "not denied: %s (cwd %s)" % (cmd, cwd)


def test_a_relative_word_that_stays_outside_a_tail_entry_is_allowed(pq):
    p = pq.personal
    for cwd, tool, cmd in [
        (p / "app-two", BASH, "cat companion/loop.py"),
        (p / "app-two", BASH, "ls companion"),
        (p / "app-one", BASH, "ls"),
        (p / "app-three", BASH, "cat other/x"),
        (p / "app-three/work", BASH, "ls"),
        (p / "app-four/work", BASH, "cat exports/x.json"),
        (pq.root, BASH, "ls work"),                          # the day-job repo
        (pq.root, BASH, "cd slm-eval && ls work"),
        (pq.root, BASH, "git commit -m 'work on companion'"),
    ]:
        assert pq.ev(tool, cmd, cwd=cwd) is None, "wrongly denied: %s (cwd %s)" % (cmd, cwd)


def test_grep_and_glob_that_land_inside_a_tail_entry_are_denied(pq):
    p = pq.personal
    assert pq.glob("work/*", path=p / "app-one") is not None
    assert pq.glob("work/*", cwd=p / "app-one") is not None
    assert pq.glob("*", path=p / "app-one/work") is not None
    assert pq.glob("*.txt", path=p / "app-three/work") is not None    # a wildcard that reaches the file entry
    assert pq.glob("*.md", path=p / "app-three/work") is None
    assert pq.grep(path=p / "app-one/work") is not None
    assert pq.grep(cwd=p / "app-one/work") is not None
    assert pq.grep(path=p / "app-two/work/companion") is not None
    assert pq.grep(path=p / "app-two/companion") is None
    assert pq.glob("**/*.md", path=pq.root / "slm-eval") is None


def test_containment_does_not_apply_to_a_plain_string_entry(fake):
    mod = _fresh_module("pfg_contain_string")
    argv = ["--config", str(fake.cfg)]
    cmd = "ls Public"
    assert mod.evaluate(BASH, {"command": cmd}, str(fake.work), cmd, argv, {}) is None


# ---- through the real hook, once
def test_the_hook_denies_a_tail_entry_and_leaves_the_day_job_alone(pq):
    for cmd, cwd, denied in [("cat work/companion/x", pq.elsewhere, True), ("cat slm-eval/work/x", pq.elsewhere, False),
                             ("cat work/token.txt", pq.personal / "app-one", True),
                             ("rg -n foo", pq.root, False), ("rg -n foo", pq.personal / "app-one", True)]:
        reason = run_hook(BASH, cmd, cfg=pq.cfg, cwd=str(cwd), env={})
        assert (reason is not None) == denied, cmd + " in " + str(cwd)
    assert run_hook("Grep", cfg=pq.cfg, cwd=str(pq.root), env={}, tool_input={"pattern": "x"}) is None
    assert run_hook("Glob", cfg=pq.cfg, cwd=str(pq.root), env={}, tool_input={"pattern": "**/*.md"}) is None


# ---- 8.3 short names (S3)
def _short_stub(mapping):
    """A stand-in for the guard's short-path lookup: the given path with each long segment swapped for its short one."""
    def short(path):
        return os.sep.join(mapping.get(seg, seg) for seg in re.split(r"[\\/]", path))
    return short


def test_short_spellings_are_matched_in_every_layer_with_a_stubbed_lookup(tmp_path):
    mod = _fresh_module("pfg_short_stub")
    base = tmp_path / "Claude" / "personal"
    (base / "App Three" / "Work Files").mkdir(parents=True)
    (tmp_path / "elsewhere").mkdir()
    cfg = _write_raw_cfg(tmp_path / "cfg" / "protected-folders.json",
                         json.dumps({"protected_folders": [_entry(base / "App Three" / "Work Files", 2)]}))
    argv = ["--config", str(cfg)]
    mod._short_form = _short_stub({"App Three": "PARTNE~1", "Work Files": "WORKFI~1"})

    def ev(tool, cmd, cwd=None):
        return mod.evaluate(tool, {"command": cmd}, str(cwd or tmp_path / "elsewhere"), cmd, argv, {})
    short_parent = base / "PARTNE~1"
    assert ev(BASH, "cat PARTNE~1/WORKFI~1/x") is not None            # both short
    assert ev(BASH, "cat App\\ Three/WORKFI~1/x") is not None       # mixed long and short
    assert ev(BASH, "cat PARTNE~1/Work\\ Files/x") is not None
    assert ev(BASH, "cat partne~1/workfi~1") is not None             # any case
    assert ev(BASH, "cat PARTNE~1/other/x") is None
    ti = {"pattern": "x", "path": str(short_parent)}
    assert mod.evaluate("Grep", ti, str(tmp_path / "elsewhere"), "\n".join([str(short_parent), "", "x"]), argv, {}) is not None
    assert ev(BASH, "rg foo", cwd=short_parent) is not None           # the short parent as the cwd
    assert ev(BASH, "cat WORKFI~1/x", cwd=base / "App Three") is not None     # containment through a short spelling
    assert ev(BASH, "cat WORKFI~1/x", cwd=base) is None


def test_a_missing_path_gets_no_short_lookup(tmp_path):
    mod = _fresh_module("pfg_short_missing")
    calls = []
    mod._short_form = lambda path: calls.append(path) or path
    base = tmp_path / "Claude" / "personal"
    cfg = _write_raw_cfg(tmp_path / "cfg" / "protected-folders.json",
                         json.dumps({"protected_folders": [_entry(base / "Gone Dir" / "events.jsonl", 2, True)]}))
    mod.evaluate(BASH, {"command": "ls"}, str(tmp_path), "ls", ["--config", str(cfg)], {})
    assert calls == []


@windows_only
def test_short_names_on_a_real_c_drive_folder_are_matched():
    root = os.environ.get("LOCALAPPDATA")
    assert root and os.path.isdir(os.path.join(root, "Temp")), "no %LOCALAPPDATA%\\Temp to test short names on"
    base = Path(tempfile.mkdtemp(prefix="pfg-", dir=os.path.join(root, "Temp")))
    try:
        mod = _fresh_module("pfg_short_real")
        (base / "personal" / "App Three" / "Work Files").mkdir(parents=True)
        (base / "elsewhere").mkdir()
        target = base / "personal" / "App Three" / "Work Files"
        short = mod._short_form(str(target))
        assert short and short.lower() != str(target).lower(), "this volume made no short name for %s (got %r)" % (target, short)
        short_parts = re.split(r"[\\/]", short)
        sp_parent, sp_leaf = short_parts[-2], short_parts[-1]
        assert "~" in sp_parent and "~" in sp_leaf, short
        cfg = _write_raw_cfg(base / "cfg" / "protected-folders.json", json.dumps({"protected_folders": [_entry(target, 2)]}))
        argv = ["--config", str(cfg)]

        def ev(tool, cmd, cwd=None):
            return mod.evaluate(tool, {"command": cmd}, str(cwd or base / "elsewhere"), cmd, argv, {})
        assert ev(BASH, "cat %s/%s/x" % (sp_parent, sp_leaf)) is not None
        assert ev(BASH, "cat App\\ Three/%s/x" % sp_leaf) is not None
        assert ev(BASH, "cat %s/other/x" % sp_parent) is None
        parent_short = Path(short).parent
        ti = {"pattern": "x", "path": str(parent_short)}
        assert mod.evaluate("Grep", ti, str(base / "elsewhere"), "\n".join([str(parent_short), "", "x"]), argv, {}) is not None
    finally:
        shutil.rmtree(str(base), ignore_errors=True)


# ---------------------------------------------------------------- fix round 1 (Opus review of tasks 1 to 7)
def _fix_cases(pq):
    p = pq.personal
    psc, pic, lcw = p / "app-three", p / "app-one", p / "app-two/work"
    return {
        # 1: redirection targets, and the command word picked before redirections are dropped
        "redirect": [
            (psc, BASH, "cat <work/token.txt"), (psc, BASH, "t=$(< work/token.txt)"),
            (psc, BASH, "t=$(tr -d x <work/token.txt)"), (psc, BASH, "< work/token.txt cat"),
            (pic, BASH, "echo hi >work/x"), (pic, BASH, "echo hi > work/x"), (pic, BASH, "echo hi 2>work/x"),
            (pic, BASH, "echo hi >>work/x"),
        ],
        # 2: quotes and escapes the shell removes before the program sees the word
        "quotes": [
            (psc, BASH, 'cat "work"/token.txt'), (psc, BASH, 'cat work/"token.txt"'), (psc, BASH, "cat wo''rk/token.txt"),
            (psc, BASH, "cat wo\\rk/token.txt"), (lcw, BASH, "cat compan\\ion/x"), (psc, BASH, "cat 'work'/'token.txt'"),
        ],
        # 3: PowerShell -Param:value
        "psparam": [
            (psc, PS, "Get-Content -Path:work\\token.txt"), (psc, PS, "Get-Content -LiteralPath:work\\token.txt"),
            (pic, PS, "Get-ChildItem -Path:work"), (pic, BASH, "cat --file=work/x"),
        ],
        # 4: a wildcard word the shell expands into the entry
        "wild": [
            (psc, BASH, "cat work*/token.txt"), (psc, BASH, "cat work/tok*"), (lcw.parent, BASH, "cat */companion/identity.md"),
            (lcw.parent, BASH, "cat work/compan*/identity.md"), (pq.root, BASH, "cat personal/app-one/w*"),
            (pq.root, BASH, "cat personal/app-two/work/compan*/identity.md"), (pic, BASH, "ls */"),
            (psc, BASH, "ls work/?oken.txt"),
        ],
        # 5: Windows drops a trailing dot
        "dot": [
            (psc, PS, "gc work\\token.txt."), (psc, PS, "gc work.\\token.txt"), (pic, BASH, "cat work./x"),
            (pq.elsewhere, BASH, "cat personal/app-one/work./x"), (pq.elsewhere, PS, "gc personal\\app-one\\work.\\x"),
            (pq.elsewhere, BASH, "cat work./companion./x"),
        ],
    }


@pytest.mark.parametrize("group", ["redirect", "quotes", "psparam", "wild", "dot"])
def test_fix_round_one_words_that_land_inside_a_tail_entry_are_denied(pq, group):
    for cwd, tool, cmd in _fix_cases(pq)[group]:
        assert pq.ev(tool, cmd, cwd=cwd) is not None, "not denied: %s (cwd %s)" % (cmd, cwd)


def test_fix_round_one_look_alikes_stay_allowed(pq):
    p = pq.personal
    for cwd, tool, cmd in [
        (p / "app-three", BASH, "cat <other/x"), (p / "app-one", BASH, "echo hi >out.txt"),
        (p / "app-one", BASH, "git commit -m 'fix work stuff' 2>&1"), (p / "app-one", BASH, "echo hi 2>&1 >/dev/null"),
        (p / "app-three", BASH, 'cat "other"/x'), (p / "app-one", PS, "Get-ChildItem -Path:src"),
        (p / "app-one", BASH, "ls src/*"), (p / "app-one", BASH, "cat *.md"), (p / "app-three", BASH, "cat oth*/x"),
        (p / "app-one", BASH, "grep -n '*' src/a.py"), (pq.root, BASH, "ls */"), (pq.root, BASH, "cat slm-eval/work./x"),
    ]:
        assert pq.ev(tool, cmd, cwd=cwd) is None, "wrongly denied: %s (cwd %s)" % (cmd, cwd)


def test_fix_round_one_a_wildcard_word_adds_no_deny_for_a_string_only_config(fake):
    mod = _fresh_module("pfg_wild_string")
    argv = ["--config", str(fake.cfg)]
    for cwd in (fake.work, fake.home, fake.tmp, fake.other):
        for cmd in ("ls *", "ls */", "cat */x", "ls ../*", "cat <x", "cat 'Public'/x", "cat wo*/x"):
            hit = mod.evaluate(BASH, {"command": cmd}, str(cwd), cmd, argv, {})
            assert hit is None, "wrongly denied: %s in %s: %r" % (cmd, cwd, hit)


def test_fix_round_one_a_trailing_dot_in_a_name_is_matched_by_rule_zero(pq):
    for cmd in ("cat personal/app-one/work./x", "cat app-one./work/x", "cat personal/app-two/work./companion./x"):
        assert pq.ev(BASH, cmd) is not None, cmd


# ---- the 8.3 lookup's failure paths, and the glob layers reading short names (review item 13)
class _FakeK32(object):
    def __init__(self, fn):
        self.GetShortPathNameW = fn


def _short_form_with(monkeypatch, mod, fn):
    import ctypes
    monkeypatch.setattr(mod, "IS_WINDOWS", True)
    monkeypatch.setattr(ctypes, "WinDLL", lambda *a, **k: _FakeK32(fn), raising=False)
    return mod._short_form("C:\\some\\Long Path")


@windows_only
def test_short_form_gives_no_short_name_when_the_api_fails(monkeypatch):
    mod = _fresh_module("pfg_short_fail")

    def ok(path, buf, size):
        buf.value = "C:\\SOME\\LONGPA~1"
        return len("C:\\SOME\\LONGPA~1")
    assert _short_form_with(monkeypatch, mod, ok) == "C:\\SOME\\LONGPA~1"          # the control: a working API gives the name
    assert _short_form_with(monkeypatch, mod, lambda path, buf, size: 0) == ""        # the call failed
    assert _short_form_with(monkeypatch, mod, lambda path, buf, size: 5000) == ""     # the buffer was too small
    assert _short_form_with(monkeypatch, mod, lambda path, buf, size: 1024) == ""     # exactly the buffer size is "too small" too

    def boom(path, buf, size):
        raise OSError("no")
    assert _short_form_with(monkeypatch, mod, boom) == ""


def test_the_glob_layers_read_short_names(tmp_path):
    base = tmp_path / "Claude" / "personal"
    (base / "App Three" / "Work Files").mkdir(parents=True)
    (tmp_path / "elsewhere").mkdir()
    cfg = _write_raw_cfg(tmp_path / "cfg" / "protected-folders.json",
                         json.dumps({"protected_folders": [_entry(base / "App Three" / "Work Files", 2)]}))
    argv = ["--config", str(cfg)]
    with_short = _fresh_module("pfg_glob_short")
    with_short._short_form = _short_stub({"App Three": "PARTNE~1", "Work Files": "WORKFI~1"})
    without = _fresh_module("pfg_glob_noshort")
    without._short_form = lambda path: ""

    def glob(mod, pattern):
        return mod.evaluate("Glob", {"pattern": pattern, "path": str(base)}, str(tmp_path / "elsewhere"),
                            "\n".join([str(base), "", pattern]), argv, {})

    def text(mod, cmd):
        return mod.evaluate(BASH, {"command": cmd}, str(tmp_path / "elsewhere"), cmd, argv, {})
    # _covers_by_glob: only the short names can match these wildcard segments
    assert glob(with_short, "PARTNE~1/WORKFI~*") is not None
    assert glob(without, "PARTNE~1/WORKFI~*") is None
    # _name_glob_in: an absolute path whose last two segments are short-name wildcards
    cmd = "cat %s/PARTNE~1/WORKFI~*" % base.as_posix()
    assert text(with_short, cmd) is not None
    assert text(without, cmd) is None
