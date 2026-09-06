# Changelog

Notable changes, tagged as GitHub releases when they land. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/); versioning is semver-ish, not strictly enforced.

**Nothing has been tagged yet.** Everything below is pre-1.0 — Lief is this project's beta tester,
and `v1.0.0` is reserved for the first release considered genuinely stable, not just "the first one
we happened to cut." Until that call is made, changes accumulate under `[Unreleased]` rather than
being assigned version numbers. See `BACKLOG.md`'s "Sharing this repo's workflow/skills" section for
the open item tracking when to actually cut `v1.0.0`.

## [Unreleased]

### 2026-09-06 — next-command contract, update-notification, two-axis SDLC redesign

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
- Verified against a real fresh install (11 required checks) and a real first adopter
  (Lief/Dungeonkeep), whose feedback fixed three gaps: a stated persistent-adoption warning, an
  `/adopt`-shaped retrofit path for already-in-progress projects, and a mandatory (still
  optional-to-run) execution-gate checkpoint.
