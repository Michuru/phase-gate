---
name: build
description: Implement an approved spec doc — runs execution-gate automatically as its opening gate (no approval question, cost stated, stopping itself when trivial per that gate's own Step 0), then executes the design's tasks at whatever bucket/scrutiny level the gate assigned. For several independent already-approved designs on BACKLOG.md's "Ready to implement" checklist, runs implement-queue as its batch mode instead. Use when the user invokes /build, or asks to implement/build a design doc that's already been approved via /spec.
---

# Build: implement an approved design

Covers `spec`'s former "Step 4: Implement task-by-task" phase, now genuinely automatic at its
opening gate rather than asking permission to check. Two modes — **single-design** (the common
case: implement one already-approved `Design Docs/<slug>.md`) and **batch** (several independent,
already-approved designs sitting on `BACKLOG.md`'s "Ready to implement" checklist, delegated
straight to `implement-queue`) — decided by what's actually being asked for, not a fixed choice.

## Step 0: Which mode?

- **A specific design doc named or clearly implied** (the user just approved one, or points at a
  `Design Docs/<slug>.md`) → single-design mode, below.
- **"Run the queue" / "build what's ready" / no specific design named, and `BACKLOG.md`'s "Ready to
  implement" checklist is non-empty** → batch mode: invoke `implement-queue` directly. Nothing
  further in this skill applies — that skill owns its own full flow end to end.
- **Both a specific design and a non-empty checklist** → ask which was meant, rather than guessing.

## Step 1: Run `execution-gate` automatically — no approval question

**This is the one behavior change from how implementation used to start.** Run `execution-gate`
against the design's own task breakdown as this skill's opening step, unconditionally — never ask
whether to run it first. State the cost per `execution-gate` Step 8's existing requirement (task
count, projected `docs-writer`/fork/`code-reviewer` calls) so the spend is visible, but don't wait
for a go-ahead before running it — announcing and running happen in the same step, unlike `spec`
Step 3.4's design-review announcement, which gets a real turn boundary to decline in (see Notes for
why the two are treated differently).

**"No approval question" means whether the gate runs at all — not its own report.** Deliver
`execution-gate` Step 8's full report as that skill already specifies, including its point 4
(a plain-prose model recommendation via `AskUserQuestion`, only when a specific Bucket A task or
QA pass genuinely warrants a non-default model) if it fires. That question is about resource
allocation for a task the gate already analyzed, asked before Step 2 below starts anything — it
doesn't gate whether `execution-gate` itself ran, so it survives this skill's no-approval-question
rule intact.

**Automatic means it always *decides*, not that it always does work.** `execution-gate` Step 0
("Worth running at all?") already stops itself on 1-2 tasks or no real delegation question — this
skill doesn't second-guess that self-limit or force the full process on a trivial design. The
failure this closes is a *skipped decision*, not a cheap design forced through a heavyweight gate.

If the design's own `## Execution strategy` section already shows `done` (a prior invocation
already ran this gate for the same doc), don't re-run it — proceed straight to Step 2 with the
existing strategy.

## Step 2: Execute per the recorded strategy

Reference the specific task/section from `Design Docs/<slug>.md` for each implementation step,
the same way `backlog` anchors fixes to a `BACKLOG.md` entry (mirrors `spec`'s former Step 4).
Route each task per `execution-gate`'s own bucket assignment from Step 1 above:

- **Bucket A (direct)** — executed in the main session, at the stated scrutiny level.
- **Bucket B (`docs-writer`)** — delegated to that subagent.
- **Bucket C (fork)** — forked off for context hygiene.
- **Bucket D (user-executed)** — wait on the user; never attempt it yourself.
- **Bucket E (rare, independent subset)** — a one-off scoped `Workflow` call for just that
  subset, per `execution-gate`'s own recommendation. Never routed through `implement-queue` — that
  skill's checklist mechanism expects a whole separate design, never a task fragment of one.

**Write `## Build — running` into the design doc the moment this step starts** (write-on-entry,
per `spec/SKILL.md` Step 3.1), and update it to `## Build — done` (or `blocked: <what, on whom>`
if execution stalls) once every task above is finished. This is the phase record `/initiate`
Step 1.4 reads to tell "mid-build" apart from "never started" — the exact gap `spec/SKILL.md`'s
own §3 table was written to close.

## Step 3: Everything Step 3.5's old machinery still owns

Three things that used to live inside `spec` Step 3.5, still apply and still live there, unchanged
by this skill's existence — `build` doesn't own backlogging, only implementing:
- The forbidden-path test and the "Ready to implement" checklist add/skip.
- Auto-commit-on-(b) when a design is backlogged instead of implemented now.
- `implement-queue` Step 1's own prerequisite rule (a pending cross-model review satisfied once
  `spec` Step 3.4 ran) — **unchanged by this task**: eligibility for the checklist never depended
  on `execution-gate` having already run (it was always optional before, and now always runs
  automatically inside `/build` itself, never before backlogging) — so there's nothing here for
  this skill to add a prerequisite for.

## Step 4: Hand off to `/verify`

Once every task is done, invoke `/verify` — it owns the QA gate (independent `code-reviewer`
pass, reactive escalation, and writing the `## QA gate` record) as its own work-axis phase. Don't
reimplement any of that here; this step is a handoff, not a second copy.

## Notes

- **Why the design review gets an opt-out turn boundary and this gate doesn't.** `spec` Step 3.4
  spawns a differently-priced subagent pass on a design that hasn't been touched yet — a real,
  reversible-only-by-not-spending decision worth a pause. This gate is a main-session analysis pass
  over a design already approved for implementation, and it stops itself on trivial designs per its
  own Step 0 — different cost shape, different treatment.
- **This answers a question `execution-gate` used to leave deliberately open**: whether running it
  should ever become mandatory rather than opt-in. The answer here is that `/build` runs it
  automatically as its own opening gate, with no approval question (see Step 1) — in practice this
  makes running it mandatory for any Tier 1/2/3 design implemented through the normal path. The
  user made this call directly rather than because some prior evidence bar was cleared — record
  that as **waived by direct user decision**, not as if the original precondition was satisfied,
  if your own `execution-gate` doc still records the older open question.
- Local-model fit: not applicable — this skill is dispatch/orchestration over an already-decided
  design and an already-scored task breakdown, not a generation task.
