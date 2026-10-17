# Changelog

Notable changes, tagged as GitHub releases when they land. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/); versioning is semver-ish, not strictly enforced.

**`v1.0.0` (2026-09-12) is the first release** — cut alongside this repo going public.

## [Unreleased]

### Added
- `spec` Step 3.4's design-review question now offers "run it, then a second pass" when a
  genuinely different third model exists. The second reviewer gets the first pass's report, and a
  two-pass review is recorded under one `## Design review` heading with a sub-section per pass.
- `spec` Step 3.5 option (b) ("backlog it") now closes with an explicit session-close line:
  `/end-task` if this session's changes are uncommitted, otherwise safe to `/clear`, with
  `/handoff` as the named alternative. `docs/WORKFLOW.md` rule 5 states the same for any next
  command that belongs to a future session.
- `spec` Step 3.5 gains option (d), "hand this session off to a fresh one via `/handoff`": offered
  every time, and recommended ahead of "implement now" when the session's context is getting full.
  It does everything option (b) does, then runs `/handoff`.
- `block-dangerous-commands` now also blocks a script passed through a heredoc with a backslash in it
  (an interpreter such as `python - <<'EOF'`, or a redirect into a code file). Those scripts can come back
  silently corrupted: a `\n` inside a string turns into a real line break and the script dies at run time. Every
  other heredoc, such as a commit message or notes, and any heredoc script with no backslash, is still allowed.
- `handoff` never overwrites an existing primer (a same-day second handoff gets an `-<HHMM>` suffix), and
  checks `git status --short` before committing a path another session may have half-staged.

### Changed
- Drift review of the source repo's 12 drifted components, all manifest hashes updated. Ported:
  `context-usage-nudge` now works as a `UserPromptSubmit` hook and its settings fragment wires it there (a `Stop`
  hook's `systemMessage` reaches only you, never the model; it still runs unchanged as a `Stop` hook).
  `hooks-health-check` accepts an absolute `core.hooksPath` that points at the repo's own hooks folder, and reports
  to the model as well as to you (a drifted `core.hooksPath` means its own commits skip the secret guard).
  **Reviewed and deliberately not ported**, because each depends on a source-repo script or tool that is not
  exported: `backlog` (chain mode, snooze markers, the `backlog_view.py` and `backlog_check.py` helpers),
  `end-task` (the backlog-headline check that runs `backlog_check.py`), `code-reviewer` (a machine-readable
  `REVIEW-RESULT` footer that only `ops-audit` reads), `spec`'s matching `DESIGN-REVIEW-RESULT` footer,
  `handoff`'s chain-run primers, `block-dangerous-commands`' launch-line rule (Windows-only and tied to one
  incident), `verify`'s local-review step (still the deferred drift), and the pinned full model ids and
  `effort:` lines in the source repo's agent and skill files (the exported agents keep the `sonnet`/`haiku`/`opus`
  aliases).
- Manifest hash record for `statusline` updated with no content change. The source repo's copy gained a
  rate-limit sampler that appends the account-wide 5h/7d percentages to a state file for its own `ops-audit`
  tool. That tool is not exported, so the sampler is deliberately not ported: it would add silent file
  writes to every adopter's status line with nothing reading them.
- Manifest hash records updated for `spec` and `context-usage-nudge` after a drift review, with no
  content change. `spec`'s one new source line only points at a source-repo design doc that is not
  exported. `context-usage-nudge` already resolves point-release model names through its own
  family fallback, which was checked against `claude-sonnet-5-5`, `claude-opus-5-5` and
  `claude-fable-5-1`. `verify` remains the one deliberately deferred drift (its local-review step).
- `spec`, `handoff` and `end-task` are each now a short core plus reference files that load only on the
  branch that needs them, instead of one long file read in full on every use (`spec`: about 44 KB to an 11 KB
  core plus five references; `handoff`: about 17 KB to a 6 KB core plus one reference; `end-task`: about 17 KB to
  an 8 KB core plus one reference). Every rule is kept. Citations between skills now name the section or rule
  rather than a step number, and the same was done in `initiate`, `build`, `verify`, `ship`, `execution-gate`,
  `implement-queue` and `local-delegate`'s runner comments, so a renumbered step can no longer leave a stale
  pointer behind.
- `handoff` ships two small stdlib-only scripts that replace prose procedures that kept going wrong in practice:
  `handoff_scan.py` lists the live primers (directory position only; the repo you are in, repos nested directly
  under it, and an `EXTERNAL_REPOS` list you set), and `handoff_consume.py` archives a consumed primer in one
  safe step (`git mv`, marker, `git add`, a pathspec commit, then proof from `git show HEAD:`; exit 0 consumed,
  1 refused or rolled back, 2 committed but the proof failed). Python and git are now listed as a prerequisite.
- `end-task` keeps its survey as short manual steps (`git status` and `git diff --stat` in each repo touched,
  named by recall); the source repo's survey script is not exported because it depends on helpers that are not.
- `block-dangerous-commands` now blocks any script passed through a Bash heredoc, not only one with a backslash
  in it (the narrower rule was broken again within a session). Its message names the working route: a script
  file, or on Windows a PowerShell here-string piped to the interpreter. Heredocs for commit messages, notes,
  markdown and JSON are still allowed.
- Drift review of the 13 components that drifted after the split: all manifest hashes updated. Reviewed and
  still deliberately not ported: `spec`'s `DESIGN-REVIEW-RESULT` footer, `handoff`'s chain-run primers and
  `end-task`'s backlog-headline check, for the reasons given in the earlier drift review above.

### Removed
- The `commit` and `wrap-up-session` redirect stubs, kept for one cycle after `end-task` absorbed them (the
  first is now `end-task`'s narrow-commit depth, the second its full-sync depth). Anyone who installed them
  earlier can delete `.claude/skills/commit/` and `.claude/skills/wrap-up-session/`.

## [1.2.0] - 2026-09-24

### Added
- **New optional `local-delegate` component**: a free local-model draft for `/build`'s implement
  mode, gated by your own visible tests, before spending a turn on your main model. Off by default
  (ships with the new `local_delegate` variable empty) and safe to leave off — see
  `process/local-delegate/README.md` for the full mechanism, prerequisites, and limitations.
  Reverses `[1.1.4]`'s "deliberately deferred" decision now that the source repo's own design for
  this feature has fully settled (build and QA gate both done there, no open questions left).
  Ported and generalized into `spec` (the `(local-delegate: implement)` task marker and its
  eligibility rules), `build` (the Bucket A execution path and outcome logging), and
  `execution-gate` (the new Step 3.5 flag and its Step 6/8 reporting columns) — all three now say
  so explicitly rather than silently omitting the feature.

### Fixed
- `consolidate-docs` re-synced against source-repo drift: a mechanize-before-prose reminder added to
  both its Pruning-MISTAKES.md and Pruning-CLAUDE.md steps, generalized (no specific script name
  assumed — an adopter without an equivalent script builds their own, per the step's own suggestion).

## [1.1.5] - 2026-09-22

### Fixed
- `consolidate-docs` re-synced against source-repo drift: a third `MISTAKES.md` pruning shape
  (single-occurrence entries age out at 90 days with zero recurrence) and an optional
  growth-ratchet-baseline record step after each trim, generalized (no specific tool/hook name
  assumed — the exported `rules-doc-size` hook doesn't implement a growth ratchet yet, so that step
  is phrased as conditional).

## [1.1.4] - 2026-09-21

### Fixed
- `end-task`, `build`, `consolidate-docs`, `spec`, `execution-gate`, and `handoff` skills
  re-synced against their source repo after real drift accumulated since the last export pass
  (up to ~480 changed lines on `end-task`). The local-delegate feature content in `spec`/`build`/
  `execution-gate` (a runner script, a delegation-prompt-construction skill, a config field) is
  **not part of this export and won't be** — a permanent decision, not a "pending design settling"
  placeholder as `[1.0.1]` below originally described it. It's tied to the source repo's own local
  Ollama install and test suites; there's no standalone-shaped version of it to ship.
- `handoff`'s "Consuming a primer" step now explicitly warns that re-reading a moved file back is
  **not** sufficient to confirm a `CONSUMED` marker actually landed in a commit — only checking the
  commit itself does. A plain re-read shows current on-disk content, which can silently differ from
  what a `git mv` immediately following an uncommitted edit actually committed; this substitution
  error caused several real, otherwise-silent failures before being called out explicitly.

## [1.1.3] - 2026-09-20

### Added
- `verify` Step 2 now offers a `handoff`-style primer as an alternative to a third escalated
  `code-reviewer` pass, once two prior escalated passes have already failed to converge on the same
  finding — trades a subagent pass's zero-friction convenience for genuine live interactivity on the
  stronger model.

## [1.1.2] - 2026-09-18

### Changed
- `backlog` and `end-task` skills now spec a consistent presentation for the "still open" list
  shown after resolving an item or closing out a session: a short numbered list, one line per
  item, with a just-resolved item struck through in place rather than dropped.

## [1.1.1] - 2026-09-18

### Fixed
- `spec` Step 3.4's automatic design review now uses a real `AskUserQuestion` stop to offer
  skipping it, instead of a plain-text announcement followed by ending the turn to wait for a
  reply — brought in line with every other genuine decision point in this file, which already
  used `AskUserQuestion`. Updated `WORKFLOW.md`'s and `build/SKILL.md`'s cross-references to the
  old mechanism for consistency. (`build`/`spec`'s remaining drift is still the deferred
  local-delegate feature content — not touched here.)

## [1.1.0] - 2026-09-18

### Added
- New standalone component `schedule-wakeup-guard`: a `PreToolUse` hook that blocks
  `ScheduleWakeup` unless the session's own transcript shows a genuinely live `/loop` invocation,
  rather than a general "check back on this later" use it wasn't meant for.

### Fixed
- `implement-queue` Step 6.4's ship branch had no case for a tool that ships by manually
  republishing to an already-existing hosted page (a Claude Artifact, a wiki page) instead of a
  git push — such an item would have been silently archived as done with no actual republish.
  Added a `pending-publish` status, distinct from `blocked`, surfaced the same way through Step 7.

## [1.0.1] - 2026-09-15

### Fixed
- `code-reviewer` agent's `test_command` citation retargeted from `installer/variables.json` (the
  shipped-defaults copy, always empty) to `.claude/phase-gate-install/variables.json` (the resolved
  per-adopter value). Every adopter's reviewer previously reported "no automated tests were run"
  regardless of what test command was actually configured.
- Re-ported 7 of 10 components that had drifted from their source since the 2026-09-06 export:
  `periodic-audit`, `adopt`, `verify`, `handoff`, `end-task` (content already current or
  citation-only; hash records updated), `docs-writer` (its "invoking session re-checks fabricated
  references" section was re-generalized from the source's current wording; an initial pass
  wrongly re-added stale content instead and was caught and corrected by the QA gate),
  `implement-queue` (new repo-root-resolution step, untracked-file harvest fix, dev-server-lock
  guidance). `execution-gate` got one stale cross-reference fix. `build`, `spec`, and the remainder
  of `execution-gate`'s drift is local-delegate feature content, deliberately deferred pending that
  feature's own design settling — tracked as a follow-up, not included here.

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
