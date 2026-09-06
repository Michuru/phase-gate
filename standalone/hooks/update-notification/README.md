# update-notification

A `SessionStart` hook that passively checks whether phase-gate has new commits upstream since this repo
was installed, using the install receipt's recorded `source_commit`/`source_origin`. Throttled to at most
one network check every 24 hours, and notifies at most once per new upstream commit — never fetches or
applies anything itself, purely a discovery nudge. Fails silently (no message, never blocks) if it can't
determine an answer: no receipt, the check disabled, no git, no network, no credentials, or a malformed
remote.

**Zero configuration required, but has one setting worth knowing about.**

## Install

1. Copy `update-notification.py` to `.claude/hooks/update-notification.py` in your project.
2. Merge the contents of `settings.fragment.json` into your `.claude/settings.json`'s `hooks`
   key.
3. Restart Claude Code, or start a new session, for the hook to take effect.

(Note: normally this file's install and the settings merge happen automatically via the phase-gate
installer skill, not by hand — but this is stated this way for someone raiding `standalone/` directly
per this repo's own README's stated audience.)

## Configuration

- `update_check_enabled` — an `installer/variables.json` entry (kind `default`, value `true`). Not
  asked about during install the way a `required`-kind variable would be; the real opt-in moment is
  choosing to install this component at all. This is a secondary off-switch. Its resolved value lives
  in your own install receipt (`.claude/phase-gate-install/receipt.json`'s `variables` array) — the
  hook reads it from there, not from a separate file.
- `--force` CLI flag on the script: bypasses the 24-hour throttle window (not the once-per-commit
  notify gate) — useful for testing or an on-demand check.

## Notes

- Compares against the remote's `HEAD` (its default branch) — doesn't distinguish an adopter who
  deliberately pinned to an older tag or branch.
- The settings fragment's command tries `python3` first, falling back to `python` — same convention
  as every other bundled hook.
- Privacy: `git ls-remote` is an unauthenticated read against a remote you already trust enough to
  have cloned from — the same operation `git fetch`/`git pull` already perform. Any embedded
  credentials in the remote URL are stripped before being recorded in your receipt at install time.
- If phase-gate is still a private repo when you check for updates, the installer records whichever
  remote you confirmed — the hook uses that same remote, with hardened non-interactive git settings
  so a missing/expired credential fails silently rather than popping a login prompt.
- If you get the nudge: pull the phase-gate clone (or re-clone it), re-copy
  `installer/phase-gate-install/` from the updated clone into your own `.claude/skills/` (the
  installer skill itself may also have changed upstream), then re-run `/phase-gate-install <path>`
  to review what's new.
- Zero repository coupling — reads only its own installed receipt and state file.
