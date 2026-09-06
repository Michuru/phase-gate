---
name: initiate
description: Session-start dispatcher — surveys the project's own tracked state (a live handoff primer, the BACKLOG.md implement-queue checklist, every Design Docs/ file's own Kind/Status record) and routes to whichever is actually next, closing with an unconditional report of what's blocked and on whom. Use when the user types /initiate, asks "what's going on," "what should I work on," "what's in flight," or starts a session wanting to pick up wherever things left off.
---

# Initiate: the session-start dispatcher

Mirrors `end-task`'s own structure exactly (if you have that skill installed) — survey → signal
check → route → report — as its session-*start* counterpart. Same discipline: **thin dispatcher,
real delegation.** This skill detects and routes; it never prints its own backlog list, never
starts its own investigation, and persists no state of its own between invocations.

## Step 1: Survey

Gather the raw facts the signal check (Step 2) evaluates, in this order:

1. **Invoke `handoff` incoming mode unconditionally** — don't pre-check its directory first.
   Detection *is* `handoff` Step 0's own scan; it already discovers every sibling repo
   dynamically, handles the zero-primer case gracefully, and lists multiple live candidates for
   the user to pick from rather than silently guessing the most recent. Reimplementing that scan
   here would just do it worse.
2. **Determine whether this project has any process history at all.** Check for `Design Docs/`
   and `BACKLOG.md` in **the current repo, resolved upward** — a sub-repo nested under a parent
   may have neither of its own (both may live only in the parent), so check upward through
   parent directories before concluding "none." A naive same-directory-only check false-fires
   Signal 2 below on every sub-repo session. **Bounded, explicit algorithm** (this is a manual
   file-existence walk, not any harness-level rules-doc/skill upward-resolution mechanism — that
   kind of mechanism typically does *not* extend to `BACKLOG.md`-shaped files, only to specific
   filenames the harness itself recognizes): check the current directory first; if not found,
   check exactly **one** parent directory up and stop there. If your workspace nests sibling
   repos more than one level deep, extend this bound to match your actual layout — don't walk
   arbitrarily far by default.
3. **Read `BACKLOG.md`'s "Ready to implement" checklist section.** Note whether it's empty or has
   entries.
4. **Read every `Design Docs/*.md` file's `Kind:`/`Status:` line.** Collect every `Kind: work-item`
   doc whose status is `running` or `blocked: ...` — these are the in-flight items.

## Step 2: Signal check, in priority order — stop at the first one that fires

1. **A live, unclosed `handoff` primer exists** (Step 1.1 found and confirmed one) → resume from
   it directly; `handoff`'s own confirmation already handled this. Stop — none of the signals
   below apply once a primer is actively being resumed.
2. **No process history in this repo at all** (Step 1.2), but the repo has real existing code or a
   scope/spec document → this is the adopting-onto-an-existing-project case. Go to Step 3 below.
3. **`BACKLOG.md`'s "Ready to implement" checklist is non-empty** (Step 1.3) → offer
   `/implement-queue`.
4. **One or more in-flight work items exist** (Step 1.4) → offer to resume. **Plural, always** —
   follow `handoff` Step 0's own multi-candidate rule: list every one (design doc, its status
   line's blocker if any, a one-line summary), let the user pick, never silently take the most
   recent or the first alphabetically.
5. **None of the above** → fall through to `/backlog` List mode (invoke it, don't reimplement its
   listing).

## Step 3: Adopting onto an already-in-progress project

This is `spec`'s former Step 0.5, moved here — `spec` now leaves only a one-line pointer back to
this step. If there's no `Design Docs/`/`BACKLOG.md` history yet for this project, but the repo
already has an existing scope/spec document (an architecture doc, a feature spec) or substantial
existing code, do a scoping pass before anything else: reconcile the project's own
scope/spec/README (or a specific request, if one was already given) against the actual code —
what is already built (cited by file/section), what is genuinely remaining. **This scoping pass
stops at inventory** — what exists vs. what's missing, cited — it does not extend into weighing
implementation approaches, which stays gated behind `spec`'s own tier call. **Write the inventory
down as a durable artifact, not just a transcript message** — a real adoption session against an
existing project produced exactly this kind of inventory live and then lost it entirely when the
session ended with nothing written to disk. **Destination and format, so this isn't left to the
executing agent to invent each time**: write it to `Design Docs/<slug>-inventory.md` in this
project's own repo root (creating `Design Docs/` if it doesn't exist yet — this scoping pass is
what's introducing the process to the project, so the folder not existing yet is expected, not a
blocker). Mark it `Kind: deliverable` / `Status: done` — an inventory is a one-time snapshot, not
an ongoing item, and giving it `Kind: work-item` would wrongly make this skill's own Step 1.4 treat
it as perpetually in-flight on every future `/initiate` run. If the remaining scope splits into
multiple independently-designable areas, say so explicitly and ask (`AskUserQuestion`) which one to
run through `/spec` first — note every area *not* picked directly in this same inventory doc, as
remaining/not-yet-scoped, rather than creating separate stub docs for the deferred areas — never
bundle unrelated areas into one design doc just because they came up together.

## Step 4: Report

**Print the blocked-on-whom summary unconditionally, regardless of which signal fired.** This is
this command's one genuinely new output, and gating it behind a particular branch would hide it
exactly when several things are in flight and it matters most. Pull it straight from Step 1.4's
collected list: every `blocked: <what, on whom>` item, named plainly (design doc, what it's
waiting on). If nothing is blocked, say so in one line rather than omitting the section.

Then state which signal fired and which skill (if any) got invoked or offered — `handoff`,
`implement-queue`, `spec` (via Step 3's inventory), or `backlog` — and let that skill's own output
speak for the actual work. Don't re-summarize another skill's report; just hand off to it.

## Notes

- **Stateless, re-derived every invocation.** This skill reads state that other phases wrote
  (`handoff` primers, `BACKLOG.md`'s checklist, Design Docs' own `Kind:`/`Status:` lines); it
  persists none of its own. This is why a scenario dry-run for cross-session state logic doesn't
  apply here — that's reserved for `/ship`, which does carry real state via the archive gate.
- **Cross-reference, never duplicate.** If your setup has `commit`, `end-task`, and
  `wrap-up-session` skills that already restate the same git-survey prose, don't add a fourth copy
  here of anything those skills, `handoff`, `backlog`, or `implement-queue` already own. If a
  signal's handling needs more than the routing line above, that explanation belongs in the skill
  it routes to, not here.
- **A clearly-biggest-tier planning request has skipped straight to `EnterPlanMode` without
  invoking `spec` at all before now.** Because neither skill ran, `spec`'s own Step 1 model-check
  never fired either — exploration and the first several plan drafts ran on the wrong model, and
  the user had to notice and request a model switch manually, mid-session. The fix is cheaper than
  "remember to invoke a skill": before calling `EnterPlanMode` for anything shaped like a
  plan/design/roadmap/new-tool request, check in your head whether this project has any process
  history at all, even with no skill file in front of you — the same check Step 2 above makes
  explicit.
- **Local-model fit: not applicable.** Every signal in Step 2 is a deterministic check (file
  existence, a directory listing, a status-line grep) — exactly the kind of check that's
  preferable over a probabilistic guess, and there's no generation step here for a local SLM to
  plausibly take over.
