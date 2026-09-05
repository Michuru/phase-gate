# Workflow: the full project lifecycle, start to finish

A map of which skill handles which stage of turning a problem/need into shipped, archived, committed work.
The pieces (`work-backlog`, `design-gate`, `execution-gate`, `implement-queue`) each cover their own slice.
This file lays out how they chain together into one pipeline.

**This file cites other skills by named phase, not step number.** A skill's own step numbering can change
as it grows. Hardcoding a specific step number here would create a silent drift hazard nothing would
catch. If a skill's own step numbering changes in a way that would make a phase name below misleading,
update this file in the same pass.

---

## 1. A problem or need arises

A bug, a feature idea, a backlog item, or an ambiguous ask.

## 2. Tier check

Self-assess against `docs/methodology.md`'s four tiers, before touching anything:

- **Tier 4** (single-spot/single-file, no new UI, no schema change) → skip straight to **`work-backlog`**'s
  Full-investigation mode: state a one-line plan, investigate/fix/verify, `code-reviewer` only if a
  flagged surface, archive, commit. Done. The rest of this file doesn't apply.
- **Tier 1/2/3** (multi-file, new UI, shared-schema change, or a new tool/major rewrite) → **`design-gate`**.

## 3. `design-gate`'s design phase

`design-gate` covers more ground than just the design pass. Its own later phases are what sections 5 and
6 below expand on, not a separate process. Its design phase runs through several steps, in order. First,
confirm the tier out loud before any exploration. For Tier 1 only, ask immediately whether to switch to a
stronger model for the design pass. Draft the doc in Plan Mode: problem and scope, approach, a task
breakdown. Save the approved doc to `Design Docs/<slug>.md`. For Tier 1/2 designs, an automatic
design-phase review spawns immediately, before implementation or backlog questions come up, targeting a
model from a different family than the one that drafted the doc, with an opt-out window and a durable
record written to the doc regardless of outcome. Then ask whether to implement now, file it to
`BACKLOG.md` for later, or get another cross-model review pass. (Tier 3's two-way choice stays unchanged.
Tier 1/2 option (c) now means an *additional* pass, or a first review if the automatic one was declined
or failed.) Run any further cross-model review if chosen, then switch back to the base model once the
design pass itself is done.

## 4. Decision point A: does this design's task breakdown need an execution-strategy pass?

**Considering this pass is a mandatory, recorded checkpoint above the threshold below. Actually running
it stays fully optional.** `design-gate` Step 3.5 states a recommendation (run/skip) as part of its own
implement-now/backlog question once a design crosses the threshold, and records the outcome either way
under a `## Execution-gate consideration` heading. Whether `execution-gate` itself runs is always the
adopter's call.

- **Trivial** (1–2 tasks, confined to a single sub-part/component) → skip straight to section 5 below.
- **Substantial** (3 or more tasks **and** a real question of how they'd be delegated, ordered, or
  parallelized, not only a single, obviously-sequential track, **or** the design spans more than one
  independently-identifiable sub-part/component) → `design-gate` states a recommendation and records the
  outcome, then **optionally runs `execution-gate`**: the parallelization/Workflow-worthiness gate first,
  then per-task classification into buckets (Direct / `docs-writer` / fork / user-executed), a scrutiny
  label from a fixed vocabulary on every task including Direct ones, the rare check for a
  genuinely-independent parallel subset, and a written `## Execution strategy` section appended to the
  design doc.

## 5. Decision point B: one design right now, or several independent already-approved designs ready to go?

- **One design** → implement directly, task by task against the design doc (and its Execution-strategy
  section if one exists). This is `design-gate`'s own task-by-task implementation phase. Direct tasks run
  in the main session at their stated scrutiny level, `docs-writer` tasks go to that subagent, fork-flagged
  tasks fork off, user-executed tasks wait on the user, and any rare independent-subset tasks run via their
  own one-off `Workflow` call (not through `implement-queue`).
- **Several independent designs, each with no unmet prerequisite** → each gets added to `BACKLOG.md`'s
  "Ready to implement" checklist (`design-gate`'s backlog-it option does this automatically) → when ready,
  invoke **`implement-queue`**: read the queue, pre-run cleanliness check + capture the batch's
  `baseCommit`, confirm a batch (max 3, state agent count/cost), run the `Workflow`, harvest and commit
  sequentially with the stray-commit/forbidden-path anomaly checks, batch any blocked-item questions,
  checkpoint between batches, close with a final summary.

## 6. What happens at the end, regardless of which path was taken

This is `design-gate`'s own post-implementation phases, plus this methodology's standing archive/commit
conventions, not a separate process:

1. **QA gate**: an independent `code-reviewer` pass, mandatory for any Tier 1/2/3 work, or a Tier 4 fix on
   a flagged surface (see `flagged_surfaces` in `installer/variables.json`). Re-verifies against real data
   and regression suites. Never trusts the implementer's own claim.
2. **Docs sync**: mechanical `NOTES.md`/rules-doc-pointer updates, delegated to `docs-writer`.
3. **Archive**: move the resolved `BACKLOG.md` entry to `BACKLOG_ARCHIVE.md` verbatim, citations included.
4. **Commit**: per this methodology's standing local-commit authorization (see `docs/methodology.md`).
   One commit per resolved item, narrow staging, message drafted from the `BACKLOG.md` entry.
5. **Tool-specific extra gate, if any**: some tools have their own publish/deploy step. If so, "resolved"
   also requires that step to have actually happened, not only that the fix works locally.
6. **Display what's still open**: show every remaining open `BACKLOG.md` item across all sections, every
   time, without being asked.

---

## Parallel process: externally-submitted PRs

For PRs submitted by an external contributor, use **`review-pr`** instead of the numbered workflow above.
It handles repo/PR resolution, delegates to code-review/security-review, posts a real GitHub review,
reports merge status, and prompts a merge-now-vs-hold decision, independent of the design-gate/
implement-queue pipeline.
