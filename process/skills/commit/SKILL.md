---
name: commit
description: Lightweight, narrow git-status-and-commit pass across every repo this session actually touched — the on-demand way to invoke your rules doc's standing commit trigger 3 right before clearing context, without the full /wrap-up-session survey (no docs-sync, no cheat-sheet refresh). Use when the user types /commit, or says something like "commit before I clear," "make sure everything's committed," or "quick commit check."
---

# Commit — narrow pre-clear commit check

This is the **lightweight companion to `/wrap-up-session`**, not a replacement for it. Use this right
before `/clear` to make sure this session's verified work is actually committed; use `/wrap-up-session`
at the actual end of a working day (or when the skill roster or documented behavior changed) for the
full docs-sync sweep. This skill does none of that — it exists specifically to be cheap enough to run
many times a day.

It implements exactly one thing: your rules doc's standing commit trigger 3 ("before ending a session or
wrapping up a chunk of substantive work, proactively run `git status` and commit any narrowly-staged,
verified changes"), as an explicit, on-demand action instead of something left to have happened silently.

## Step 1: Survey

**Once per repo actually touched this session** — recall from the conversation which repo(s) had any
work land in them this session (if your workspace spans more than one). Don't blindly check every repo
you know about if only one was touched. In each one, run `git status` (never `-uall`) and `git diff
--stat` to see the real on-disk picture. A parent repo's own `.gitignore` commonly excludes its nested
sub-repos outright, so a survey only at the parent root will never see changes in a sub-repo — the same
repo-scoping `wrap-up-session`'s own Step 1 uses, and for the same reason.

If another session may have touched a shared file (`CLAUDE.md`, `BACKLOG.md`, `MISTAKES.md`) concurrently — a very recent commit from elsewhere, or a file showing `MM` (staged + unstaged)
suggesting someone's mid-`git add -p` — flag it and don't stage that file until confirmed safe, per
your rules doc's multi-session guidance.

## Step 2: Commit pass

For each verified, complete change found — and anything else sitting modified that's genuinely
finished, not mid-edit — stage narrowly (`git add` specific files, never `-A`/`.`) and commit **in the
repo that file actually lives in**, with a message describing the change. Report the commit hash for
each one, labeled by repo, so there's a record without the user needing to ask.

If it's ambiguous whether something is actually finished versus still in-progress, ask rather than
guess — don't fold a half-done change into a commit just to clear the working tree. Mid-investigation,
uncommitted changes are fine to leave sitting; nothing here forces a commit before something is
actually done.

**Never push without explicit confirmation**, in any repo, regardless of this skill's standing local-commit authorization.

## Step 3: Report

Short and distinct from `wrap-up-session`'s full close-out summary — no doc-drift check, no
cheat-sheet-artifact status, no backlog-open-items listing. Just:

- Commit hash + one-line description, per repo, for anything actually committed.
- **An explicit call-out of anything deliberately left uncommitted, and why** (mid-investigation, not
  yet verified) — so a `/clear` immediately after this never silently loses track of in-progress state.
  Silence here would look identical to "nothing was left outstanding," which is exactly the ambiguity
  this skill exists to remove.

## Notes

- **Explicitly out of scope** (this is what keeps it cheap): no `CLAUDE.md`/`NOTES.md`/`MISTAKES.md`
  drift check, no cheat-sheet-artifact sync, no backlog-open-items listing. If any of
  those seem to actually need attention, say so and point at `/wrap-up-session` rather than doing a
  partial version of that work here.
- No hook automatically fires this on `/clear` — Claude Code's hook events (`SessionStart`/`SessionEnd`,
  `UserPromptSubmit`/`Stop`/`StopFailure`, `PreToolUse`/`PostToolUse`, `PermissionRequest`/
  `SubagentStop`) don't include a `/clear`-specific event, and whether `/clear` triggers `SessionEnd` is
  undocumented. This is manual-invocation only — `/commit` then `/clear` is the intended habit.
