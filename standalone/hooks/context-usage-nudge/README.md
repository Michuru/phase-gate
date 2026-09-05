# context-usage-nudge

A `Stop` hook that nudges you toward wrapping up as a session's context usage climbs. Scans
the transcript for the last assistant turn's token-usage numbers, estimates what percentage
of that model's context window is in use, and fires a message once per debounce tier
(50/60/70/80/90%) per session — never more often than that, and never twice for the same
tier.

**Zero configuration. Zero repository coupling** — the nudge message suggests writing
yourself a handoff/summary, in generic terms; it does not assume you have any particular
skill or slash command installed.

## Install

1. Copy `context-usage-nudge.py` to `.claude/hooks/context-usage-nudge.py` in your project.
2. Merge the contents of `settings.fragment.json` into your `.claude/settings.json`'s `hooks`
   key.
3. Restart Claude Code, or start a new session.

## Notes

- The settings fragment's command tries `python3` first, falling back to `python` if that
  fails — many Linux/Mac systems have only `python3` on `PATH`, no bare `python` at all. If
  your system uses a different interpreter name entirely, edit the command directly.
- State (which debounce tier has already fired, per session) is written to
  `.claude/state/context-usage-nudge.json`, derived from the script's own install location
  (one level up from wherever you copied the script). If you install it somewhere other than
  `.claude/hooks/`, the state file lands at `<parent of that directory>/state/`.
- `MODEL_CONTEXT_WINDOWS` is a small table of known model context-window sizes. An
  unrecognized model falls back to the smallest/safest known window, so an unmapped future
  model doesn't silently suppress the nudge. Update the table if it drifts from your Claude
  Code version's actual models.
- A transcript below 2 MB is skipped entirely — it cannot plausibly be near even the lowest
  debounce tier for any known model's window, so there's nothing to scan for.
