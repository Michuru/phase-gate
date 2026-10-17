# spec: the automatic design review (Tier 1 and 2)

Read from `SKILL.md` when a Tier 1 or 2 design has been saved. The "a review defers the decision, it does not answer it" guardrail and the paste-findings-in-chat rule are in `SKILL.md` and apply to everything here.

## Contents
- Pick the reviewer
- Spawn it
- Show the findings
- Ask before spawning
- Opt-out and failure
- Record it
- Further passes: the two paths
- After the review

## Pick the reviewer

A fresh context on a **different model than the drafter** is the requirement; which model is decided by tier (a Fable-first default on every tier collapsed the cost ladder to one rung, with nothing graduated below the priciest option).

- **Tier 1**, in order: (1) your most differentiated available model (for example Fable), when available and the draft was not itself written on it (a design drafted on that model goes straight to option 2: reviewing it with the same model again would be a same-model pass at the top of a ladder meant to avoid exactly that); (2) **another Claude-mainline model** (Sonnet- or Haiku-drafted: `model: opus`; Opus-drafted: `model: sonnet`; drafted on the most differentiated model: the strongest Claude-mainline model); (3) **the same model in a fresh context**, only when nothing else is available.
- **Tier 2**, in order: (1) **another Claude-mainline model** (Sonnet- or Haiku-drafted: `model: opus`; Opus-drafted: `model: sonnet`, the most common pairing); (2) **the same model in a fresh context**, only when no other Claude-mainline model is available. Your most differentiated model is **not** part of Tier 2's automatic default; it stays reachable as an explicit further pass (option (c) in `SKILL.md`).

Every option in these ladders, the most differentiated model included, is a Claude model: what buys the independence is the fresh context plus a different model than the author, not a different vendor. Check your own recorded model-availability configuration before picking a target (resolved upward from the current repo if this session is in a nested sub-repo, like the Tier 1 model check). Never assume your most differentiated model is available for Tier 1 and never reach for it automatically on Tier 2. The review heading names the actual reviewing model every time (`## Design review — Fable`, `— Opus`, `— Sonnet, fresh context`) and claims nothing more; a same-model pass is never labeled cross-model. The review still runs when only the weakest option is reachable: silently skipping for lack of a stronger independence reverses the point of the step.

## Spawn it

A plain `Agent` call, **not** `code-reviewer` (it has no `Edit` or `Write` and is tuned to review an implementation's diff against a design doc, not the doc itself), with the target model override. Tell it to read `Design Docs/<slug>.md` (plus whatever it cites) cold and return a structured review as its final answer. The main session then appends that report into the `## Design review` section opened `pending` at draft time: a relayed report, not something the subagent writes into the doc.

## Show the findings

Paste the findings into the chat response itself, in full, as an explicit numbered list, at the same time they are written into the doc: every finding and the closing verdict. Filing them only in the `.md` leaves the user a compressed "review done, found some gaps" they cannot act on. The same applies to any synthesis proposed on top of a review: show the actual proposed changes.

## Ask before spawning

Use `AskUserQuestion`, not a plain-text announcement (a sentence can blend into the response and be missed; this is the only point where declining is actually reachable). Name the real cost in the question (for example "this spawns an Opus-priced review pass"), with options to run it now (recommended) or skip it for this design.

**Offer a third option, "run it, then a second pass", whenever a genuinely different third model exists:** the strongest model that is neither the drafter nor the first reviewer (Tier 2: typically another Claude model first, then the strongest model you have; Tier 1: the strongest first, then another Claude model). The second pass receives the design doc **plus the first pass's report**; say that trade-off in the option text (the second reviewer can adjudicate the first's claims but is also anchored by them). If no such third model exists, omit the option and say so out loud rather than offering a same-model pass dressed as a second opinion. Name each pass's cost separately in the option text. One answer authorizes both passes: run them back to back, paste each pass's findings into chat as soon as it returns, and propose one combined synthesis at the end rather than one per pass.

## Opt-out and failure

If the user picks skip, skip it and record the decline the same way a completed review is recorded. If the spawned subagent errors or times out, report that plainly (never treat it as if it ran clean) and fall through the same way. In both cases option (c) in `SKILL.md` reverts to meaning a *first* review.

## Record it

Whether the review ran and found something, ran clean, was declined or failed, update the `## Design review` heading's status in place: `done`, or `blocked: declined by user` or `blocked: subagent failed`, stating which of the four happened. The design doc, not the transcript, is what a future session reads. **A two-pass review stays one section**: `## Design review — done, Opus then Fable`, with `### Pass 1 — <model>` and `### Pass 2 — <model>, given pass 1's report` beneath it, each pass's findings relayed under its own sub-heading. The heading names the actual reviewing models and claims nothing else. If pass 2 fails after pass 1 succeeded, write `done, <model 1>` and add a `### Pass 2 — <model>: failed, <why>` line rather than marking the whole review blocked. (This is the same remedy `execution-gate` uses for its recorded decline: a silent stop is indistinguishable from the step never having run.)

## Further passes: the two paths

A second model reading the design catches a different class of issue than the same model re-checking its own work, and the more the reviewer differs from the drafter the more that holds: a closely related pass tends to catch internal inconsistency, a more differentiated one tends to catch what the first pass took as given. The two ways to get a further pass are not interchangeable:

- **Subagent pass (cold, filtered):** spawned directly with a `model` override; zero shared context, it sees only the saved doc and what its prompt points at. No user action needed, which is what makes the automatic review possible. What comes back is a relayed report the user cannot question directly.
- **Direct switch (unfiltered, contaminated):** the user runs `/model` and the same running session reviews, having seen the whole conversation. It is unmediated, with no relay, and the user can push back on the reviewer in the same thread. **Known limitation:** if this session also authored the design, it reviews a doc against its own just-written reasoning, the weakest independence available. Prefer the subagent path when independence matters more than interrogating the reviewer live.

State this trade-off wherever either is offered. Whichever path ran: **append the review as a new section, never overwrite or merge it into the original design** (the baseline must stay visible so the comparison is real); tag findings by strength of claim; and close with a **synthesis section**, a priority-ordered consolidated list of proposed changes each citing which review raised it, plus what every pass agreed should stay. **Mark it proposed, not applied.** Ask the user which changes to adopt before touching the design doc or any backlog it feeds. On the direct-switch path, where there is no subagent prompt, the reviewing model writes the result line itself as the last line of its review block.

## After the review

Once the review, the synthesis and any follow-up decisions are settled, return explicitly to the implement-or-backlog question in `SKILL.md` before anything is implemented or backlogged.
