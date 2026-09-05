# block-dangerous-commands

A `PreToolUse` hook that hard-blocks a short, deliberately narrow list of catastrophic Bash
commands, regardless of permission mode — a technical backstop for autonomous/auto modes,
where a soft "confirm before risky actions" convention gets skipped by design.

Blocks:
- `rm -rf` (or PowerShell `Remove-Item -Recurse -Force`) targeting a bare filesystem root
- `git push --force` (or `-f` / `--force-with-lease`) targeting `main`/`master`
- `git reset --hard` when the working tree actually has uncommitted changes to lose
- `git clean -f` when a dry run shows it would actually remove something

Anything not matched here still goes through Claude Code's normal permission-prompt flow —
this hook only ever adds a stricter floor, never loosens the default. Pattern-matched on the
raw command string, not a real shell parser — best-effort, not a guarantee against a
deliberately obfuscated command.

**Zero configuration. Zero repository coupling.**

## Install

1. Copy `block-dangerous-commands.py` to `.claude/hooks/block-dangerous-commands.py` in your
   project.
2. Merge the contents of `settings.fragment.json` into your `.claude/settings.json`'s `hooks`
   key (or create that key if you don't have one yet).
3. Restart Claude Code, or start a new session, for the hook to take effect.

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
by this exact hook running live in the source repo.

There's no clean fix without a real shell parser tracking quote nesting, which this
deliberately isn't (see the "best-effort" note above). If you hit this, reword the message —
paraphrase the command rather than quoting it literally, or drop the flag
(`git clean -fd` → `git clean` with the flags described separately).
