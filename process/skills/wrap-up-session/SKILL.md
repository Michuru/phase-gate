---
name: wrap-up-session
description: Wrap up a working session across every repo touched this session — survey what changed, sync any docs that drifted (CLAUDE.md, BACKLOG.md, MISTAKES.md, tool NOTES.md), and commit verified narrow changes per-repo with reported hashes. Use whenever the user says something like "let's wrap up the session," "wrapping up," "let's call it," or otherwise signals they're closing out for now.
---

# Wrap up a session

This is a manual catch-all layered on top of the repo's existing standing auto-commit triggers (your rules doc's commit triggers, and `backlog`'s own archive-and-commit step). Most of the time it should find little left to do, because those triggers already fired mid-session — treat this as the safety net, not the primary mechanism.

**Repo-aware for any nested-repo layout** — a session's work this turn may span more than one repo (a parent repo plus one or more nested sub-repos, each their own git root, skills resolving upward from the parent). Every step below runs **once per repo actually touched this session**, not just in whichever directory the session happens to be rooted in — a parent repo's own `.gitignore` commonly excludes its nested sub-repos outright, so a `git status` run only at the parent root will never see changes in a sub-repo.

## Step 1: Survey what actually happened

Recall from the conversation what was built, fixed, or investigated this session — don't re-derive it from scratch, and note which repo each piece of work actually landed in (if more than one is in play). Then, **in each repo touched this session**, run `git status` (never `-uall`) and `git diff --stat` to see the real on-disk picture, including anything a standing trigger might have missed.

If another session may have touched shared files (`CLAUDE.md`, `BACKLOG.md`, `MISTAKES.md`) concurrently — a very recent commit from elsewhere, or a file showing `MM` (staged + unstaged) suggesting someone's mid-`git add -p` — flag it and don't stage that file until confirmed safe, per your rules doc's multi-session guidance.

## Step 2: Docs pass

For each doc type below, judge whether this session's work is actually reflected yet. This is a judgment call, not a mechanical sweep — skip anything that's already current.

- **`CLAUDE.md`** — new tool, new skill, new structural fact, or a changed behavior not yet documented? If your setup has more than one rules doc (a shared parent plus per-repo ones), update whichever one actually owns the content — cross-cutting process → the shared/parent doc; a specific repo's own structure/behavior → that repo's own file. Use `Edit`, never `Write`, on any of them. If a fix only needs a one-line pointer or fact update, do it directly; anything more substantial (a new NOTES.md section) gets delegated to the `docs-writer` subagent — announce the delegation explicitly.
- **Tool `NOTES.md`** — did this session add dated narrative history (a fix, an investigation, a verification) to a tool that has its own NOTES.md? If so and it's not written yet, delegate to `docs-writer`.
- **`BACKLOG.md` / `BACKLOG_ARCHIVE.md`** — any item resolved and verified this session that hasn't been archived yet? Normally `backlog`'s own step 7 already handles this; this is only a catch for anything that slipped through.
- **`MISTAKES.md`** — any process/methodology mistake surfaced this session (a false "verified" claim, a bad runtime assumption) not yet logged? Usually already logged same-turn per standing habit; this is a last-chance catch, not a re-investigation.
- **`CLAUDE.md` size** — if it's grown past your configured threshold (a `PostToolUse` hook will typically have already flagged this on any edit to that file), either run `/consolidate-docs` now or tell the user it's pending — don't silently ignore an already-fired nudge.

## Step 3: Commit pass

For each verified, complete change identified above — and anything else sitting modified that's genuinely finished, not mid-edit — stage narrowly (`git add` specific files, never `-A`/`.`) and commit **in the repo that file actually lives in**, with a message describing the change. **Report the commit hash for each one, labeled by repo** (short hash is fine) so the user has a record without needing to ask.

If it's ambiguous whether something is actually finished versus still in-progress, ask rather than guess — don't fold a half-done change into a commit just to clear the working tree.

**Never push without explicit confirmation, in any repo** — don't assume a repo has no remote configured just because another one in the same workspace doesn't; check each repo's own `git remote -v` rather than assuming.

## Step 4: Any cheat-sheet artifacts (conditional, only if you maintain one)

If you keep a command-reference artifact or a short daily-driver list summarizing available skills, and this session added, removed, or renamed a skill, or materially changed what an existing one does — update it now. This is the only place such artifacts get refreshed, since nothing else in this process checks them on its own.

If you don't maintain anything like this, skip this step entirely — it's a convenience for a specific workflow, not a required part of wrapping up.

## Step 5: Close-out summary

One message covering: commits made (hash + one-line description each, labeled by repo), which docs were touched and how, whether any cheat-sheet artifact was refreshed, and what's still open across `BACKLOG.md` (same "show what's open" convention as `backlog`'s own last step) — so the user can pick up next time without re-asking.
