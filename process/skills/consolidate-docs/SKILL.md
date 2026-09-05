---
name: consolidate-docs
description: Periodic maintenance pass that keeps CLAUDE.md lean — sweeps sections that have grown into dated, narrative bug-fix history and splits them into companion NOTES.md files, leaving only current-state facts and pointers behind. Use when CLAUDE.md feels like it's grown noticeably since the last pass, or the user asks to clean up/consolidate/trim the docs.
---

# Consolidate CLAUDE.md

`CLAUDE.md` is loaded in full on every session regardless of task, so its size is a fixed token cost every single time — unlike a tool's own `NOTES.md`, which only loads when someone's actually working on that tool. The goal isn't to lose information, it's to relocate it so it's paid for only when relevant.

## What to look for

A section is a consolidation candidate when it reads like a diary rather than a reference: dated bug-fix paragraphs ("Fixed 2026-08-XX: ..."), step-by-step verification blow-by-blow, or citation trails for a resolved investigation. It's *not* a candidate when it's a current-state fact, a standing behavioral rule, or a pointer — those are exactly what should stay.

## Steps

1. Read `CLAUDE.md` in full and identify sections that have grown past "what is this and where do I go for more" into full narrative history. This identification step is judgment, not transcription — do it in the main session.
2. For each candidate section belonging to a specific tool/folder, delegate the actual sweep to the **`docs-writer` subagent** (a cheap model is fine here) — announce the delegation explicitly ("Delegating to docs-writer to split the X section into X.NOTES.md") rather than running it inline. Give `docs-writer` the section(s) identified in step 1 and this instruction:
   - If a companion `<tool>.NOTES.md` (root-level tool) or `<folder>/NOTES.md` (per-folder tool) doesn't exist yet, create it, following the existing pattern (e.g. `some-tool.NOTES.md`, `some-folder/NOTES.md`).
   - Move the narrative content there verbatim (don't summarize away real citations/verification detail — the point is relocation, not deletion).
   - Leave behind in `CLAUDE.md`: a short current-state summary (what it is, current roster/status), and a pointer sentence to the NOTES.md file for the full history.
3. For candidate content that's a *procedure* (a repeatable "how to do X" workflow) rather than tool-specific history, check whether a skill already covers it before writing a new one — prefer extending an existing skill's Notes section over duplicating. If none exists and the procedure is genuinely repeated (not a one-off), propose a new skill to the user rather than just leaving the prose in `CLAUDE.md`. This judgment call stays in the main session, not `docs-writer`.
4. Re-read the trimmed `CLAUDE.md` end to end afterward to confirm every remaining pointer resolves to a real file/skill and nothing load-bearing got cut — this check also stays in the main session, since it's a judgment call about what matters, not transcription.
5. Commit the pass as its own commit (per `methodology.md` §6's commit trigger 2 — before/around a large rewrite) with a message describing which sections moved where.

## Notes

- This mirrors the `anthropic-skills:consolidate-memory` skill's purpose (merge/prune/re-tighten) applied to project docs instead of personal memory files.
- Don't run this reflexively every session — it's a periodic pass, triggered by noticeable growth, an explicit ask, or your rules-doc-size `PostToolUse` hook nudging past its threshold, not a per-turn habit.
- Delegating the sweep itself to `docs-writer` keeps this mechanical, high-volume relocation work off the more expensive main-session model — see `methodology.md`'s tiered-work section for the reasoning.
