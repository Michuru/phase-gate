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

Eight yes/no questions:

1. **Your rules doc** (any repo) — new tool/skill/structural fact/changed behavior from this session
   not yet documented?
2. **Tool `NOTES.md`** — did this session change an ongoing architecture fact, live caveat, or
   schema a future session needs to know, not yet recorded there? **Not** a dated fix/investigation
   narrative — if your rules doc draws a distinction between "current-state fact" (belongs in
   `NOTES.md`) and "dated history of a specific fix" (belongs in `BACKLOG_ARCHIVE.md`/the commit
   message), follow it — writing narrative into `NOTES.md` here is exactly what recreates the
   duplication that distinction exists to prevent.
3. **`BACKLOG.md`/`BACKLOG_ARCHIVE.md`** — an item resolved this session but not yet archived?
4. **`MISTAKES.md`** — a process/methodology mistake surfaced this session, not yet logged?
5. **A cheat-sheet artifact** (a command-reference doc or short daily-driver list, if you maintain
   one) — was a skill added, removed, renamed, or materially changed this session, **and that change
   isn't reflected there yet**? (Check the file directly rather than assuming — a session that
   already did its own sync as part of the same work answers "no" here. Skip entirely if you don't
   maintain anything like this.)
6. **A downstream export of your own — uncommon; skip this and question 7 entirely unless you
   actually maintain one** (a generalized copy of your own customized skills/hooks/config that you
   periodically publish or copy into a separate project, the way this methodology itself gets
   published from wherever you actually customize it). If you do maintain one, and this session
   added a wholly new skill, agent, or hook (not merely edited one already in your export), has
   whether to port it there actually been decided — a real yes/no recorded somewhere (this session's
   own response, a `BACKLOG.md` entry, a design doc) — rather than never coming up at all? Not-yet-
   decided is a "yes" here. This is deliberately distinct from question 7 below: a brand-new
   component has no existing record for a drift check to compare against, so a drift check alone can
   never catch it.
7. **Drift on an already-exported component** (same "uncommon — skip if it doesn't apply" scope as
   question 6). Did this session **edit** (not add) any skill/agent/hook file your own export already
   tracks as a ported component? If so, has whatever mechanism you use to re-check for drift (a
   script, or just a side-by-side diff) actually been run and come back clean since? Not-yet-checked
   is a "yes" here.
8. **File-size thresholds — mechanical, not a judgment call, unlike questions 1-7 above.** If you
   have a hook (or just a habit) that flags your rules doc, mistakes log, or a `NOTES.md`/
   `*.NOTES.md` file once it grows past some size, is any such file touched this session now sitting
   past that threshold? Check the actual file size directly — past-threshold is an automatic "yes,"
   no interpretation needed. Skip this question if you don't track file size at all.

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

**If a repo you maintain publishes versioned releases (a `CHANGELOG.md` plus git tags, or similar)
and this session just pushed to it, also check whether a release should be cut** — a real gap worth
naming: nothing forces this question to get asked on its own, so real fixes can sit merged with an
"Unreleased" section sitting non-empty and no tag ever cut, indefinitely, until someone happens to
notice and ask directly. Check that file's unreleased section: if it has real content after this
push, ask whether to cut a release now or hold off. Not every push needs a release — this is a
judgment call the user makes, not an automatic trigger — but the question itself should never go
unasked. Skip entirely if you don't publish versioned releases from any repo touched this session.

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
- **Tool `NOTES.md`** — did this session change an ongoing architecture fact, live caveat, or schema
  for a tool that has its own `NOTES.md`, not yet recorded there? If so, delegate to `docs-writer`.
  **Not** dated fix/investigation narrative — that belongs in `BACKLOG_ARCHIVE.md`/the commit
  message, if your rules doc draws that same distinction (see question 2 above).
- **`BACKLOG.md` / `BACKLOG_ARCHIVE.md`** — any item resolved and verified this session that hasn't
  been archived yet? Normally `backlog`'s own still-open display step already handles this; this is
  only a catch for anything that slipped through.
- **`MISTAKES.md`** — any process/methodology mistake surfaced this session, not yet logged?
  Usually already logged same-turn per standing habit; this is a last-chance catch, not a
  re-investigation.
- **Rules-doc size** — if any repo's file has grown noticeably large (a `PostToolUse` hook, if
  configured, will typically have already flagged this on any edit to that file), either run
  `/consolidate-docs` now or tell the user it's pending — don't silently ignore an already-fired
  nudge.
- **`MISTAKES.md` / `NOTES.md` size** — same check, same "don't silently ignore an already-fired
  nudge" rule (if you have one), for the mistakes log and any tool's `NOTES.md`/`*.NOTES.md` file
  past its own threshold — run `/consolidate-docs`'s pruning mode for that file if it covers this
  doc type, prune it directly, or tell the user it's pending.

**Commit pass** — same mechanics as Step 5's narrow-commit depth, for every verified complete
change identified in the docs pass above plus anything Step 1's survey found; same
ask-about-pushing-per-remote-repo rule.

**Cheat-sheet artifact sync (conditional, only if you maintain one)** — needed only if this session
added, removed, or renamed a skill, or materially changed what an existing one does (not a wording
tweak). Update it directly and, if it's a published artifact, republish it to its **existing** URL
(never create a new one for this). Skip entirely if you don't maintain anything like this, or if the
roster didn't change this session.

**Downstream-export drift check (conditional)** — triggered by Step 3's question 7, and only
relevant if you maintain a downstream export as described there (uncommon — most adopters don't). If
this session edited a skill/agent/hook file your export already tracks as a ported component, run
whatever drift-check mechanism you use for it and re-generalize whatever it flags (patch the
exported file, update your own tracking record, re-run to confirm clean). Skip entirely if you don't
maintain such an export, or if none of its tracked files were touched this session.

**Downstream-export new-component consideration (conditional)** — only if Step 3's question 6 came
back "yes": surface it explicitly rather than letting the session end without ever raising it. Ask
the user whether the new skill/agent/hook should be ported now (if so, do it — generalize it, add it
to your export's own tracking, confirm it's clean) or explicitly declined (say so plainly, and note
the decision somewhere findable — a one-line `BACKLOG.md`/design-doc note is enough) so a future
session doesn't have to re-ask the same question with no record of the answer.

**Close-out summary** — one message covering: commits made (hash + one-line description each,
labeled by repo), which docs were touched and how, whether any cheat-sheet artifact was refreshed,
and what's still open across `BACKLOG.md` — so the user can pick up next time without re-asking.
**Presentation for the still-open part, same convention as `backlog`'s own still-open display step
(if you have that skill installed)**: a short numbered list, one line per item, with any item
resolved this session shown struck through (`~~text~~`) in place rather than dropped — don't
re-expand full investigation detail for any item here.

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
