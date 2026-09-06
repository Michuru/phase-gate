# periodic-audit-threshold-check

A `SessionStart` hook that decides whether any of your registered tools are due for a
`periodic-audit` pass — either enough commits have landed on a tool's flagged surfaces since its
last audit, or its bug-shape ledger grew a new entry with no matching commits yet (the one signal a
commit-count trigger alone would never catch). Read-only: it never runs an audit itself, only
reports that one is due, via a `systemMessage` (or, during calibration, only logs).

This is the companion hook to the `periodic-audit` process-shelf skill and its two agent
definitions (`periodic-audit-coverage`, `periodic-audit-structural`) — install all three together.

## Install

1. Copy `audit-threshold-check.py` **and** `audit_state.py` to `.claude/hooks/` in your project
   (both files, same directory — the hook imports the state helper as a sibling module).
2. Merge the contents of `settings.fragment.json` into your `.claude/settings.json`'s `hooks` key.
3. Create `.claude/audit-config.json` for each repo you want checked (see schema below). No file
   here means no tools registered for that repo — the hook silently skips it, by design; this is
   the same "not seeded yet" state a fresh install starts in for every repo.
4. Restart Claude Code, or start a new session, for the hook to take effect.

## `audit-config.json` schema

```json
{
  "tools": {
    "<tool-key>": {
      "main_file": "path/to/the/main/file.html",
      "related_files": ["path/to/a/shared/helper.js"],
      "notes_file": "path/to/that/tool's/NOTES.md",
      "flagged_surfaces": ["functionOne", "functionTwo"],
      "regression_suite": "path/to/its/regression/suite.html",
      "real_data_folder": null,
      "commit_threshold": 5
    }
  }
}
```

`regression_suite` gates the coverage-gap pass (`null` if the tool has none — that pass reports
"not applicable" rather than being skipped silently). `flagged_surfaces` is documentation only for
this hook; the structural pass's own agent reads it fresh from your prompt each run.

## `.claude/audit-ledger/<tool-key>.json` schema

Machine-readable, not prose — a prose ledger (e.g. a `NOTES.md` bug-shape section) has a real,
observed failure mode: it goes stale exactly when a fix extends to a sibling branch the note never
gets updated for, producing both false-clean and false-open reads later.

```json
{
  "shapes": {
    "<shape-name>": { "description": "what this bug shape looks like and how it was first found" }
  },
  "entries": [
    { "function": "functionOne", "shape": "<shape-name>", "checked_at_sha": "abc1234", "status": "clean" }
  ]
}
```

`status` is `clean` or `affected-pending`. The structural pass re-checks every flagged function
against every named shape on every run — these markers are report bookkeeping, never a skip-list.
An empty or absent ledger reports "not applicable: no ledger entries yet," which is an honest,
expected state for a tool you haven't seeded yet, not a bug.

## Configuration

One constant worth knowing about, at the top of `audit-threshold-check.py`:

- `CALIBRATION_MODE` — ships `True`. A brand-new tool's default `commit_threshold` of 5 can trip
  immediately on a normal active stretch, so nudging starts disabled and the hook only logs what
  *would* have fired, to `.claude/state/audit-calibration-log.jsonl`. Watch that log for a real
  stretch of work before flipping this to `False` and trusting the default threshold — or lower it
  per-tool in `audit-config.json` if 5 is clearly too sensitive for your own commit cadence.

## Notes

- Discovers repos dynamically — checks `CLAUDE_PROJECT_DIR` itself, plus any immediate subdirectory
  that is its own git root (a monorepo-of-repos workspace). A single plain repo just gets checked on
  its own; no configuration needed either way.
- The settings fragment's command tries `python3` first, falling back to `python` — see
  `hooks-health-check`'s own README for why.
- `audit_state.py`'s state file (`.claude/state/audit-thresholds.json`) is machine-generated,
  per-tool-per-pass state — gitignore it, the same way `.claude/state/` is gitignored in this
  export's own source repo.
- Never reuse a generic code-review agent for either pass — the structural pass in particular needs
  a fresh, whole-function read, the opposite of a diff-scoped review default.
