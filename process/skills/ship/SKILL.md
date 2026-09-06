---
name: ship
description: Ship a finished work item — for anything with a deploy target, dispatch to the applicable publish-* skill to check locally, copy from source of truth to the deploy target, confirm before it's visible to others, and verify against the real deployed target afterward; then, for any work item (deploy target or not), archive its BACKLOG.md entry to BACKLOG_ARCHIVE.md and commit. Use when the user invokes /ship, says they're ready to ship/publish/push a finished change, or a design/backlog item is otherwise done and needs archiving.
---

# Ship: publish (if applicable) and close out

Generalizes the shape any tool-specific `publish-*` skills in your repo already share: check
locally against a real runtime, copy from the source of truth into the deploy target, confirm
before anything becomes visible to others, verify against the real deployed target afterward. This
skill **dispatches** to the applicable `publish-*` skill for the actual tool-specific work rather
than replacing it — a fifth deploy target just means writing a new `publish-*` skill first; this
skill picks it up automatically once Step 1's list includes it.

## Step 1: Does this work item have a deploy target?

- **Yes** — a `publish-*` skill already exists for this tool → invoke it now. That skill owns the
  actual publish mechanics end to end (local check, copy, confirm, verify live) — this skill's own
  job is what comes after, in Step 2.
- **No** — most work items (a skill, a doc, an unpublished tool) have nothing to publish → skip
  straight to Step 2. This is not a lesser or incomplete path; a one-shape loop with an absent
  optional stage beats teaching two different-shaped loops depending on the work item. **If `/ship`
  was invoked directly by the user on an item like this, say so plainly rather than silently
  no-op'ing**: there's no deploy step here, and Step 2's archive-and-commit is already owned by
  `backlog` or `implement-queue` for exactly this case (see Step 2 below) — point the user at
  whichever of those already covers this item instead of proceeding as if `/ship` itself does
  something further.

## Step 2: Archive and commit

**`/ship` owns this step for anything with a deploy target** (Step 1 fired "yes"), extending
`backlog/SKILL.md`'s existing debugger-only "resolved means published" rule to every tool with a
`publish-*` skill. For anything with no deploy target, `backlog` and `implement-queue` keep owning
this step themselves, exactly as they do today — each of the three skills states the split
explicitly rather than leaving it to be inferred. **The rest of this step only executes when Step 1
fired "yes"** — the no-deploy-target case stops at Step 1's own redirect and never reaches the
actions below.

Move the resolved `BACKLOG.md` entry (checklist line and tool-section entry, if either exists) to
`BACKLOG_ARCHIVE.md` verbatim — cut-and-paste, don't retype, terse close-out summary, per
`backlog`'s own existing convention. Then commit narrowly (standing local-commit authorization
covers this the same way it covers `backlog`'s own step), one commit, message drafted from the
entry.

**Ask about pushing, only if that commit landed in a repo with a remote configured.** Check via
`git remote -v` rather than assuming. Don't wait for the user to bring it up; ask right after
committing, once per repo.

**If this work item has a `Design Docs/<slug>.md` file, write `## Shipped — done` into it first**
(write-on-entry, per `spec/SKILL.md` Step 3.1) — the phase record `/initiate` Step 1.4 reads to
know the item is actually finished rather than still mid-flight. A plain `BACKLOG.md` item with no
design doc has nothing to write this into; skip it in that case.

## Notes

- **Next command, if your setup uses a next-command contract**: once Step 2's archive-and-commit
  lands, the recommendation is **`/end-task`** if this closes out the session's work, or
  **`/backlog`** as the named alternative to pick up the next open item in the same session.
- **Never a second publish mechanism.** This skill contains no tool-specific publish logic of its
  own — every actual "check locally / copy / confirm / verify live" step happens inside the
  dispatched `publish-*` skill.
- Local-model fit: not applicable — dispatch/orchestration over already-existing publish skills
  and a mechanical archive move, no generation step.
