# statusline

A Claude Code `statusLine` script. Line 1: model, working directory, git branch (with a `*`
if dirty), and an open PR/MR badge if present. Line 2: context-window usage percentage
(colored, with a warning at ≥75%), session cost, wall-clock duration, and lines
added/removed. Line 3 (optional, only when the payload provides it): account-wide 5-hour/7-day
rate-limit usage and prompt-cache hit ratio.

Every field is read defensively and simply omitted when the payload doesn't provide it —
never guessed, never shown as a literal "None" or crash.

**Zero configuration. Zero repository coupling.**

## Install

1. Copy `statusline.py` to `.claude/statusline.py` in your project (or anywhere you like —
   just update the path in the settings fragment below to match).
2. Merge the contents of `settings.fragment.json` into your `.claude/settings.json` (it sets
   the top-level `statusLine` key, not something under `hooks`).
3. Restart Claude Code, or start a new session, to see the new status line.

## Notes

- The settings fragment's command tries `python3` first, falling back to `python` if that
  fails — many Linux/Mac systems have only `python3` on `PATH`, no bare `python` at all. If
  your system uses a different interpreter name entirely, edit the command directly.
- Git branch/dirty-state is cached to a temp file for 5 seconds, keyed by session ID, since
  Claude Code re-invokes this script as a fresh process on every refresh (every ~30 seconds
  and after every assistant turn) — without the cache, that's a `git status` + `git branch`
  call on every single refresh tick.
- `rate_limits`, `prompt_cache`, and `pr` payload fields require a sufficiently recent Claude
  Code version and are simply absent (and therefore omitted from the output) on older
  versions — nothing to configure, this degrades automatically.
