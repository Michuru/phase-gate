---
name: end-task
description: Parent-level session-close router — surveys session state once, detects unfinished work first, then routes to /handoff (a fresh-session primer) or a wrap-up at narrow-commit or full-sync depth, always naming /handoff as the alternative in every row. Absorbs /commit and /wrap-up-session as internal depth modes. Use when the user types /end-task, or says something like "what do I need to do before I clear," "am I clean to clear," or "end the task."
---

# End-task: the parent-level close router

Mirrors `initiate`'s own structure, if you have that skill installed, as the session's close-out
counterpart — survey → detect → route → report. If you also have `initiate` installed, the two bind
the same "next-command contract" as the parent-level ranker/router pair — one screen, collapse what
can't be acted on, and — the rule this command exists to enforce — **surface the fork to `/handoff`,
never silently pick it.** Absorbs `/commit` and `/wrap-up-session` as internal depth modes — one
implementation of the shared git-survey logic instead of three cross-referencing copies.

**Manual invocation only** — Claude Code has no `/clear`-specific hook event, so nothing fires this
automatically. `/end-task` then `/clear` is the intended habit.

## Step 1: Survey

**Once per repo actually touched this session** — recall from the conversation which repo(s) had any
work land in them this session (if your workspace spans more than one, e.g. a parent repo plus
nested sub-repos, each their own git root, skills resolving upward from the parent). Don't blindly
enumerate a fixed repo list — recall-based scoping naturally covers whatever was actually touched,
including a deploy repo, without needing a special case for any one of them. In each one, run `git
status` (never `-uall`) and `git diff --stat` to see the real on-disk picture. A parent repo's own
`.gitignore` commonly excludes its nested sub-repos outright, so a survey only at the parent root
will never see changes in a sub-repo.

If a shared file (your rules doc, `BACKLOG.md`, `MISTAKES.md`) shows `MM` (staged + unstaged) or
looks like another session may be mid-edit, flag it per your rules doc's multi-session guidance
rather than folding it into this survey's verdict.

## Step 2: Detect "Work unfinished" — checked first, before anything else

Any of the following, true → **Work unfinished** fires, and nothing below this step runs:

- A `Design Docs/*.md` file with `Kind: work-item` and `Status: running` was edited this session.
- An open Plan Mode plan exists with no matching saved `Design Docs/<slug>.md` file yet.
- A `Kind: work-item` doc was edited this session with no `## QA gate` record written yet.

This is a concrete, checkable signal, not "whatever this skill currently improvises from `git status`
plus conversational impression" — deriving "is this actually finished" from impression alone is
exactly the gap that lets a WIP session get committed as though done. **Checked before the
docs-drift/dirty checks below, on purpose** — a session mid-design or mid-implementation should never
be routed toward "commit and clear," even if the working tree happens to be clean at this exact
moment (a design doc saved but not yet built, for instance).

## Step 3: If nothing unfinished, run the docs-sync signal check

Five yes/no questions:

1. **Your rules doc** (any repo) — new tool/skill/structural fact/changed behavior from this session
   not yet documented?
2. **Tool `NOTES.md`** — dated narrative history (a fix, an investigation, a verification) from this
   session not yet written?
3. **`BACKLOG.md`/`BACKLOG_ARCHIVE.md`** — an item resolved this session but not yet archived?
4. **`MISTAKES.md`** — a process/methodology mistake surfaced this session, not yet logged?
5. **A cheat-sheet artifact** (a command-reference doc or short daily-driver list, if you maintain
   one) — was a skill added, removed, renamed, or materially changed this session, **and that change
   isn't reflected there yet**? (Check the file directly rather than assuming — a session that
   already did its own sync as part of the same work answers "no" here. Skip entirely if you don't
   maintain anything like this.)

Answer each concretely, not by vague impression — e.g. #3 is answerable by checking whether a
`BACKLOG.md` item discussed this session still has an open checkbox; #1/#2 are answerable by
checking whether something that came up this session is already recorded, rather than assuming "new"
without checking.

**Tie-break, when unsure whether a question is really a "yes": take the deeper mode.** It's a
superset of the narrow mode, so the wrong answer is cheap in exactly one direction.

## Step 4: Route and report

| Detected state | Recommendation | Named alternative |
|---|---|---|
| Work unfinished (Step 2) | **`/handoff`** — write a primer so a fresh session continues | wrap up anyway, if you're actually done despite the signal |
| Any "yes" in Step 3 | **Wrap up at full-sync depth** (Step 6 below) | **`/handoff`**, if you're actually still mid-task |
| Dirty repo(s), no "yes" in Step 3 | **Wrap up at narrow-commit depth** (Step 5 below) | **`/handoff`**, if you're actually still mid-task |
| No dirty repos, no "yes" in Step 3 | `Clean — nothing pending. Clear to /clear.` | **`/handoff`**, if you're actually still mid-task |

`/handoff` appears in **every** row — that's what makes it discoverable to someone who doesn't know
it exists. State which row fired and why (the concrete signal, not just the verdict) before doing the
row's own work — the routing decision should be visible, not a silent side effect.

## Step 5: Narrow-commit depth (absorbs former `/commit`)

For each verified, complete change found in Step 1's survey — and anything else sitting modified
that's genuinely finished, not mid-edit — stage narrowly (`git add` specific files, never `-A`/`.`)
and commit **in the repo that file actually lives in**, with a message describing the change.

If it's ambiguous whether something is actually finished versus still in-progress, ask rather than
guess — don't fold a half-done change into a commit just to clear the working tree. Mid-investigation,
uncommitted changes are fine to leave sitting; nothing here forces a commit before something is
actually done.

**Ask about pushing, once per repo with a remote configured — this is the only point in the whole
session that asks, not a separate ask after every commit-producing skill.** Check each repo's own
`git remote -v` rather than assuming from another repo in the same workspace. Covering *every*
commit made in that repo this session (this depth's own commits, plus anything `ship`/`backlog`
already committed earlier without asking), proactively ask whether to push now, rather than sitting
passively until the user brings it up. Still needs an explicit yes before pushing — this only
changes who raises the question first, and consolidates it to one ask instead of several.

**Report**: commit hash + one-line description, per repo, for anything actually committed, plus an
explicit call-out of anything deliberately left uncommitted and why (mid-investigation, not yet
verified) — silence here would look identical to "nothing was left outstanding," which is exactly
the ambiguity this depth mode exists to remove.

## Step 6: Full-sync depth (absorbs former `/wrap-up-session`)

**Docs pass** — for each doc type below, judge whether this session's work is actually reflected
yet; this is a judgment call, not a mechanical sweep — skip anything already current:

- **Your rules doc** — new tool, new skill, new structural fact, or a changed behavior not yet
  documented? If your setup has more than one (a shared parent plus per-repo ones), update whichever
  one actually owns the content (cross-cutting process → the shared/parent doc; a specific repo's own
  structure/behavior → that repo's own file). Use `Edit`, never `Write`, on any of them. A one-line
  pointer/fact fix goes directly; anything more substantial (a new NOTES.md section) delegates to the
  `docs-writer` subagent — announce the delegation explicitly.
- **Tool `NOTES.md`** — did this session add dated narrative history (a fix, an investigation, a
  verification) to a tool that has its own `NOTES.md`? If so and it's not written yet, delegate to
  `docs-writer`.
- **`BACKLOG.md` / `BACKLOG_ARCHIVE.md`** — any item resolved and verified this session that hasn't
  been archived yet? Normally `backlog`'s own step 7 already handles this; this is only a catch for
  anything that slipped through.
- **`MISTAKES.md`** — any process/methodology mistake surfaced this session, not yet logged?
  Usually already logged same-turn per standing habit; this is a last-chance catch, not a
  re-investigation.
- **Rules-doc size** — if any repo's file has grown noticeably large (a `PostToolUse` hook, if
  configured, will typically have already flagged this on any edit to that file), either run
  `/consolidate-docs` now or tell the user it's pending — don't silently ignore an already-fired
  nudge.

**Commit pass** — same mechanics as Step 5's narrow-commit depth, for every verified complete
change identified in the docs pass above plus anything Step 1's survey found; same
ask-about-pushing-per-remote-repo rule.

**Cheat-sheet artifact sync (conditional, only if you maintain one)** — needed only if this session
added, removed, or renamed a skill, or materially changed what an existing one does (not a wording
tweak). Update it directly and, if it's a published artifact, republish it to its **existing** URL
(never create a new one for this). Skip entirely if you don't maintain anything like this, or if the
roster didn't change this session.

**Close-out summary** — one message covering: commits made (hash + one-line description each,
labeled by repo), which docs were touched and how, whether any cheat-sheet artifact was refreshed,
and what's still open across `BACKLOG.md` — so the user can pick up next time without re-asking.

## Notes

- **`/handoff` in every row is the point of this design.** If your setup has a `Stop` hook that
  nudges toward `/handoff` at high context-fill, that's real but only above its own threshold — a
  session that reaches `/end-task` with unfinished work below that threshold previously had no route
  to `/handoff` at all; this table closes that gap without touching the hook.
- **`/commit` and `/wrap-up-session` are retained as 5-line redirect stubs for one cycle**, not
  deleted outright — enough live references may still say "run `/commit`"/"run `/wrap-up-session`"
  that a missing skill would fail harder than a stub pointing here.
- **Explicitly out of scope**: this skill doesn't change `handoff`'s own mechanics — it only routes
  to it.
- Not a candidate for a scenario dry-run under a cross-session-state rule — every invocation
  re-derives its verdict from live `git status`, Design Docs' own `Kind:`/`Status:` lines, and that
  session's own conversational recall; nothing here persists state across invocations. That kind of
  requirement is better reserved for skills like `handoff` (a CONSUMED-marker mechanism) or
  `implement-queue` (worktree bookkeeping) that do carry real cross-session state.
- **Local-model fit: not applicable.** Steps 2-3's checks are deterministic reads; the docs pass and
  close-out summary are open-ended judgment about what changed and why — not a good fit for a small
  local model.
