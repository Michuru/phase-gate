# Changelog

Notable changes, tagged as GitHub releases when they land. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/); versioning is semver-ish, not strictly enforced.

**`v1.0.0` (2026-09-12) is the first release** — cut alongside this repo going public.

## [Unreleased]

## [1.0.0] - 2026-09-12

First release, cut alongside the repo's private→public flip.

### Added
- The full Phase-Gate method: eleven skills (`design-gate`, `execution-gate`, `implement-queue`,
  `consolidate-docs`, `handoff`, `commit`, `wrap-up-session`, `work-backlog`, `review-pr`, plus
  `code-reviewer`/`docs-writer` subagents) covering the AI-assisted design→build→QA→ship lifecycle,
  shipped as both an integrated `process/` shelf and a pick-and-choose `standalone/` catalog (four
  hooks, a statusline, `ai-check`, `humanize`).
- A grounded, citation-checked installer skill (`phase-gate-install`) that reads an adopter's repo
  and proposes what applies before writing anything.
- `update-notification`: a `SessionStart` hook that passively checks for new commits upstream since
  install, throttled and fail-open — closes the discovery half of the "no update mechanism" gap.
- **`doc-review`** (standalone shelf): a three-pass documentation review skill — a
  fresh-context cold read for clarity, a grounding pass that checks every claim against
  the files it cites, and a deterministic script that scans for document-level word
  repetition and machine-register vocabulary. Report-first, gated apply, source-checked
  before any edit lands. Ships with its own `LICENSE` (partly derived, with notice, from
  `humanize`'s vocabulary list and hard rules).
- Verified against a real fresh install (11 required checks) and a real first adopter (the beta
  tester's own in-progress project), whose feedback fixed three gaps: a stated persistent-adoption
  warning, an `/adopt`-shaped retrofit path for already-in-progress projects, and a mandatory (still
  optional-to-run) execution-gate checkpoint.

### Changed
- **Two-axis SDLC redesign**: re-cut the command surface along lifecycle phases (`design-gate` →
  `spec`, `work-backlog` → `backlog`, new `build`/`verify`/`ship`/`initiate`), with the four process
  gates (tier check, design review, execution, QA) now firing automatically between commands
  instead of being invoked directly.
- **Next-command contract**: every command now closes by naming what happens next — one
  recommendation, one named alternative — so unfinished work doesn't get silently `/clear`ed away.
  `/initiate` is now a ranker over all actionable project state instead of a stop-at-first-match
  router; `/end-task` is its mirror, a parent-level close router that surfaces the `/handoff` fork
  in every branch; `/adopt` split out of `/initiate`'s old Step 3.
- `commit`/`wrap-up-session` are now 5-line redirect stubs pointing at `end-task`, kept one cycle
  for backward compatibility.
- Commit-producing skills (`end-task`, `ship`, `backlog`) now proactively ask about pushing to a
  GitHub remote right after committing, when the target repo has one configured — previously
  purely passive (never pushed without the user explicitly bringing it up first).
- `README.md`'s Quick Start now offers a copy-paste onboarding prompt alongside the existing
  terminal steps, so an adopter can start from Claude Code instead of a terminal first.

### Fixed
- The installer never staged the files it writes (`.githooks/*` and others) into git's index,
  leaving them untracked and silently vulnerable to a fresh clone or `git clean`.
- A duplicated line in the ported `execution-gate/SKILL.md` from the two-axis port.
- `spec`'s Step 1 model-ladder check didn't consider a different-family model when picking a design
  review target.
- `update-notification`'s `dependencies.json` git-prerequisite wording.
- `doc-review`'s `voice_scan.py`: the vocabulary-list check's raw-occurrence floor
  (`RAW_FLOOR_WORD = 4`) made it empirically dead on anything under a few hundred words
  and was unreachable from the CLI. Adds a `scan_text(text, raw_floor=...)` in-memory
  entry point and a matching `--raw-floor` flag so a caller can lower the floor (e.g. to
  1) for short documents; default behavior is unchanged for every existing caller.
- `handoff`'s multi-candidate resume path (Step 0) deferred its "is this thread already
  closed" check to whichever primer the user picked, leaving every other candidate in the
  list unchecked and presented as equally live. The check now runs on every candidate
  before the list is shown, and now also greps the primer's own named repo for commits
  that plausibly completed the work, since an explicit Status/`BACKLOG_ARCHIVE.md` marker
  isn't the only way a thread can actually be closed.
