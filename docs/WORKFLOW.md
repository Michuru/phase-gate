# Workflow — the full project lifecycle, start to finish

This file maps two independent axes, not one linear pipeline. See
[methodology.md](methodology.md)'s opening section for the full mission statement and rationale.

**Work axis** — a work item's own lifecycle: `/backlog` → `/spec` → `/build` → `/verify` → `/ship`
→ back to `/backlog`. Four gates fire automatically between these phases — tier check, design
review, execution, QA — never asked about except the design review's own announced opt-out
window.

**Session axis** — the operator's own context lifecycle, orthogonal to the work axis: `/initiate`
at the start, `/handoff` when context fills at any phase, `/end-task` to close out (absorbing
narrow-commit and full-sync depth modes). `/consolidate-docs` is a self-firing threshold gate. This axis exists
only because the collaborator is a context window rather than a person — no organizational SDLC
models it, and it's covered in its own section below.

**This file cites other skills by named phase, not step number.** A skill's own step numbering can
change as it grows. Hardcoding a specific step number here would create a silent drift hazard
nothing would catch. If a skill's own step numbering changes in a way that would make a phase name
below misleading, update this file in the same pass.

---

## The work axis

### 1. A problem or need arises

A bug, a feature idea, a backlog item, or an ambiguous ask.

### 2. Tier check (automatic gate, before `/spec`)

Self-assess against `docs/methodology.md`'s four tiers, before touching anything:

- **Tier 4** (single-spot/single-file, no new UI, no schema change) → skip straight to
  **`/backlog`**'s Full-investigation mode: state a one-line plan, investigate/fix/verify,
  `code-reviewer` only if a flagged surface, then `/ship` (if a deploy target exists) or archive
  directly, commit. Done — the rest of this file doesn't apply.
- **Tier 1/2/3** (multi-file, new UI, shared-schema change, or a new tool/major rewrite) →
  **`/spec`**.

### 3. `/spec` — the design phase

Covers more ground than just drafting, in order: for a project with no `Design Docs/`/`BACKLOG.md`
history yet, deferring to **`/adopt`**'s scoping-inventory pass first; confirming the tier out
loud before any exploration; for Tier 1 only, asking whether to switch to the strongest available
model, immediately; drafting the doc in Plan Mode (`## Intent`, `## Problem`, `## Approach`, a
local-model-fit check, a task breakdown, plus an owed `## Design review — pending, <model>` line
and, if the breakdown looks substantial, an owed `## Execution strategy — pending` line) with a
`Kind: work-item` marker; saving the approved doc to `Design Docs/<slug>.md`; the automatic
design-phase review (Tier 1/2 only — see the gate below); then asking whether to (a) implement now
via `/build`, (b) file it to `BACKLOG.md`'s "Ready to implement" checklist for later, or (c) get
another design review pass; switching back to the starting model once the design pass is done.

### 4. Design review (automatic gate, Tier 1/2 only, inside `/spec`)

Fires the moment the doc is saved — no `AskUserQuestion` deciding *whether* it runs, only an
announced turn boundary to opt out in before the subagent actually spawns. Target: a fresh context
on the most different model available, in preference order — **Fable** when available, else
**another Claude model**, else **the same model in a fresh context** (never labeled as more than it
is — see `installer/variables.json`'s `available_models`/`fable_available`). The result appends into
the doc's own `## Design review` section, whose heading names the actual reviewing model every time.

### 5. `/build` — implementation

Two modes: **single-design** (the common case — implement one already-approved design doc) and
**batch** (`implement-queue`, for several independent already-approved designs sitting on
`BACKLOG.md`'s "Ready to implement" checklist).

### 6. Execution (automatic gate, inside `/build`)

`execution-gate` runs as `/build`'s opening step, unconditionally — no approval question, cost
stated per its own cost-line requirement — but it stops itself (its own first step, "worth running
at all?") on 1-2 tasks or when there's no real delegation question. Classifies every task into a
bucket (Direct / `docs-writer` / fork / user-executed) with a scrutiny label from a fixed
vocabulary, checks for the rare genuinely-independent parallel subset, and writes the result to the
doc's own `## Execution strategy` section.

### 7. `/verify` — the QA gate

An independent `code-reviewer` pass against the design doc, never trusting the implementer's own
claim; confirms any recorded baseline metric's after-number was actually measured. Reactive
escalation to a stronger model (then Fable, if a third pass is needed) when the same finding
survives two consecutive passes.

### 8. `/ship`

For a work item with a deploy target (a `publish-*` skill exists for the tool): dispatches to that
skill for the actual publish mechanics (check locally, copy from source of truth, confirm before
visible to others, verify live), then owns archive-and-commit. For anything with no deploy target,
archive-and-commit stays with whichever of `/backlog`/`implement-queue` produced the item — `/ship`
states this split explicitly rather than leaving it inferred.

### Back to `/backlog`

Once shipped and archived, the loop returns to step 1 for the next problem or need.

---

## The session axis

The operator's own context lifecycle — independent of which work-axis phase is active, and can
fire at any point in it:

- **`/initiate`** — session start. Surveys a live `handoff` primer, `BACKLOG.md`'s
  implement-queue checklist, and every `Design Docs/` file's own `Kind:`/`Status:` record; routes
  to whichever is actually next, and always reports what's blocked and on whom.
- **`/adopt`** — a one-time scoping-inventory pass for a project with real existing code or a
  scope/spec document but no `Design Docs/`/`BACKLOG.md` history yet. `/initiate` detects this case
  and hands off here; runs at most once per project.
- **`/handoff`** — write a self-contained briefing so a fresh context window can continue the
  *same* in-progress task with zero shared history (not a session close-out), or resume from one
  at the start of a fresh session.
- **`/end-task`** — the parent-level session-close router. Detects unfinished work first and
  routes to `/handoff` if so; otherwise wraps up at narrow-commit depth (absorbs former `/commit`)
  or full-sync depth (absorbs former `/wrap-up-session`), whichever the docs-sync signal check
  calls for. `/handoff` is named as the alternative in every row, so it stays discoverable even to
  someone who doesn't know it exists.
- **`/consolidate-docs`** — a self-firing threshold gate, not a phase anyone invokes deliberately:
  nudges splitting a rules-doc section that's grown into dated narrative history into a companion
  notes file once it crosses a size threshold.

---

## Parallel process: externally-submitted PRs

For PRs submitted by an external contributor, use **`review-pr`** instead of the work axis above —
it handles repo/PR resolution, delegates to code-review/security-review, posts a real GitHub
review, reports merge status, and prompts a merge-now-vs-hold decision, independent of the
`/spec`→`/build` pipeline.
