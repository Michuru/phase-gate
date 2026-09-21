---
name: execution-gate
description: Analyze one already-decided design doc's own task breakdown and decide, task by task, how it should actually be executed — stays on the main model (at what scrutiny level), delegates to docs-writer, forks for context hygiene, or is blocked on the user — plus whether a genuinely-independent subset is worth a one-off parallel Workflow call. Runs automatically as /build's opening gate whenever implementation actually starts (no approval question) — still directly invocable standalone too, e.g. to preview cost before deciding. Does not execute anything itself, and does not replace implement-queue (which parallelizes across several already-approved separate designs, not within one).
---

# Execution gate: decide how one design's tasks should run

`spec` produces the design doc and its task breakdown. `implement-queue` parallelizes several
already-approved, separately-scoped designs against each other. Neither owns the gap this skill fills:
taking **one already-decided design's own task list** and deciding, task by task, whether it stays on the
main model (and at what scrutiny level), gets delegated to `docs-writer`/`code-reviewer`, gets forked off
for context hygiene, belongs to the user, or — rarely — forms a genuinely-independent subset worth a
one-off scoped `Workflow` call. This is a **planning-phase refinement skill**: it executes nothing itself,
it decides how execution should happen.

## Step 0: Worth running at all?

If the design doc's task breakdown has only 1–2 tasks, or raises no real delegation/parallel question,
say so in one line and stop — don't run the rest of this process for its own sake.

**Write that one-line decline into the design doc's `## Execution strategy` section anyway, dated.** A
silent stop is indistinguishable from this skill never having been invoked — the same failure
`spec`'s own Step 0 was written to prevent. Recording the decline is cheap; recording nothing is
not distinguishable from "never checked."

## Step 1: The parallelization/Workflow-worthiness gate — and the `/implement-queue` eligibility check

Run this first, before classifying any individual task. The question is **logical dependency and
file-level overlap**, not shared state: does task N's output feed task N+1 (a strict sequence), or would
two candidate-parallel tasks edit the same file or region? If yes to either, state explicitly "not a
parallel-`Workflow` candidate — execute sequentially," and skip Bucket E (Step 4) for every task in this
design.

**Shared git state alone does not disqualify, and must not be treated as if it does.** `implement-queue`
already runs parallel agents against this repo's single git history today, and solves it structurally via
worktree isolation (its Step 2's single captured `baseCommit`; its Step 5's scoped-patch application that
never merges or fast-forwards a worktree branch). Reading "concurrent agents might touch git" as
disqualifying would disqualify every design in this repo and make Bucket E permanently dead code. A real
disqualifier looks like a repo-restructure precedent: a strict task-to-task sequence where a later task
rewrites history/state the rest depend on — a dependency chain, not a concurrency hazard.

**Run a second, independent check here too: whole-design `/implement-queue` eligibility — not just Bucket
E's parallel-worthiness.** `implement-queue`'s Step 6 anomaly check treats any touched path under
`CLAUDE.md`, `BACKLOG.md`, `BACKLOG_ARCHIVE.md`, `MISTAKES.md`, or anything under `.claude/` (skills,
workflows, settings, hooks) as tainted — those are the forbidden paths `GIT_BOUNDARY` reserves to the
harvest step alone, so a queued run of such a design would flag nearly every item as tainted and harvest
nothing. If **any** task in this design's own breakdown touches one of those paths, the **whole design**
is disqualified from `/implement-queue`'s "Ready to implement" checklist — independent of Step 1's
parallelization test above, and regardless of how independent the design's own tasks are from each other.
A design can pass the dependency/overlap test and still be forbidden-path-disqualified, or vice versa;
check both. State this disqualification explicitly and record it as the design's `/implement-queue`
eligibility verdict in Step 6's Execution-strategy section (not left implicit, and not folded into Bucket
E's note) — if disqualified, the design stays tracked wherever it already lives (its own tool section, or
a cross-cutting section like `BACKLOG.md`'s "Environment / machine setup") rather than added to the
"Ready to implement" checklist, and Bucket E (Step 4) is skipped for the whole design too, since the same
disqualifier applies to both queues. This exact scenario has happened once by hand already: a design doc
for this very kind of execution-planning work had most of its own tasks touch forbidden paths and had to
be pulled from the checklist and tracked manually before this check existed as a repeatable step.

## Step 2: Classify every task into exactly one primary bucket

Every task in the breakdown lands in exactly one of:

- **A — Direct/main-model.** Executed in the main session.
- **B — `docs-writer`.** Mechanical docs-sync work with the decisions already made.
- **C — Fork for context hygiene.** Independent work worth keeping out of the main transcript, not
  primarily a cost play.
- **D — User-executed / blocked on user action.** Not Claude's to execute at all — a task the user must do
  themselves (rotating a credential, an out-of-band confirmation), or a task blocked pending user input.

**No task may be left unclassified.** Bucket D is not optional bookkeeping — some designs have tasks
marked `(User)` in their own body, and without an explicit bucket for them they either get silently
mis-bucketed as Direct or survive only as a prose aside.

**If one numbered task in the design's own breakdown bundles sub-actions that belong in different
buckets** (a Phase-0-style task combining a user-executed credential step with a mechanical docs update; a
durability/backup task combining a user-decided setting with routine automated setup), classify at that
sub-action's own granularity rather than forcing the whole task into one bucket. Say so explicitly in the
Step 8 table (e.g. "Task 1a/1b: D, Task 1c/1d/1e: B") rather than picking whichever bucket applies to most
of the bundle and silently absorbing the rest.

## Step 3: Layer the QA-gate flag on top

This is deliberately **not a fifth bucket** — it's an independent flag stacked on whichever of A–D
executed the task, never a peer a task lands in *instead of* one of those. Flag a task for an independent
`code-reviewer` pass when your rules doc's flagged-surface rule applies, the action is irreversible, or the
standing Tier 1/2/3 QA-gate rule requires it regardless.

## Step 4: Check for a genuinely-independent parallel subset (Bucket E) — rare

Only if Step 1 didn't already disqualify the whole design: check whether a genuinely-independent
multi-task subset exists *within* this one design. Expect this to be **rare** — most single-design task
lists are at least loosely interdependent by construction, since they're steps of one coherent design, not
several separate designs.

If found, this becomes **Bucket E**. Its output is a *recommendation to author a one-off, scoped
`Workflow` call* for just that subset, reusing `implement-queue`'s proven worktree-isolation and
harvest-anomaly-check pattern — **never** a queue entry for `implement-queue` itself. That skill's own
checklist mechanism expects each item to be a whole, independently-implementable design
(`{designDocPath, backlogEntryText, toolName}`), not a task fragment pulled out of a larger one.

## Step 5: State a scrutiny label for every task, from a fixed vocabulary

State a scrutiny label for **every** task, including every Bucket A one. Free prose doesn't work here —
different sessions describe the same kind of risk in incompatible ways ("trivial", "genuinely dangerous",
"needs explicit go-ahead", "foundational"), which can't be compared, sorted, or checked for completeness.

Use exactly this vocabulary, two orthogonal fields per task:

- **stakes** — exactly one of `routine` / `verify-after` / `high-stakes` / `irreversible`. This is an
  ordered scale; a higher label subsumes the lower ones' obligations.
- **approval** — exactly one of `none` / `explicit-go-ahead`.

Write both together per task, e.g. `high-stakes / explicit-go-ahead` or `irreversible / explicit-go-ahead`
— a task can be both the one-way door and gated on the user's go-ahead at once; a single exclusive label
can't express that.

## Step 6: Write the result as a new `## Execution strategy` section

Append this section to `Design Docs/<slug>.md` — **append, never overwrite**, the same convention as
`spec` Step 3.6's cross-model review. Once the section's content has been adopted elsewhere, it may
later be *trimmed*, provided the full text stays recoverable and the doc names the commit that carries it.
Trimming after adoption is not a violation of the append-only rule; overwriting in place is.

**This section is the strategy's single source of truth.** A `BACKLOG.md` checklist entry may carry at
most a pointer to it, or a one-line summary explicitly marked as derived — never a second full copy that
can drift out of sync with this one.

**Always include the `/implement-queue` eligibility verdict from Step 1's second check** — eligible, or
disqualified-forbidden-path with the offending task numbers and paths named — even when the design was
never destined for the checklist at all. This is a distinct line from Bucket E's recommendation (Step 7):
Bucket E is about an independent *subset* running its own scoped `Workflow`, this verdict is about whether
the *whole design* may ever appear on `BACKLOG.md`'s "Ready to implement" checklist as a single queue item.

## Step 7: Note Bucket E's recommendation in the same section

If Step 4 fired (rare), note the recommended scoped-`Workflow` approach inside the same Execution-strategy
section — this is guidance for whoever executes the design, not a `BACKLOG.md` checklist entry.
`BACKLOG.md`'s "Ready to implement" checklist stays reserved for whole separate designs, exactly as
`implement-queue` already expects it.

## Step 8: Report before anything downstream runs

Report to the user before implementation, `implement-queue`, or any fork actually starts. The report must
include:

1. **An enumerated task-number-to-bucket table covering every task in the design**, so an unclassified
   task is visible rather than assumed away. "No task left unclassified" is a *checked* output here, not
   just an instruction back in Step 2.
2. **The `/implement-queue` eligibility verdict from Step 1's second check** — state it plainly (eligible,
   or disqualified-forbidden-path and why) so the user knows before deciding whether to backlog this design
   onto the checklist at all.
3. **The projected cost of the recommended strategy** — how many `docs-writer` calls, forks,
   `code-reviewer` passes, and (if Bucket E fired) `Workflow` agents it implies. `implement-queue` already
   states agent count and rough spend before running so the user's yes is informed; this skill's entire
   output is "run these tasks this way," and that number shouldn't go unstated here either.
4. **A plain-prose model recommendation, only when one is genuinely warranted.** If a Bucket A task or a
   QA-gate `code-reviewer` pass would clearly benefit from a non-default model (real design judgment calling
   for a stronger model, a maximally differentiated review calling for a different one), say so directly in the
   report — the same pattern `spec` Step 1 already uses for its model-switch offer (an
   `AskUserQuestion`, not a fixed field). Most tasks need no model call-out at all; don't manufacture one.
   This is deliberately **not** a third scrutiny field alongside Step 5's `stakes`/`approval` — see the
   Notes section below for why.

**Note for Tier 1/2 designs reaching this stage:** A Tier 1/2 design has already had its automatic
design-phase review via `spec` Step 3.4 (run before Step 3.5, before implementation/backlog/further-review
questions are even asked). This Step 8 cost line covers only the *implementation* cost — do not re-propose
a design-level cross-model review pass as part of your execution strategy. Step 3.4's review is sunk cost
by the time this step runs, not a projected expense to account for here. **Keep this separate from Step 3's
QA-gate flag above** — that flag covers *implementation* QA on executed tasks (a different concept from the
design-phase review), and conflating the two risks a future session treating implementation QA as
pre-satisfied by Step 3.4's design-phase pass when they're actually independent concerns. Step 5's reactive
QA-burst escalation (a `spec`-scoped feature) is also outside `execution-gate`'s scope entirely.

## Notes

- Whether *running* this skill should become a required step, rather than opt-in/standalone, was an
  open question for a while. A narrower version resolved first: *considering* this skill (stating a
  run/skip recommendation, recording the outcome) became a mandatory, recorded checkpoint in `spec`
  Step 3.5 whenever a design's breakdown is substantial. **The broader question is now answered too
  — but as *waived*, not *satisfied*.** `/build` runs this skill automatically as its own opening
  gate, with no approval question (see `build/SKILL.md` Step 1) — in practice this makes running it
  mandatory for any Tier 1/2/3 design implemented through the normal path, without your rules doc's
  tiered-work section ever having to state a separate rule for it. The user made this call directly
  rather than because some original evidence bar was cleared — record that distinction (waived by
  direct decision, not satisfied by evidence) if your own history of this skill's design still
  records the older open question, rather than silently erasing the prior position. This skill
  remains directly invocable standalone outside `/build` too, e.g. to preview cost before deciding.
- **No per-task model field, by design.** A per-project model plan (drafting on one model, reviewing on
  another, an occasional maximally-differentiated pass) is usually resolved by hand without real friction — not
  enough evidence to justify a new fixed-vocabulary field alongside Step 5's `stakes`/`approval`, and
  `stakes` doesn't cleanly imply a model choice anyway (an irreversible git push needs a human confirm,
  not a stronger model). Step 8's point 4 above (plain-prose recommendation, only when genuinely
  warranted) is the whole fix. Revisit only if a recurring, structured need shows up that this doesn't
  cover.
- **Local-model fit: not applicable.** Bucket classification requires judging irreversibility, stakes, and
  dependencies from context — open-ended judgment with no deterministic gate to check the output against.
  `spec/SKILL.md`'s own Local-model-fit note (Step 2) states the general principle this falls under: a
  local model is a plausible fit for the generation half of a propose → deterministic-gate → act
  pipeline, never for open-ended judgment/QA work with no deterministic gate — bucket, stakes, and
  approval classification is exactly that kind of work, so it stays on a full model regardless of how
  tempting a free local pass looks.
- For the full pipeline this skill fits into — from a problem arising through `backlog`/`spec`
  and on to `implement-queue` and the standing QA/docs-sync/archive/commit conventions — see `WORKFLOW.md`
  at the repo root.
