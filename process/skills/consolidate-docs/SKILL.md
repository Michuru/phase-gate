---
name: consolidate-docs
description: Periodic maintenance pass that keeps CLAUDE.md lean — sweeps sections that have grown into dated, narrative bug-fix history and splits them into companion NOTES.md files (leaving only a terse current-state sentence and a pointer behind), plus a separate staleness pass that deletes rules no longer true rather than just relocating them. Use when CLAUDE.md feels like it's grown noticeably since the last pass, or the user asks to clean up/consolidate/trim the docs.
---

# Consolidate CLAUDE.md

`CLAUDE.md` is loaded in full on every session regardless of task, so its size is a fixed token cost every single time — unlike a tool's own `NOTES.md`, which only loads when someone's actually working on that tool. The goal isn't to lose information, it's to relocate it so it's paid for only when relevant.

## What to look for

Two distinct problems, checked separately — don't conflate them:

**Narrative bloat** — a section reads like a diary rather than a reference: dated bug-fix paragraphs ("Fixed 2026-08-XX: ..."), step-by-step verification blow-by-blow, or citation trails for a resolved investigation. It's *not* a candidate when it's a current-state fact, a standing behavioral rule, or a pointer — those are exactly what should stay. But even a legitimate standing rule is usually over-long: most existing entries are a full paragraph (3-5 sentences of *why*/*how it was found*/*the incident*) followed by a `Full incident: X.NOTES.md` pointer — and that paragraph typically just re-narrates what the pointed-to file already says in full. **The target shape is one terse sentence stating the current rule, plus the pointer** — not a paragraph-plus-pointer. If trimming a paragraph down to one sentence would lose a genuine boundary condition or caveat the rule depends on (not just color/backstory), keep that clause in the one sentence rather than dropping it — brevity never overrides correctness.

**Staleness** — independent of length, a rule can simply no longer be true: a superseded fix, a retired file path/tool, a workaround for a bug that's since been fixed at the root (making the workaround permanently unreachable), or a one-off gotcha whose underlying cause can no longer recur. These get **deleted outright**, not relocated to `NOTES.md` — moving a dead rule to a file nobody reads by default is barely better than leaving it in `CLAUDE.md`, and either way it wastes a future reader's time treating it as live guidance. When unsure whether something is actually stale (the underlying code/config hasn't been directly re-checked this session), verify before deleting rather than guessing — check the file/behavior the rule describes still matches reality.

## Steps

1. Read `CLAUDE.md` in full and identify, separately, (a) sections that have grown past "what is this and where do I go for more" into full narrative history, and (b) individual rules that may be stale (see "Staleness" above). Both are judgment calls, not transcription — do them in the main session, not `docs-writer`.
2. For each stale rule identified in step 1b, verify it against the actual current file/config/behavior it describes (don't delete on a hunch), then delete it outright — no relocation, no pointer. Note each deletion in the eventual commit message so the reasoning isn't silently lost.
3. For each narrative-bloat section belonging to a specific tool/folder, delegate the actual sweep to the **`docs-writer` subagent** (a cheap model is fine here) — announce the delegation explicitly ("Delegating to docs-writer to split the X section into X.NOTES.md") rather than running it inline. Give `docs-writer` the section(s) identified in step 1a and this instruction:
   - If a companion `<tool>.NOTES.md` (root-level tool) or `<folder>/NOTES.md` (per-folder tool) doesn't exist yet, create it, following the existing pattern (e.g. `some-tool.NOTES.md`, `some-folder/NOTES.md`).
   - Move the narrative content there verbatim (don't summarize away real citations/verification detail — the point is relocation, not deletion).
   - Leave behind in `CLAUDE.md`: **one terse sentence** stating the current rule/status (not a paragraph — see "Narrative bloat" above for the target shape and its one exception), and a pointer sentence to the NOTES.md file for the full history.
4. For candidate content that's a *procedure* (a repeatable "how to do X" workflow) rather than tool-specific history, check whether a skill already covers it before writing a new one — prefer extending an existing skill's Notes section over duplicating. If none exists and the procedure is genuinely repeated (not a one-off), propose a new skill to the user rather than just leaving the prose in `CLAUDE.md`. This judgment call stays in the main session, not `docs-writer`.
5. Re-read the trimmed `CLAUDE.md` end to end afterward to confirm every remaining pointer resolves to a real file/skill and nothing load-bearing got cut — this check also stays in the main session, since it's a judgment call about what matters, not transcription.
6. Commit the pass as its own commit (per `methodology.md` §6's commit trigger 2 — before/around a large rewrite) with a message describing which sections moved where and which rules were deleted as stale.

## Notes

- This mirrors the `anthropic-skills:consolidate-memory` skill's purpose (merge/prune/re-tighten) applied to project docs instead of personal memory files.
- Don't run this reflexively every session — it's a periodic pass, triggered by noticeable growth, an explicit ask, or your rules-doc-size `PostToolUse` hook nudging past its threshold, not a per-turn habit.
- Delegating the sweep itself to `docs-writer` keeps this mechanical, high-volume relocation work off the more expensive main-session model — see `methodology.md`'s tiered-work section for the reasoning.
