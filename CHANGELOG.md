# Changelog

Notable changes, tagged as GitHub releases when they land. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/); versioning is semver-ish, not strictly enforced.

**Pre-1.0, tagged `0.x.y`.** `v1.0.0` is reserved for the first release considered genuinely
stable, not just "the first one we happened to cut" — `0.x` tags mark real checkpoints along the
way and stay in the history once `1.0.0` lands (no retroactive cleanup planned). See `BACKLOG.md`'s
"Sharing this repo's workflow/skills" section for the open item tracking when to actually cut
`v1.0.0`.

## [Unreleased]

### Added
- **`doc-review`** (standalone shelf): a three-pass documentation review skill — a
  fresh-context cold read for clarity, a grounding pass that checks every claim against
  the files it cites, and a deterministic script that scans for document-level word
  repetition and machine-register vocabulary. Report-first, gated apply, source-checked
  before any edit lands. Ships with its own `LICENSE` (partly derived, with notice, from
  `humanize`'s vocabulary list and hard rules).

### Fixed
- `doc-review`'s `voice_scan.py`: the vocabulary-list check's raw-occurrence floor
  (`RAW_FLOOR_WORD = 4`) made it empirically dead on anything under a few hundred words
  and was unreachable from the CLI. Adds a `scan_text(text, raw_floor=...)` in-memory
  entry point and a matching `--raw-floor` flag so a caller can lower the floor (e.g. to
  1) for short documents; default behavior is unchanged for every existing caller.

## [0.1.0] - 2026-09-06

### 2026-09-05/06 — next-command contract, update-notification, two-axis SDLC redesign

#### Changed
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

#### Added
- `update-notification`: a `SessionStart` hook that passively checks for new commits upstream since
  install, throttled and fail-open — closes the discovery half of the "no update mechanism" gap.
- Commit-producing skills (`end-task`, `ship`, `backlog`) now proactively ask about pushing to a
  GitHub remote right after committing, when the target repo has one configured — previously
  purely passive (never pushed without the user explicitly bringing it up first).

#### Fixed
- The installer never staged the files it writes (`.githooks/*` and others) into git's index,
  leaving them untracked and silently vulnerable to a fresh clone or `git clean`.
- A duplicated line in the ported `execution-gate/SKILL.md` from the two-axis port.
- `spec`'s Step 1 model-ladder check didn't consider a different-family model when picking a design
  review target.
- `update-notification`'s `dependencies.json` git-prerequisite wording.

### 2026-09-05 — initial build

#### Added
- The full Phase-Gate method: eleven skills (`design-gate`, `execution-gate`, `implement-queue`,
  `consolidate-docs`, `handoff`, `commit`, `wrap-up-session`, `work-backlog`, `review-pr`, plus
  `code-reviewer`/`docs-writer` subagents) covering the AI-assisted design→build→QA→ship lifecycle,
  shipped as both an integrated `process/` shelf and a pick-and-choose `standalone/` catalog (four
  hooks, a statusline, `ai-check`, `humanize`).
- A grounded, citation-checked installer skill (`phase-gate-install`) that reads an adopter's repo
  and proposes what applies before writing anything.
- Verified against a real fresh install (11 required checks) and a real first adopter (the beta
  tester's own in-progress project), whose feedback fixed three gaps: a stated persistent-adoption
  warning, an `/adopt`-shaped retrofit path for already-in-progress projects, and a mandatory (still
  optional-to-run) execution-gate checkpoint.
