---
name: handoff
description: Write a self-contained briefing so a fresh context window (a new session, or this one after a checkpoint) can continue the current in-progress task with zero shared history — or, invoked at the start of that fresh session, pick the briefing back up. Use when the user asks for a handoff, a prompt to paste into a new window, wants to resume/continue a prior handoff, or explicitly invokes /handoff - or when accepting this skill's own automatic context-usage nudge.
---

# Handoff: brief a fresh context window

This skill is **not** `end-task` (that's session closeout: commit + docs-sync + done, if you have that
skill installed) and not the harness's own automatic compaction. It's for continuing the *same*
in-progress task under a fresh budget, not ending it.

## Step 0: Determine direction — outgoing (write a primer) or incoming (resume from one)

This skill runs under the same `/handoff` command both ways; use context to tell which:

- **Explicit argument** (`/handoff resume`, `/handoff continue`) → incoming, skip to the incoming path below.
- **Bare `/handoff`, but this session already has substantial prior conversation** (you've been working on something across multiple turns) → outgoing. Proceed to Step 1.
- **Bare `/handoff`, and this is at or near the start of a fresh session** → likely incoming. **Discover every live primer before doing anything else, by running all three of these checks, in any order:**
  1. **This repo's own `.claude/handoffs/*.md`, always — never gated on whether it's part of a larger nested workspace.** This is the single most common case (a fresh session in an otherwise-standalone repo checking for its own live primer), so it must never be skipped just because check 2 doesn't apply.
  2. **Sibling repos nested under a common parent, discovered dynamically — never a fixed, hardcoded list, and only if this repo actually sits inside such a nested workspace:** glob `*/.claude/handoffs/*.md` from that parent root. This naturally covers every sibling repo the moment its own `.claude/handoffs/` directory exists, with no name list to keep in sync — a hardcoded repo list is exactly what lets a newly-added repo go unchecked for days.
  3. **External repos — repos that live physically outside your nested workspace tree, so check 2's glob structurally cannot reach them, but still carry their own `.claude/handoffs/` mechanism because they were seeded from the same source** (e.g. a project exported or ported elsewhere from this one). Unlike check 2, this list can only ever be maintained by hand — there is no parent directory to glob from, so a repo has to be added here explicitly the first time it's found carrying a live primer checks 1-2 missed. Maintain a short, explicit list of such repos here as you discover the need, and run the same top-level `.claude/handoffs/*.md` check against each.

  **Use forward slashes in every glob pattern above, always** — on Windows, a backslash pattern can be silently treated as an escape sequence and match nothing at all, with no error, which reads indistinguishably from "no live handoffs exist" (confirmed the hard way). Pass the search root as its own parameter rather than embedding backslashes in the pattern, if your tooling supports that. **Not just the current repo by cwd** — a fresh session's cwd is often the workspace root, but the actually-relevant in-progress WIP frequently lives in a sibling repo (confirmed the hard way). **List only the top-level `.md` files in each `.claude/handoffs/` directory — never its `archive/` subfolder, and never open a file just to check for a marker.** A consumed primer is moved into `archive/` at the moment it's consumed (see "Consuming a primer" under Step 6) — so anything still sitting at the top level is live by construction, a plain directory listing rather than a per-file content check. This is a deterministic count: **exactly one live file** → that's the candidate, proceed below. **More than one live file** → that is itself the ambiguity signal, regardless of how close or far apart their mtimes are (a stale, orphaned primer from an interrupted session can sit for hours or days before anyone runs `/handoff` again — elapsed time says nothing about whether it's still live) — **run the closed-thread check (below) on every candidate before presenting the list, not just on whichever one the user eventually picks.** Deferring the check to "whichever one gets picked" leaves every candidate that *isn't* picked unchecked — that's exactly the gap that let two stale primers go undetected in the same multi-candidate scan in practice. Then list all of them (filename, repo, date, one-line summary of each, **and, for any the check found closed, say so directly in that line** — e.g. "(looks closed — see below)" — rather than presenting it as equally live and hoping the user catches it from memory) and let the user pick, rather than silently taking the most recent by mtime. **Zero live files** → say so plainly and ask what the user wants to do instead, per the no-file case below.

**The closed-thread check itself** (run once per candidate, whether there's one or several): read the primer, then **cheaply check whether its own thread is already closed** before presenting it as authoritative. Two things to check, both targeted reads/greps of what the primer already points at — never a fresh investigation:
1. The primer names a source of truth (a `BACKLOG.md` entry, a design doc) — read just that, and look for an explicit completion marker (Done/Closed/Archived, a Status section saying so, or a `BACKLOG.md` entry that's moved to `BACKLOG_ARCHIVE.md` entirely).
2. **Also check the primer's own named repo/files for the work having shipped without the primer ever being resumed** — a targeted `git log --oneline` (optionally `--since=<primer's own date>`) on the repo/directory the primer names, scanning for a commit message that plausibly completes the exact feature/task the primer describes. Absence of a Status field or a `BACKLOG_ARCHIVE.md` entry is **not** proof the thread is still open — it may just mean nobody wrote a completion marker even though the work shipped by a different path than resuming this primer.

Once a single live candidate is identified (directly, or by the user's pick from a multi-file list) and its check has run, confirm with the user before treating it as authoritative — state its filename, its repo, its date, a one-line summary of what it's continuing, **and, if either check above found evidence of closure, say so plainly instead of presenting it as routinely resumable** (e.g. "this primer's thread looks closed per `BACKLOG.md`/git log — its item is now archived/shipped; want me to mark it CONSUMED and pick something else, or is there a real tail left?"). Ask whether to pick it up from there. If confirmed live, act on the primer directly (read whatever it points at — design doc, `BACKLOG.md` entry, file/line — and continue the work, `cd`-ing into that primer's own repo first if it differs from the current cwd); the primer itself is the full briefing, nothing further from this skill is needed. If confirmed closed, **consume it now** (see "Consuming a primer" under Step 6) and ask what to work on instead. If no live handoff file exists anywhere, say so plainly and ask what the user wants to do instead — never force a resume that isn't there.

**Track whether this session's own work started from an incoming resume** — note the file path if so. It matters for Step 6 below.
- **Genuinely ambiguous either way** → ask the user directly rather than guessing.

The rest of this document (Steps 1-8) covers the outgoing direction only.

## Step 1: Confirm the trigger

Either the user asked for a handoff directly (a manual request, `/handoff`, "give me a prompt for a new
window"), or this is a response to an automatic context-usage nudge, if you have one wired up (see the
`context-usage-nudge` standalone component). Either way, proceed to Step 2 — the process is identical
regardless of which triggered it.

## Step 2: Check whether compaction has already happened this session

**Do this first, before assembling anything.** If the harness has already compacted this session's
context, say so plainly to the user, and note in the primer itself that it was assembled from a
post-compaction summary, not the original reasoning — the early decisions the primer most needs may
already be gone. A primer that silently launders a summary into "here's what we decided" is worse than no
primer at all.

## Step 3: Assemble the primer from the current conversation directly

Write the briefing from what's actually in this conversation's own context — goal, key decisions already
made, the exact design-doc/`BACKLOG.md` entry to point the fresh session at, remaining go-ahead points
still open, and any caution flags (e.g. worktree-vs-main-checkout, a peer session touching the same file).

**Do not re-explore the repo to reconstruct any of this** — re-deriving facts already sitting in context
defeats the point of a cheap checkpoint.

**Keep the primer itself lean.** A fresh session already starts at a nontrivial fixed token floor
(system prompt, all core tool schemas, your rules doc, memory, skills catalogue) before the primer is even
read — a bloated primer stacks directly on top of that and undoes the point of a cheap restart. Prefer
pointers over pasted content: a design-doc section name, a `BACKLOG.md` entry, a file path with line
range, a commit hash — not the text those things already contain. Only paste content that exists nowhere
else on disk (a decision made purely in conversation, with no written record). If a primer is running
long, that's a sign to point harder, not explain harder.

**Also run `git status --short` in every repo touched this session** — not just the one the trigger fired
in, if your workspace spans more than one. Fold the raw per-repo output into the primer as-is. This is
deliberately narrow, matching the pattern of an equivalent `SessionEnd` hook's warn-only posture, if you
have one: **report only — never stage or commit anything, and never judge whether something should be
committed.** This exists only so the fresh session isn't surprised by uncommitted state it has no way to
otherwise discover, since Step 3's own rule tells it not to re-explore the repo.

## Step 4: Determine the output path

`<repo-root>/.claude/handoffs/<YYYY-MM-DD>-<slug>.md`, where `<repo-root>` is whichever repo the work is
actually happening in — by the session's own cwd, never hardcoded to any one repo. Pick `<slug>` from the
task at hand (short, kebab-case).

**This directory holds user-facing primers only** — never hook state or other machine-internal files.

## Step 5: Write the file

Write the assembled primer to the path from Step 4.

## Step 6: Hand off explicitly

**If this session's own work began from an incoming resume** (tracked in Step 0 above), consume that
source primer now, before anything else in this step (see "Consuming a primer" below), noting it was
superseded by `<new primer path>`. If this session did *not* start from a resume, there's nothing to mark
— a brand-new thread's primer has no predecessor.

Tell the user the primer's full path and a one-line summary of what it continues — that's it. Don't print
the primer's full contents in the chat. This relies on Step 0's incoming-path auto-detection (a fresh
session, invoked bare, discovers every repo's `.claude/handoffs/` on its own and confirms the most recent
one with the user before acting on it) rather than a manual copy-paste — the file is the handoff, not the
chat message.

### Consuming a primer

Used both by Step 0's closed-thread case and this step's supersession case — whenever a primer's thread is
done, whether superseded by a new primer or found already closed:

1. Prepend a `> **CONSUMED <today's date> — <reason>.**` line at the top of the file — `superseded by
   \`<new primer path>\`` or `thread closed, see <source>` as the reason. This keeps a human-readable
   record of why/when/what closed it, for anyone who opens the archive later.
2. Move the file from `.claude/handoffs/<name>.md` to `.claude/handoffs/archive/<name>.md` in that same
   repo (create `archive/` if it doesn't exist yet) — **as its own separate move-and-commit, not folded
   into a later multi-file commit.** A move run in the same breath as a preceding edit can stage the
   *pre-edit* content, so the marker never actually lands in the commit, with no error anywhere in the
   chain (confirmed the hard way). Before treating this as done, re-read the moved file (or check the
   commit itself) and confirm the `CONSUMED` marker is actually present in what got committed — don't just
   trust that the edit and the move both reporting success means the content carried through.

**Both steps matter — the marker alone isn't enough.** Step 0's live-candidate scan is a plain directory
listing of each `.claude/handoffs/` top level (see Step 0) with no per-file marker check, specifically so
the scan stays cheap as the number of primers grows — a consumed file left sitting at the top level would
be silently miscounted as live under this scheme. Moving it into `archive/` is what actually removes it
from the candidate pool; the marker is just the historical record once it's there.

## Step 7: Give this a real backup path if your setup needs one

If your setup has a mechanism that only captures *committed* history for backup or sync purposes (e.g. a
`SessionEnd` hook bundling changes to an external backup tool), a brand-new primer — or the design
doc/notes/`BACKLOG.md` edit it points at — has zero coverage under it until some later, unrelated commit
happens to include it, which could be a long time if the handed-off work spans several more handoffs
before it's ever "finished." If that applies to you, immediately after writing the primer, stage and
commit narrowly: the primer file itself, plus whatever specific file(s) it points at that are also
uncommitted (a design doc, notes, a `BACKLOG.md` edit) — never `git add -A`/`.`. If the primer and the
file(s) it points at live in different repos, commit narrowly in each repo separately. If your setup has
no such mechanism, this step is optional — its whole purpose is closing a backup-coverage gap that may
not exist for you.

Use a distinct commit message convention from `end-task`'s "this is actually finished" tone —
lead with `WIP checkpoint:` and state plainly what's not finished, e.g.:

```
WIP checkpoint: <short description of the in-progress task>

Not finished — <what's still open>. Committing now purely so this WIP has
backup coverage before the session hands off to a fresh context — see the
accompanying handoff primer for the actual continuation state.
```

This is a standing exception scoped to this skill, not a general auto-commit rule — it exists only to
close the backup gap for genuinely half-done work, never to imply the work is ready to archive or is
otherwise "done."

## Step 8: Confirm and stop

Confirm the handoff is written (and committed, if Step 7 applied), and don't chain into anything else (no
docs-sync, no archive move, no cheat-sheet refresh) — those belong to `end-task`'s full-sync depth mode,
not this skill.

**State plainly, in that same confirmation, that it's safe to `/clear` now** — don't make the user
ask separately (confirmed the hard way: a user had to ask "am I ok to clear?" right after a handoff
had already finished, when the confirmation should have said so up front). One line is enough, e.g.
"Handoff written (and committed) — safe to `/clear` whenever you're ready."

**Next command, per the next-command contract, if your setup uses one**: the recommendation is
**`/clear`** — the primer is written and committed specifically so the session can end here; named
alternative is continuing in this same session if there's more to do before actually clearing.
