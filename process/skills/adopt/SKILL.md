---
name: adopt
description: Scope phase-gate onto a project that already has real code or a scope/spec document but no Design Docs/BACKLOG.md history yet — a one-time inventory pass (what's built vs. what's missing, cited) before anything else runs. Use when /initiate detects this case, or when the user explicitly asks to adopt phase-gate onto an existing project.
---

# Adopt: scope phase-gate onto an already-in-progress project

Split out from `initiate`'s own onboarding case, if you have that skill installed — `initiate`
only detects this case (a two-line check: no `Design Docs/`/`BACKLOG.md` history yet, but real
existing code or a scope/spec document → "run `/adopt`") and hands off here for the actual body,
keeping this once-per-project cost off `initiate`'s hot path.

## Step 1: Scope the project

If there's no `Design Docs/`/`BACKLOG.md` history yet for this project, but the repo already has an
existing scope/spec document (an architecture doc, a feature spec) or substantial existing code, do
a scoping pass before anything else: reconcile the project's own scope/spec/README (or a specific
request, if one was already given) against the actual code — what is already built (cited by
file/section), what is genuinely remaining. **This scoping pass stops at inventory** — what exists
vs. what's missing, cited — it does not extend into weighing implementation approaches, which stays
gated behind `spec`'s own tier call.

**Write the inventory down as a durable artifact, not just a transcript message** — a real adoption
session against an existing project can produce exactly this kind of inventory live and then lose it
entirely if the session ends with nothing written to disk. **Destination and format, so this isn't
left to the executing agent to invent each time**: write it to `Design Docs/<slug>-inventory.md` in
this project's own repo root (creating `Design Docs/` if it doesn't exist yet — this scoping pass is
what's introducing the process to the project, so the folder not existing yet is expected, not a
blocker). Mark it `Kind: deliverable` / `Status: done` — an inventory is a one-time snapshot, not an
ongoing item, and giving it `Kind: work-item` would wrongly make `initiate`'s own signal check treat
it as perpetually in-flight on every future run.

If the remaining scope splits into multiple independently-designable areas, say so explicitly and
ask (`AskUserQuestion`) which one to run through `/spec` first — note every area *not* picked
directly in this same inventory doc, as remaining/not-yet-scoped, rather than creating separate stub
docs for the deferred areas — never bundle unrelated areas into one design doc just because they
came up together.

## Step 2: Name the next command

Recommend **`/spec`** for the area just picked — the ordinary work-axis entry point, same as any
other new item, now that a real inventory exists to design against. Named alternative: **`/backlog`**
it instead, if none of the remaining areas are ready to design yet.

## Notes

- **Once per project.** This body only ever runs when there's no `Design Docs/`/`BACKLOG.md` history
  yet — after this first pass, every future session's `initiate` check for "no process history" comes
  back false and this skill is never invoked again for the same project.
- **Cross-reference, never duplicate.** If you have `initiate` installed, it keeps a cheap two-line
  detection for this case rather than folding this body back into its own hot path — this
  once-per-project cost stays off `initiate`'s critical path; this skill just gives it a proper name
  and a next-command line of its own.
- **Local-model fit: not applicable.** Reconciling a scope doc against real code is open-ended
  judgment (what's actually built vs. claimed) — not a good fit for a deterministic check or a small
  local model.
