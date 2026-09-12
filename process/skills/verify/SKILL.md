---
name: verify
description: QA gate for an implemented design — invokes code-reviewer to independently check the implementation against its Design Docs/<slug>.md, confirms any recorded baseline metric's after-number was actually measured, and reactively escalates to a stronger model when the same finding survives two consecutive passes. Use when the user invokes /verify, or a design's implementation (via /build) is complete and needs independent QA before /ship.
---

# Verify: the QA gate

Extracts `spec`'s former Step 5 into its own addressable phase, keeping its reactive-escalation
rules intact.

## Step 1: Independent QA pass

Invoke the `code-reviewer` subagent (announce it explicitly — "Delegating to `code-reviewer` to
verify against `Design Docs/<slug>.md`") to independently check the implementation against the
design doc and re-verify rather than trusting your own claim.

**If the design doc recorded a Step 2 baseline metric** (`spec`'s own Baseline metrics
checkpoint), confirm the after-number was actually measured and written down here too, not just
asserted — an unmeasured "this should be faster now" fails this gate the same way an unverified
correctness claim would.

## Step 2: Reactive escalation

Either party can trigger a higher-model pass when the current attempt isn't converging. Trigger on
concrete, checkable criteria, not vague judgment: `code-reviewer` reports the same specific finding
(same file, same root cause) across two consecutive passes, or a fix has been revised 2+ times
without resolving that same finding — or the user asks to escalate directly.

When triggered, propose one additional `code-reviewer` pass on **the strongest Claude model
available that isn't the one already reviewing** (check your own recorded model-availability
configuration — resolved upward from the current repo if this session is in a nested sub-repo,
same rule `initiate/SKILL.md` Step 1.2 uses). **Always start with a single escalated pass** — don't
jump straight to multiple models. If that pass *also* doesn't resolve the same finding, that's a
new, separate decision point for whether to add a third pass **on Fable, when available, as the
most differentiated model in the ladder** — never assumed upfront, and no more than one further
pass is proposed without stopping to reassess whether escalating models is even the right fix at
that point. State the cost each time ("this is a second/third `code-reviewer` pass, N total"),
mirroring `execution-gate` Step 8's own cost-line requirement.

## Step 3: Record the result

Write `## QA gate — done` (or `blocked: <what>` if escalation is still unresolved) into the design
doc, per the standard phase-record convention (`spec/SKILL.md` Step 3.1) — this is the record,
distinct from `## Verification`, which is the plan `spec` already wrote at draft time.

## Notes

- **Next command, if your setup uses a next-command contract**: once Step 3 writes `## QA gate —
  done`, the recommendation is **`/ship`**. Named alternative if escalation is still unresolved
  (`## QA gate — blocked: <what>`): stop here and surface the blocker rather than proceeding to
  `/ship` on an unresolved finding.
- **Scoped specifically to this gate — not a repo-level rule, and not reachable from `backlog`'s or
  `implement-queue`'s own separate QA loops**, since forked/`implement-queue` executors are
  fixed-prompt workflow stages that never run `spec`/`build`/`verify` at all (not because of any
  git-state restriction).
- Local-model fit: not applicable — QA/correctness verification is exactly the open-ended-judgment
  category local SLMs tend to be unreliable for; keep `code-reviewer` on a full model regardless.
