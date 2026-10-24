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
