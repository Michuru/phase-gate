# spec: the Tier 1 model check

Read from `SKILL.md` for a Tier 1 design only, before any exploration or drafting. Tier 2 and 3 never prompt this.

Real architectural ambiguity is the "cost of a wrong assumption is high" case the design-doc gate exists for, so ask via `AskUserQuestion`, as the very first action after the tier is confirmed, whether to switch to **the strongest model you have** for this design pass. Make it a genuine offer with a one-line explainer (deeper reasoning for ambiguous architecture calls), not an assumption.

**Which model is "the strongest you have":** check your own recorded model-availability configuration. If a more differentiated model (for example Fable, itself a Claude model and not a different vendor, just more differentiated in training and personality than the mainline ladder) is available, it outranks every entry in your Claude-mainline model ladder; only when none is reachable use the strongest Claude-mainline entry. This is a different question from the design review's reviewer ladder, which deliberately does not reach for a more differentiated model automatically on Tier 2: do not reuse that answer.

**If the strongest available model is already the one running, say so out loud** instead of skipping the question silently, so a design that never escalated never looks identical to one that did.

## Offer three paths, and state the real trade-off in the question

The user cannot weigh options whose cost they cannot see, so put the trade-off in the `AskUserQuestion` text itself, not only three labels.

- **(a) Live `/model` switch.** Full interactivity, same window, no window swap. Costs a full session recache at the new model's rates (real money and time on a long session). Simplest when the session is short enough that the recache does not matter.
- **(b) A cold fresh-subagent `Agent` call** on the target model. No recache cost and no window swap. Costs all interactivity: one self-contained prompt in, one final report back, no mid-design course-correction. Best for a narrow, self-contained design question.
- **(c) A handoff-style primer.** Write a primer as the `handoff` skill's outgoing steps would (goal, tier reasoning, any pointers already known; there is normally little else this early), and the user opens a **separate window** on the target model and pastes it in. No recache cost and full interactivity, but real friction neither (a) nor (b) has: a second window to manage and a manual hand-back when the design pass is done. Better the more the design pass will need live back-and-forth on the stronger model. Do not oversell it: it is a third point on the cost and interactivity trade-off, not a strictly better replacement.

## Do it early

Asking late defeats the purpose: the deeper reasoning is wanted *during* drafting, not after a full plan was written on the weaker model. If a design pass is already underway and this step was skipped, do not wait for a natural stopping point: ask now, before writing anything further.
