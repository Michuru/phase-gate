# hooks-health-check

A `SessionStart` hook that verifies `core.hooksPath` is actually wired up in whichever repo
the session started in, and that the git hooks it points to are tracked with the executable
bit set. `core.hooksPath` is easy to lose silently — a repo restructure, a fresh clone, a
`git filter-repo` run — and the failure has no symptom of its own until something else
surfaces it. This catches that failure class at session start instead of by accident.
Reports via a `systemMessage` (shown to you) and an `additionalContext` (shown to the model);
never blocks anything. An absolute `core.hooksPath` that points at this repo's own hooks folder is
accepted as well as the relative one (`.githooks` by default).

If you also installed the [`block-dangerous-commands`](../block-dangerous-commands/README.md)
hook's protected-folder option, it checks that guard's config too: a protected-folders file that
does not parse, or a `--config` file that is missing, makes the guard deny every Grep and Glob
call and every recursive shell command, so the check says so at session start. With the guard
absent, or no config file in the guard's default search places (where a missing file simply means
the guard is off), it says nothing. `python hooks-health-check.py --report` prints the config's
entries by mode (plain, path-qualified, optional) and lists any optional entry whose folder is
missing on disk (still protected by name, but worth a typo check); it needs no session, and run
from your project it also reads the project-level config. It says plainly when the guard is not
installed beside the hook or no config is found.

**If you installed the guard user-level** (the block-dangerous-commands README recommends it, with
`--config "$HOME/.claude/protected-folders.json"` on its hook command), install this hook
user-level too: copy it and `protected_folder_guard.py` into the same `~/.claude/hooks/` folder,
merge `settings.fragment.json` into `~/.claude/settings.json`, and give it the same argument
(`... hooks-health-check.py --config "$HOME/.claude/protected-folders.json"`). Its git checks read
the session's own folder, so a user-level install still checks each repo. A project-level copy of
this hook cannot see a guard that lives in `~/.claude/hooks/`, and stays silent about it.

**Zero configuration required, but has three settings worth knowing about.**

## Install

1. Copy `hooks-health-check.py` to `.claude/hooks/hooks-health-check.py` in your project (next to
   `protected_folder_guard.py` if you use the protected-folder option, because it loads the guard from
   its own folder).
2. Merge the contents of `settings.fragment.json` into your `.claude/settings.json`'s `hooks`
   key.
3. Restart Claude Code, or start a new session, for the hook to take effect.

## Configuration

Three constants at the top of the script:

- `EXPECTED_HOOKS_PATH` — the `core.hooksPath` value your repo expects (relative, so it
  survives being cloned anywhere). Defaults to `.githooks`.
- `REQUIRED_HOOK_FILES` — the filenames under that path that must be present and tracked.
  Defaults to `("pre-commit", "pre-push", "scan-secrets.sh")`, matching this export's own
  git-hook convention (see the repo root's `.githooks/`).

- `PROTECTED_FOLDERS_CONFIG` — optional, empty by default. Only if the guard's hook command names
  its config with `--config <file>`: name that same file here so this check reads the file the
  guard reads, or put the same `--config <file>` on this hook's own command line (it wins over the
  constant, and the shell expands `$HOME` for you). Use an absolute path with forward slashes
  (`"C:/Users/you/.claude/protected-folders.json"`): a backslash path in a normal Python string is
  a syntax error that stops the whole hook, and a relative path depends on the folder the hook runs
  from. `~` and `$HOME` are expanded. Empty means the guard's default search (the project's
  `.claude` folder, then `CLAUDE_CONFIG_DIR` or `~/.claude`).

Change the first two if your repo uses a different hooks directory or a different set of files.

## Notes

- The settings fragment's command tries `python3` first, falling back to `python` if that
  fails — many Linux/Mac systems have only `python3` on `PATH`, no bare `python` at all. If
  your system uses a different interpreter name entirely, edit the command directly.
- `core.fileMode` is commonly `false` on Windows/NTFS, where there's no real POSIX executable
  bit to track. The script reads `core.fileMode` live via `git config` rather than assuming,
  and only enforces the executable-bit check when it's actually `true`.
- Zero repository coupling beyond the constants above, which you're expected to set for
  your own repo's convention.
