# hooks-health-check

A `SessionStart` hook that verifies `core.hooksPath` is actually wired up in whichever repo
the session started in, and that the git hooks it points to are tracked with the executable
bit set. `core.hooksPath` is easy to lose silently — a repo restructure, a fresh clone, a
`git filter-repo` run — and the failure has no symptom of its own until something else
surfaces it. This catches that failure class at session start instead of by accident.
Reports via a `systemMessage`; never blocks anything.

**Zero configuration required, but has two settings worth knowing about.**

## Install

1. Copy `hooks-health-check.py` to `.claude/hooks/hooks-health-check.py` in your project.
2. Merge the contents of `settings.fragment.json` into your `.claude/settings.json`'s `hooks`
   key.
3. Restart Claude Code, or start a new session, for the hook to take effect.

## Configuration

Two constants at the top of the script:

- `EXPECTED_HOOKS_PATH` — the `core.hooksPath` value your repo expects (relative, so it
  survives being cloned anywhere). Defaults to `.githooks`.
- `REQUIRED_HOOK_FILES` — the filenames under that path that must be present and tracked.
  Defaults to `("pre-commit", "pre-push", "scan-secrets.sh")`, matching this export's own
  git-hook convention (see the repo root's `.githooks/`).

Change both if your repo uses a different hooks directory or a different set of files.

## Notes

- The settings fragment's command tries `python3` first, falling back to `python` if that
  fails — many Linux/Mac systems have only `python3` on `PATH`, no bare `python` at all. If
  your system uses a different interpreter name entirely, edit the command directly.
- `core.fileMode` is commonly `false` on Windows/NTFS, where there's no real POSIX executable
  bit to track. The script reads `core.fileMode` live via `git config` rather than assuming,
  and only enforces the executable-bit check when it's actually `true`.
- Zero repository coupling beyond the two constants above, which you're expected to set for
  your own repo's convention.
