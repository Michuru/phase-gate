---
name: backlog
description: Handle a BACKLOG.md request — either "add to the backlog" (quick, uninvestigated capture), "let's work on the backlog" (full investigation and fix), or a bare invocation (list open items to pick from). Use whenever the user asks to log, note, fix, or pick up a BACKLOG.md item, references "the backlog" at all, or types /backlog with no argument.
---

# Work a BACKLOG.md item

`BACKLOG.md` holds only open/actionable items; resolved history lives in `BACKLOG_ARCHIVE.md`. Three trigger shapes mean very different amounts of work — get the mode right before doing anything else.

## Step -1: Confirm the repo

**Before anything else, state plainly that this touches `BACKLOG.md`** (e.g. "Adding this to the backlog") and pause for the user to confirm or redirect. If your workspace nests multiple repos (a parent plus sub-repos, skills resolving upward), this skill only ever reads/writes the one `BACKLOG.md` that actually holds your process backlog — if the item is actually about a different, unrelated project entirely, tell the user to switch to a conversation rooted in that project's own repo instead of proceeding here. This check exists after a session once mixed a different project's content into this file before that project had a backlog of its own. (Skip this pause for the bare-invocation List mode below — reading and displaying the file needs no confirmation, only writing to it does.)

## Step 0: Determine the mode

- **`/backlog` typed with no argument** (no text after the command, and no item/phrasing given in the same message) → **List mode** (below). Read `BACKLOG.md` and show every open item across all sections so the user can pick one — don't guess add-vs-work when there's nothing to guess from yet, just surface the menu.
- **"Add to the backlog"** (with or without the `/` prefix) → Quick-capture mode (below). Do the minimum.
- **"Let's work on the backlog"**, or `/backlog <item or description>` (with or without a prior List-mode step) → Full-investigation mode (below).
- **Ambiguous phrasing** → use `AskUserQuestion` rather than guessing. Guessing wrong either wastes an investigation the user didn't want yet, or leaves a backlog note too thin to act on later.

## List mode (bare `/backlog`)

Read `BACKLOG.md` in full and print every open item, grouped by its existing section headings (don't re-sort or re-categorize). Keep each item to its existing one-line/short form — this is a menu, not a re-investigation, so don't start reading code or verifying claims yet. End by asking which item (if any) to pick up now; once the user answers, continue into Full-investigation mode for that item. If `BACKLOG.md` has no open items at all, say so plainly instead of printing an empty list.

## Quick-capture mode

Do nothing beyond writing the note. No root-cause investigation, no reading code, no new tool calls to verify the claim — the user is typically offloading this *because* they're low on session budget, and an unrequested investigation burns the tokens needed to even finish writing it down.

Write down: what the user said, plus any concrete facts already sitting in the current conversation's context (nothing you'd need a new tool call to find). Caveat clearly as unconfirmed. Append to the relevant section of `BACKLOG.md` (create a new section if the tool/topic doesn't have one yet).

## Full-investigation mode

The normal full effort:

1. Investigate root cause — read the relevant code/data, don't assume.
2. Verify against a real source: a real log, real calculator/tool output, a source document (including scanned PDFs), or whatever ground truth applies to this item.
3. Fix the code.
4. Re-verify the fix the same way.
5. **QA gate (conditional)** — if this item is Tier 1/2 per your rules doc's tiered-work section (it shouldn't usually be, if `design-gate` was used upstream for those), or if the fix touches a flagged surface (see your `flagged_surfaces` list — `methodology.md` §5), invoke the `code-reviewer` subagent before archiving — announce it explicitly ("Delegating to code-reviewer to verify..."), don't fold it silently into the rest of the session. Otherwise skip this step; most `BACKLOG.md` items are plain Tier 3 and don't need it.
6. **Docs sync** — if the fix changes anything your rules doc documents (a behavior, a threshold, an architecture note), delegate the write to the `docs-writer` subagent (a cheap model is fine here) rather than doing it inline — announce the delegation explicitly. This is a hard requirement, not optional cleanup.
7. Move the resolved entry from `BACKLOG.md` to `BACKLOG_ARCHIVE.md` verbatim (cut-and-paste the section, don't retype). **Default to terse when writing the close-out summary** — one or two sentences: what was found, what was done, what confirmed it. Skip the play-by-play (every intermediate step tried, every ruled-out theory) unless it's genuinely non-obvious and worth preserving for a future session — the same bar your rules doc uses for code comments (would a reader be confused without it?). A full paragraph reconstruction is the exception, not the default; a citation/file-path pointer to where the real detail already lives (a design doc, the code diff, git log) beats retyping that detail into the archive. This applies to how the entry is written *while still in `BACKLOG.md`*, too — archive it promptly once resolved rather than letting related sub-findings accumulate under one still-open-looking bullet across sessions.
8. **Commit automatically, without asking** (standing authorization for local commits — pushing anywhere still needs explicit confirmation every time, see `methodology.md` §6): one commit per resolved item, message drafted from the `BACKLOG.md` entry. Small drive-by fixes riding along in the same entry ride along in the same commit. Stage narrowly (`git add` specific files, never `-A`/`.`) in case another session has unrelated changes sitting uncommitted.
9. **Display what's still open** — after wrapping up, show the remaining open items across *all* sections of `BACKLOG.md`, not just the one just worked, so the user can pick the next one without asking. Do this every time, automatically.

## Notes

- If another session may have touched `BACKLOG.md`/`CLAUDE.md`/`MISTAKES.md` since this session started (e.g. a very recent commit from elsewhere), re-read the file immediately before editing rather than trusting what was loaded at session start — `Edit`'s exact-string match fails safely on drift, `Write`'s full-file replacement doesn't.
- For a tool with its own publish/release/deploy step, "resolved" also means that step actually happened — not just that the fix works locally — before archiving.
