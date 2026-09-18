# schedule-wakeup-guard

A `PreToolUse` hook that blocks a `ScheduleWakeup` call unless the session's own transcript shows
a genuine, still-live `/loop` invocation. `ScheduleWakeup` exists for `/loop`'s dynamic pacing —
it's easy for an agent to reach for it more generally, as a "check back on this background task
later" mechanism, which it was never meant for (a background agent call already notifies on its
own when it finishes).

Allows without checking anything further:
- `{"stop": true}` — stopping a loop is always safe.
- `{"prompt": "<<autonomous-loop>>"}` — the documented sentinel for a cron-based autonomous loop,
  which may have no `/loop` command-name marker in its own transcript at all.

Otherwise, reads the session's transcript file and looks for the most recent real `/loop`
invocation (a literal `<command-name>/loop</command-name>` entry, the same way Claude Code records
any slash command). No such entry anywhere, or the most recent one was already stopped with
nothing newer — blocked.

**Zero configuration. Zero repository coupling.**

## Install

1. Copy `schedule-wakeup-guard.py` to `.claude/hooks/schedule-wakeup-guard.py` in your project.
2. Merge the contents of `settings.fragment.json` into your `.claude/settings.json`'s `hooks`
   key (or create that key if you don't have one yet).
3. Restart Claude Code, or start a new session, for the hook to take effect.

## Notes

- The settings fragment's command tries `python3` first, falling back to `python` if that
  fails — many Linux/Mac systems have only `python3` on `PATH`, no bare `python` at all. If
  your system uses a different interpreter name entirely, edit the command directly.
- This hook fails open on any read/parse error (a missing transcript file, an unreadable line) —
  it exists to catch a specific misuse shape, not to be a hard guarantee, and should never be the
  reason a legitimate loop breaks.
- The detection logic parses each transcript line as JSON and checks structured fields
  (`type`/`message.content`), rather than scanning raw line text for the command-name tag. A raw
  substring scan produces false positives whenever that exact tag text shows up inside a tool call
  or its output — for example, a session inspecting its own transcript while debugging this exact
  hook. If you adapt this script, keep the structured-field check rather than reverting to a
  substring scan.
- If Claude Code's transcript format for slash-command entries or tool-use blocks ever changes,
  this hook's detection logic will need updating to match — it was written against a live-verified
  snapshot of that format, not from documentation alone (the JSON contract at
  `code.claude.com/docs/en/hooks.md` documents the `PreToolUse` payload itself, but not the
  transcript file's own internal structure).
