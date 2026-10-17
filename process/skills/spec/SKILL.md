---
name: spec
description: Write a short design doc before building a Tier 1, 2 or 3 change (several files, new UI, a shared data-file schema change, a brand-new tool, or a major rewrite). Use before implementing any request that touches more than one file, adds new UI, changes a shared data file's schema, starts a new tool, or rewrites an existing tool's architecture, even if the user did not ask for a plan or design doc by name.
---

# Spec: write the doc before the code

This repo's `backlog` flow handles small single-spot fixes well. This skill covers work big enough that typing code immediately risks a wrong assumption that is expensive to unwind: a new tool's data model, a rewrite's architecture, a feature touching several files.

## Tier check (first, before any exploration, research or drafting)

Do this immediately, whether Plan Mode was entered literally (the user asked) or inferred; a tier call made after exploration has started is too late to inform it.

- **Tier 3**: touches more than one file, adds a new UI section, tab or control, or changes a shared data file's schema, **and closely mirrors an already-shipped, already-tested pattern elsewhere in the same tool or repo**, verifiable by direct comparison, not fresh judgment.
- **Tier 2**: the same shape, but **no clean existing pattern to mirror**: a real choice between reasonable approaches, or consequences expensive to get wrong (a shared-schema change other tools depend on, a binding constraint the design must never violate).
- **Tier 1**: a brand-new tool, or a major rewrite or consolidation (anything the "before any large or risky rewrite" commit trigger covers), or the first thing distributed beyond this repo (a new standalone repo, a public artifact, anything for someone else's machine: a wrong assumption there reaches past this repo).

The Tier 2/3 call is one question: **is there an already-shipped, already-tested pattern in this repo that I am directly copying, or am I making a real design choice?** Decide it now, not mid-plan. If unsure, default to Tier 2: the design review fires automatically, and an unnecessary review costs minutes while a missed one brings back the wrong-assumption risk. The rule is fixed because the answer used to be an ad hoc judgment that came out differently for the same shape of request.

**State the tier out loud when the skill is invoked, before Plan Mode starts, with one line of why.** A silent skip looks identical to the check never having run, and a stated tier lets the user correct a wrong call before the rest builds on it. The tier decides what happens next: Tier 1 gets the model check below, Tier 2 the automatic design review once the doc is saved, Tier 3 neither. **For Tier 2, say explicitly that no model switch is needed yet** ("staying on the current model; a review fires automatically once the doc is saved"): Tier 2 drafts on the running model and brings a second model in only to review, and users have switched early assuming it works like Tier 1.

Single-spot, single-file, no new UI, no schema change is Tier 4: use `backlog` or normal editing, not this skill. If it is ambiguous which tier applies, use `AskUserQuestion` rather than guessing. If the project has no `Design Docs/` or `BACKLOG.md` history at all, run `/adopt` first (if you have it installed).

**Tier 1 only: before any exploration, read `${CLAUDE_SKILL_DIR}/references/tier1-model-check.md` and do it.** Tier 2 and 3 proceed on the running model.

## Draft the doc in Plan Mode

Use native Plan Mode (explore, design, stop for approval). **Refuse to draft Problem or Approach until the request's real requirements are confirmed**: say directly that a specific input is needed first ("I need to know X before I can propose an approach"). An ambiguity that is not surfaced out loud gets resolved silently by assumption, which is the risk this skill exists to catch. Keep the doc short, combining what a heavier process would split into charter, requirements and design:

- **Problem**: what it is for, plus an explicit out-of-scope line if an adjacent thing is obvious.
- **Approach**: the data model, architecture or UI shape, and which existing files and patterns it reuses.
- **Summary (plain language)**: written last, 2 to 4 sentences, no jargon. **Keep the actual boundary condition instead of flattening it**: a plain-language pass once dropped exactly the distinction that mattered in a real design (a narrow technical constraint became an overstated claim that contradicted a later, more accurate document).
- **Baseline metrics** (performance or optimization work only): one concrete before-number for whatever the change claims to improve (load time, runtime, file size, call count), recorded again as the after-number at the QA gate. Otherwise say in one sentence it is not performance-shaped.
- **Local-model fit**: one sentence on whether a local small model could power any part of this (`not applicable` is fine). **If the answer might be yes, read `${CLAUDE_SKILL_DIR}/references/local-model-fit.md` first.**
- **Task breakdown**: a sequenced list, so implementation can say "task 3" the way `backlog` items point at a `BACKLOG.md` entry. A task may carry `(local-delegate: implement)`: **before writing a marked task's contract text, read the local-model-fit reference above.**

Keep it proportional: a Tier 2 or 3 doc is a few paragraphs; a Tier 1 doc can be fuller but should still fit on one screen. A design that takes longer to write than the feature takes to build has failed at being lightweight.

## Save the approved doc

Save it to `Design Docs/<slug>.md` (create the folder on first use), not left only in the ephemeral Plan Mode plan file: implementation references this file, not conversational memory. At the top write a one-line `Drafted <date> on <model>` (the design review keys its target off this recorded value, never off whatever model happens to run later), then `Kind: work-item` (`Design Docs/` also holds `Kind: deliverable` docs, so a reader such as `/initiate`, if you have it installed, can tell them apart). **For Tier 1 and 2, also write `## Design review — pending, <model>` (the reviewer the design-review gate's ladder will pick, not the drafter) before approval is asked for**, and say so when presenting the plan, so an owed review is visible in the artifact. **If the breakdown is substantial** (3 or more tasks with a real delegation, ordering or parallelization question, or more than one independent sub-part), also write `## Execution strategy — pending`; `/build` fills it in through `execution-gate`. Open the body with `## Intent` (a sentence or two on what and why now), then `## Summary`, then `## Problem` and `## Approach`.

Later phases write their own sections by the phase-record convention. **Whenever you add or update a phase section, read `${CLAUDE_SKILL_DIR}/references/phase-records.md`** (the heading grammar, the status vocabulary, the section table).

## Design review (Tier 1 and 2 only; never Tier 3)

**It fires automatically for every Tier 1 or 2 design. The only thing that can stop it is the `AskUserQuestion` right before spawning.** Read `${CLAUDE_SKILL_DIR}/references/design-review-gate.md` now and follow it: the reviewer by tier, the spawn prompt, the question that names the cost (with an optional second pass), recording, relaying. **Paste the findings into the chat in full, as an explicit numbered list, the same turn** (filing them only in the doc is not enough), and show any synthesis as the actual proposed changes.

## Ask before implementing: plan approval is not implementation approval

Exiting Plan Mode approved the *design*. After saving, and for Tier 1 and 2 after the review (or its recorded decline or failure), use `AskUserQuestion` to ask:

- **(a)** start implementation now: this **invokes `/build`**, which runs `execution-gate` automatically as its opening step;
- **(b)** file it as a `BACKLOG.md` item pointing at the doc: **read `${CLAUDE_SKILL_DIR}/references/backlog-the-design.md` first**;
- **(d)** hand this session off to a fresh one with `/handoff`. Make it the recommended option, ahead of (a), when this session's context is getting full (the statusLine past about 60%, a context-usage nudge already shown, or a long chain of other work); otherwise offer it plainly as the choice for "I'd rather build this in a fresh window". It writes and commits the doc and its `BACKLOG.md` pointer first, then runs `/handoff` with `/build Design Docs/<slug>.md` as the fresh session's first action. Like (b), it does not start building here;
- **(c)**, for Tier 1 and 2 only: another review pass. After an automatic review it means an *additional* pass (a model other than the drafter and the first reviewer; a third pass only if yet another distinct model exists); after a declined or failed review it means a *first* review. Tier 3 never offers (c): its definition is "mirrors a shipped, verified pattern", which a cross-model review adds little to. For Tier 2 with no review run, lead with (c); for Tier 1, offer it as one option of three.

**A review defers the decision; it does not answer it.** After a review, its synthesis and any follow-up discussion, return explicitly to this question before writing or editing any implementation file. Engaging with questions *about the design* is not permission to build, "review first" never meant yes, and neither does a compliment on the plan: only an explicit choice counts.

## After the design pass

If the Tier 1 model check switched the session to a stronger model, that was for the design reasoning only. Once the doc is saved, the implement-or-backlog call is made and any review is wrapped up, say that part is done and switch back to the starting model (or ask the user to with `/model`); if backlogging, switch back immediately. The one exception, worth a one-line flag, is a data model with real remaining ambiguity.

Docs sync (a `NOTES.md` entry, a rules-doc pointer) goes to the `docs-writer` subagent, announced. A large single-file rewrite that is Tier 4 by scope still trips your rules doc's separate "before any large or risky rewrite" commit trigger.

If the conversation is compacted while you are inside one of the branches above, re-read that branch's reference before continuing.

## Notes

- Next command, if your setup uses a next-command contract: the ask-before-implementing question already closes the loop with one recommendation (a, `/build`) and one named alternative (b, `/backlog`), plus (c) for Tier 1 and 2. Never a silent stop once the doc is saved.
- Do not over-apply this: a one-line copy change or a single-function bugfix is Tier 4 even if it touches a file this skill would otherwise gate. The criteria are scope and, for the Tier 2/3 split, whether an existing pattern is being copied; not which file is involved.
- `Design Docs/` holds one file per project or feature, named `<slug>.md`.
