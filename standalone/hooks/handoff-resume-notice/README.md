# handoff-resume-notice

A `SessionStart` hook that offers a window the handoff primer it wrote just before you cleared it. After you run `/handoff` and then a bare `/clear`, the new window is told which primer is waiting, and a plain "go" resumes it. Without this hook you start the new window and run `/handoff` yourself, which then lists every live primer for you to pick from.

It works with the `handoff` skill from `process/skills/handoff/`: the skill's outgoing step 6c writes a small pointer file through `handoff_pointer.py`, and this hook reads it.

## What it needs

- **A name on the window.** The hook only acts when the window kept a `/rename` name across `/clear` (Claude Code passes it as `session_title`). A window you never renamed gets no offer, and `/handoff` tells you to run `/rename <a short name>` and then re-run its pointer step.
- **A bare `/clear`.** `/clear <name>` renames the window and the pointer no longer matches.
- **A `handoff` skill that writes the pointer.** The skill and this hook go together; installing the hook alone does nothing.
- **A session id and transcript the skill can find.** Step 6c of the `handoff` skill uses `${CLAUDE_SESSION_ID}` and looks for `<session id>.jsonl` under the `projects` folder of Claude Code's config directory. If it finds neither exactly, it writes no pointer and says so, and resuming is the manual `/handoff` pick list. Not yet confirmed in a live install outside the source repo: after your first `/handoff` and bare `/clear`, check that the offer appears.
- **No check for a second window.** This hook cannot tell whether you already resumed the same primer in another window. The skill's incoming section asks you to say stop in that case.

## Install

1. Copy `handoff-resume-notice.py` **and** `handoff_pointer.py` into `.claude/hooks/` in your project. They must sit in the same folder.
2. Merge the contents of `settings.fragment.json` into your `.claude/settings.json`'s `hooks` key.
3. Restart Claude Code, or start a new session.

## Behavior

- Acts only after a `/clear`, and only for a window with a name. Silent in every other case: another start source, no pointer, more than one pointer with the same name, a primer that was consumed or archived, a pointer older than two hours, or any error. It never blocks a session start.
- The model is told the primer's path, its first heading and the writing window's six-character reference. It must check its own reference against that one before resuming, so a different window that happens to share the name does not take the primer.
- If your first message is about something else, the model mentions the waiting primer in one line and does your task.

## Notes

- Pointers are small JSON files in `.claude/state/handoff-pointers/`, derived from the script's own install location (one level up from `.claude/hooks/`, then `state/`). Installed somewhere else, they land at `<parent of that folder>/state/handoff-pointers/`. Add the folder to `.gitignore`; each pointer holds a local path and a session id.
- A pointer expires after two hours and is deleted after seven days. A newer handoff from the same window replaces its older pointer.
- Run the tests from this folder: `python -m pytest test_handoff_pointer.py test_handoff_resume_notice.py`. They set `HANDOFF_POINTER_DIR` to a temporary folder and never touch real pointers.
- The settings fragment's command tries `python3` first and falls back to `python`, since many Linux and Mac systems have no bare `python`.
