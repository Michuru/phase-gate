# block-dangerous-commands

A `PreToolUse` hook that hard-blocks a short, deliberately narrow list of catastrophic Bash
commands, regardless of permission mode — a technical backstop for autonomous/auto modes,
where a soft "confirm before risky actions" convention gets skipped by design. It can also
keep Grep, Glob and shell searches out of folders you name (off until you name one; see
"Protecting a folder" below).

Blocks:
- `rm -rf` (or PowerShell `Remove-Item -Recurse -Force`) targeting a bare filesystem root
- `git push --force` (or `-f` / `--force-with-lease`) targeting `main`/`master`
- `git reset --hard` when the working tree actually has uncommitted changes to lose
- `git clean -f` when a dry run shows it would actually remove something
- a script passed through a Bash heredoc (`python - <<'EOF'`, `node <<EOF`, `bash <<EOF`,
  `cat > fix.py <<'EOF'`): backslashes and `$`/backtick get mangled and the failure is silent
  until the script runs. The message points at a script file or, on Windows, a PowerShell
  here-string piped to the interpreter. Heredocs for commit messages, notes, markdown and JSON
  are fine.
- with a protected folder configured: any call that names the folder, or that would search
  its way into it without naming it (see below)

Anything not matched here still goes through Claude Code's normal permission-prompt flow —
this hook only ever adds a stricter floor, never loosens the default. Pattern-matched on the
raw command string, not a real shell parser — best-effort, not a guarantee against a
deliberately obfuscated command.

**With no protected folder named: zero configuration, zero repository coupling.**

## Install

The hook is two scripts that sit side by side, and the test module is optional.

1. Copy `block-dangerous-commands.py` **and** `protected_folder_guard.py` into
   `.claude/hooks/` in your project (the hook loads the module from its own folder).
2. Merge the contents of `settings.fragment.json` into your `.claude/settings.json`'s `hooks`
   key (or create that key if you don't have one yet). The matcher is
   `Bash|PowerShell|Grep|Glob`: the last two are what let the protected-folder option see
   searches that never run a shell command.
3. Restart Claude Code, or start a new session, for the hook to take effect.

The fragment's command is `python3 "..." || python "..."`. That form runs under Git Bash and
under PowerShell 7 (including with the Windows Store `python3` stub, which fails and falls
through to `python`), but **Windows PowerShell 5.1 cannot parse `||`**. If your hooks run under
5.1, replace the command with the single interpreter name that works on your machine
(`python "${CLAUDE_PROJECT_DIR}/.claude/hooks/block-dangerous-commands.py"`). The user-level
command below repeats the same form and has the same limit.

## Protecting a folder

Name a folder you want Claude Code kept out of (a personal folder, a clients folder, anything) in
a small config file, and the hook denies a call that would reach it:

```json
{
  "protected_folders": [
    "C:\\Users\\you\\Documents\\Private Files"
  ]
}
```

`protected-folders.example.json` is this file. Paths are absolute, drive-letter or `/`-rooted;
a `\\host\share` path is not supported. On Windows write a drive-letter path (a `/mnt/c/...`
path is read as the `C:` drive too).

**Where the hook looks.** A hook command that carries `--config <file>` reads that one file
and nothing else. Without `--config` it reads `${CLAUDE_PROJECT_DIR}/.claude/protected-folders.json`
and then `${CLAUDE_CONFIG_DIR}/protected-folders.json` (or `~/.claude/protected-folders.json`
when that variable is unset), and unions the lists. No file found, or an empty list, switches
the whole option off.

**Install it user-level, and add a `Read()` deny rule.** Two reasons, both about what a
project-level install cannot do:

1. A hook wired in one project's `.claude/settings.json` only runs in that project's
   sessions. To keep the folder protected in every project, copy both scripts to
   `~/.claude/hooks/`, put the config at `~/.claude/protected-folders.json`, and merge the
   fragment into `~/.claude/settings.json` with a command that names the config, so the guard
   does not depend on the hook process inheriting any environment variable:

   ```
   python3 "$HOME/.claude/hooks/block-dangerous-commands.py" --config "$HOME/.claude/protected-folders.json" || python "$HOME/.claude/hooks/block-dangerous-commands.py" --config "$HOME/.claude/protected-folders.json"
   ```

2. This hook never sees the Read, Edit or Write tools (it is matched on Bash, PowerShell,
   Grep and Glob). Close those with a permissions rule in the same settings file, one per
   protected folder, using the `//` absolute-path form:

   ```json
   { "permissions": { "deny": ["Read(//c/Users/you/Documents/Private Files/**)"] } }
   ```

   On Linux or macOS: `Read(//home/you/private-notes/**)`.

**What it catches.**

- A command, Grep or Glob call that names the folder: its name as a whole word, in any
  separator style (`Private Files`, `private_files`, `private-files`).
- A search that starts above the folder and recurses into it without naming it: `find`, `rg`,
  `fd`, `tree`, `grep -r`, `ls -R`, `cp -r`, `tar`, `robocopy`, `Get-ChildItem -Recurse`,
  `dir /s`, `findstr /s`, `os.walk` and similar, started at the drive root, at any directory
  between the root and the folder, or at your home directory (`~`, `$HOME`, `%USERPROFILE%`)
  when the folder is under it. A recursive search elsewhere is untouched. `~` is read both as
  your real home directory and, because cmd.exe and Windows PowerShell 5.1 hand it to a native
  program literally, as a folder named `~` under the working directory, so a `..` climb counts
  from either place; under Git Bash a climb out of the home (`~/../../..` reaching the MSYS
  root, where `/c` is the C: drive again) is read too, and the PowerShell tool gets the same
  reading as a conservative over-deny (PowerShell hands native programs `C:\Users\you`, and
  the climb stops at the drive root there). A lone `/` is the filesystem root on
  Linux and macOS wherever it appears in a recursive command (`tar czf x.tgz /`, `cp -r / x`),
  but a division sign in an expression is not. On Windows a one-letter switch such as `/c`,
  `/d` or `/t` after `cmd`, `dir`, `tree`, `icacls`, `forfiles`, `attrib`, `takeown`, `findstr`,
  `where`, `robocopy`, `xcopy` or `mklink` is read as a switch, never as the `C:` or `D:` drive.
  Some other tool that takes `/x` switches and recurses can still be over-denied when the
  protected folder is on that drive (the guard reads `/c` as the C: drive in Git's tools).
- The folder reached through a wildcard (`C:\Users\you\Documents\Priv*`, brace expansion
  included), a `..` climb back up to a directory above it, and a Grep or Glob call whose path,
  glob or pattern does either.
- Drive aliases that point at a directory above the folder (`subst`, `net use`, `New-PSDrive`,
  and junctions or symlinks made with `mklink` or `New-Item`), and any PowerShell
  `-EncodedCommand`, which is denied outright while a folder is protected because it hides
  what it runs.

**A config that is wrong denies, never switches the guard off.** If the file named by
`--config` is missing, or any file the default search finds does not parse, the guard
cannot know what to protect, so it denies every Grep and Glob call and every shell statement
that holds a recursion marker, and names the file. Read and Edit are not matched by this
hook, so the file can be repaired. The cases: not valid JSON; not `{"protected_folders": [...]}`;
an entry that is not a string; a relative path; a `~` path; a path with a trailing separator;
a bare drive or filesystem root (it would match everything); a glob or regex character in
the path (`* ? [ ] { } ^ $ | + < > "`); a UNC path; a `.` or `..` segment; a folder name with no letter or digit (the name rule would
match that punctuation anywhere); a path that does not exist on disk; one of two unioned files broken. A statement with no recursion marker
(`git status`, `echo hello`) still goes through.

**If the module cannot load** (the file is missing, or a syntax error from a bad edit), the
other rules keep working. When you asked for the guard, meaning the hook command carries
`--config` or a `protected-folders.json` exists in the default search places (the project's
`.claude` folder, `CLAUDE_CONFIG_DIR`, `~/.claude`), it denies Grep, Glob and any
recursion-looking statement while it is down, and the message says why. With no config
anywhere the folder option is simply off and any deny the hook issues says so once. The
fallback only looks at whether a config file exists; it does not read it.

**Python 3.9 or newer.** The scripts avoid anything newer (no possessive quantifiers, no
`match`, no `X | Y` annotations) and were tested on Python 3.12 (Windows) and 3.14 (Linux).
On an older Python the hook may fail to start, and Claude Code treats a hook that exits with
an error as non-blocking, so check `python3 --version` after installing.

**Choose a distinctive name.** The name is matched as a whole word anywhere in the command or
in a Grep pattern, so a folder called `Private` or `HR` also denies a commit message or a
search that mentions the word. Use the folder's real, specific name where you can.

**This is a text guard, best-effort.** It cannot see a path built at run time, a variable it
cannot resolve, or what a script file does when it is run by name; and it is not an
operating-system boundary. If you need a hard guarantee, use file permissions on the folder.

## Tests

`test_protected_folder_guard.py` runs the real hook as a subprocess against a fake folder in a
temp directory and a temp config (it never touches a real folder). From the folder that
holds the hook: `python -m pytest test_protected_folder_guard.py -q` (needs `pytest`). It
covers the Windows forms on Windows, the POSIX forms on Linux, macOS and WSL, every config case
above, the module-missing fallback, and rules 1 to 4 and the heredoc rule.

## Notes

- The settings fragment's command tries `python3` first, falling back to `python` if that
  fails — many Linux/Mac systems have only `python3` on `PATH`, no bare `python` at all. If
  your system uses a different interpreter name entirely, edit the command directly.
- If your Bash tool is configured to route through PowerShell
  (`CLAUDE_CODE_USE_POWERSHELL_TOOL`), both POSIX and PowerShell command shapes are checked.
- `main`/`master` are checked as a blunt, literal safety heuristic against the two
  overwhelmingly common default-branch names — this is deliberately not wired to whatever
  your repo's actual default branch happens to be named. If your default branch has a
  different name, add it to the check inside the script.

## Known false-positive class: this hook can block on prose, not just real invocations

The matching works on the raw command string handed to Bash, with no awareness of quoting —
so a `git commit -m "..."` whose *message text* happens to contain a guarded command as prose
(for example, a commit message describing this hook and quoting `git clean -fd` as an example)
can trip the same regex the hook uses to catch a real invocation. This was hit for real while
building this component: a commit message describing the `git clean -fd` test case got blocked
by this exact hook running live in the source repo. The same holds for a protected folder's
name: a commit message that names it is denied.

There's no clean fix without a real shell parser tracking quote nesting, which this
deliberately isn't (see the "best-effort" note above). If you hit this, reword the message —
paraphrase the command rather than quoting it literally, or drop the flag
(`git clean -fd` → `git clean` with the flags described separately).
