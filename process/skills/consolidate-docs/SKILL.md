---
name: consolidate-docs
description: Periodic maintenance pass covering three related but distinct targets — keeps CLAUDE.md lean (sweeps sections that have grown into dated, narrative bug-fix history into companion NOTES.md files, plus a staleness pass that deletes rules no longer true), prunes MISTAKES.md by archiving entries already promoted into CLAUDE.md, fully superseded, or aged out with zero recurrence, and prunes an overgrown tool NOTES.md by archiving closed investigations no longer needed to understand current behavior. Use when CLAUDE.md/MISTAKES.md/a tool's NOTES.md feels like it's grown noticeably since the last pass, the user asks to clean up/consolidate/trim the docs, or a doc-size threshold hook has fired.
---

# Consolidate project docs

Three related, but distinct, targets share this skill because they share the same underlying shape (a document has grown past the point where its full bulk is worth paying for every time) — but each has its own criteria and destination, covered in its own section below: **Pruning CLAUDE.md**, **Pruning MISTAKES.md**, **Pruning a tool's NOTES.md**.

## Pruning CLAUDE.md

`CLAUDE.md` is loaded in full on every session regardless of task, so its size is a fixed token cost every single time — unlike a tool's own `NOTES.md`, which only loads when someone's actually working on that tool. The goal isn't to lose information, it's to relocate it so it's paid for only when relevant.

### What to look for

Two distinct problems, checked separately — don't conflate them:

**Narrative bloat** — a section reads like a diary rather than a reference: dated bug-fix paragraphs ("Fixed 2026-08-XX: ..."), step-by-step verification blow-by-blow, or citation trails for a resolved investigation. It's *not* a candidate when it's a current-state fact, a standing behavioral rule, or a pointer — those are exactly what should stay. But even a legitimate standing rule is usually over-long: most existing entries are a full paragraph (3-5 sentences of *why*/*how it was found*/*the incident*) followed by a `Full incident: X.NOTES.md` pointer — and that paragraph typically just re-narrates what the pointed-to file already says in full. **The target shape is one terse sentence stating the current rule, plus the pointer** — not a paragraph-plus-pointer. If trimming a paragraph down to one sentence would lose a genuine boundary condition or caveat the rule depends on (not just color/backstory), keep that clause in the one sentence rather than dropping it — brevity never overrides correctness.

**Staleness** — independent of length, a rule can simply no longer be true: a superseded fix, a retired file path/tool, a workaround for a bug that's since been fixed at the root (making the workaround permanently unreachable), or a one-off gotcha whose underlying cause can no longer recur. These get **deleted outright**, not relocated to `NOTES.md` — moving a dead rule to a file nobody reads by default is barely better than leaving it in `CLAUDE.md`, and either way it wastes a future reader's time treating it as live guidance. When unsure whether something is actually stale (the underlying code/config hasn't been directly re-checked this session), verify before deleting rather than guessing — check the file/behavior the rule describes still matches reality.

### Steps

1. Read `CLAUDE.md` in full and identify, separately, (a) sections that have grown past "what is this and where do I go for more" into full narrative history, and (b) individual rules that may be stale (see "Staleness" above). Both are judgment calls, not transcription — do them in the main session, not `docs-writer`.
2. For each stale rule identified in step 1b, verify it against the actual current file/config/behavior it describes (don't delete on a hunch), then delete it outright — no relocation, no pointer. Note each deletion in the eventual commit message so the reasoning isn't silently lost.
3. For each narrative-bloat section belonging to a specific tool/folder, delegate the actual sweep to the **`docs-writer` subagent** (a cheap model is fine here) — announce the delegation explicitly ("Delegating to docs-writer to split the X section into X.NOTES.md") rather than running it inline. Give `docs-writer` the section(s) identified in step 1a and this instruction:
   - If a companion `<tool>.NOTES.md` (root-level tool) or `<folder>/NOTES.md` (per-folder tool) doesn't exist yet, create it, following the existing pattern (e.g. `some-tool.NOTES.md`, `some-folder/NOTES.md`).
   - Move the narrative content there verbatim (don't summarize away real citations/verification detail — the point is relocation, not deletion).
   - Leave behind in `CLAUDE.md`: **one terse sentence** stating the current rule/status (not a paragraph — see "Narrative bloat" above for the target shape and its one exception), and a pointer sentence to the NOTES.md file for the full history.
4. For candidate content that's a *procedure* (a repeatable "how to do X" workflow) rather than tool-specific history, check whether a skill already covers it before writing a new one — prefer extending an existing skill's Notes section over duplicating. If none exists and the procedure is genuinely repeated (not a one-off), propose a new skill to the user rather than just leaving the prose in `CLAUDE.md`. This judgment call stays in the main session, not `docs-writer`.
5. Re-read the trimmed `CLAUDE.md` end to end afterward to confirm every remaining pointer resolves to a real file/skill and nothing load-bearing got cut — this check also stays in the main session, since it's a judgment call about what matters, not transcription.
6. Commit the pass as its own commit (per `methodology.md` §6's commit trigger 2 — before/around a large rewrite) with a message describing which sections moved where and which rules were deleted as stale.
7. **If your doc-size hook tracks a growth-ratchet baseline** (recording each trim's post-size so a future nudge scales off it instead of a fixed threshold — see the `rules-doc-size` standalone hook, if you've extended it this way) **record the new post-trim size now.** Skip this if the file wasn't actually reduced in size (a staleness-only pass with no narrative-bloat relocation, for instance).

## Pruning MISTAKES.md

If your project nests other repos as subdirectories (see `methodology.md` §10), each one may maintain its own independent `MISTAKES.md`, addressed by its own explicit path rather than resolved automatically — this section applies to whichever repo's copy triggered the pass (per-repo scoping: "that repo's own `CLAUDE.md`" below always means the copy in the same repo as the `MISTAKES.md` being pruned). Most projects have just the one, in which case this scoping note is moot.

Unlike `CLAUDE.md`'s narrative-bloat problem, `MISTAKES.md`'s entries aren't candidates just for being old or long — the file's whole purpose is to be a dated incident log. Three specific candidate shapes only:

- **Already promoted into `CLAUDE.md`.** An entry may already end with a note like "(promoted the same day into CLAUDE.md directly...)" — that's a starting signal, but **verify it directly** by reading the named `CLAUDE.md` section and confirming the durable rule really is there, rather than trusting the entry's own claim (verify before consolidating, the same discipline this skill applies everywhere else).
- **Fully superseded.** The entry's underlying tool/mechanism/file no longer exists in the repo (verify via Grep/Glob, not assumption), making recurrence structurally impossible.
- **Single-occurrence, aged out.** An entry that never recurred (its shape never showed up again in a later entry, per a direct grep or a search over your own archived docs if you have one wired up) and is now **90+ days old with zero recurrence in that time** ages out on a timer, independent of the two shapes above — it was never going to get promoted, and the live file shouldn't hold it open-endedly waiting for a recurrence that may never come. Check its date against today directly before treating it as eligible; don't estimate.

**Explicit, stated distinction from `CLAUDE.md`'s own staleness step above**: `CLAUDE.md` deletes stale rules outright, because they're live guidance that's no longer true. `MISTAKES.md` entries are historical record, not live guidance — they are **archived, never deleted**, the same philosophy `BACKLOG_ARCHIVE.md` already applies to resolved `BACKLOG.md` items.

### Steps

1. Read `MISTAKES.md` in full and identify candidates against the three shapes above — for the age-out shape, check each entry's own date against today directly (don't estimate) and confirm its shape genuinely never recurred. Verify each one directly (read the named `CLAUDE.md` section; Grep/Glob for the claimed-gone tool) before treating it as confirmed. Judgment call — stays in the main session, not `docs-writer`.
2. Delegate the mechanical move to **`docs-writer`**, announced explicitly: create `MISTAKES_ARCHIVE.md` if it doesn't exist yet (header modeled on `BACKLOG_ARCHIVE.md`'s own opening paragraph — purpose, "not read by default" framing, an ongoing-convention note), move each confirmed entry's full `##`-headed text verbatim into it in date order, and leave a one-line pointer behind in `MISTAKES.md` at the original heading location: `## YYYY-MM-DD — <original title> — MOVED`, one sentence saying why (promoted into `CLAUDE.md`'s `<section>`, superseded because `<tool>` no longer exists, or `(single, aged-out YYYY-MM-DD)` for the age-out shape), and "Full record: `MISTAKES_ARCHIVE.md`." A recurrence check against an aged-out entry still searches the archive exactly as it would the live file — moving it never removes it from the promotion-recurrence check.
3. Re-read the trimmed `MISTAKES.md` afterward to confirm nothing load-bearing (an entry not actually promoted/superseded/genuinely-unrecurred) got moved by mistake.
4. Commit as its own commit.
5. If your doc-size hook tracks a growth-ratchet baseline (see step 7 above), record the new post-trim size for `MISTAKES.md` now.

`MISTAKES_ARCHIVE.md` is not created empty ahead of time — it's born the first time this pass actually finds a real candidate, the same way `BACKLOG_ARCHIVE.md` itself was born from an actual archiving action rather than a preemptive scaffold.

## Pruning a tool's NOTES.md

A tool's `NOTES.md` (or `<Tool>.NOTES.md`) is the intended *destination* for CLAUDE.md's own narrative-bloat sweep above, so "it's dated narrative history" can't be this section's trigger — that's the file's whole purpose. Three candidate shapes, checked in this order:

- **Duplicate — checked first, usually the highest-value cut.** Content already fully recorded, at comparable-or-greater detail, in `BACKLOG_ARCHIVE.md` *or any other indexed `.md` file* — not limited to `BACKLOG_ARCHIVE.md`; a tool's own retrospective doc, another `NOTES.md`, or a `Design Docs/<slug>.md` file all count (e.g. a retired tool's shutdown notes might already be fully covered by a separate review doc, not `BACKLOG_ARCHIVE.md`). **Verify fresh, every time** — independently re-read the cited location and confirm it actually matches before cutting; never trust a prior survey's citation or a matching heading alone. This isn't optional caution: a prior survey's classification — not just its line numbers — has been caught wrong on a meaningful fraction of planned cut cases before, confirmed the hard way, not just a hypothetical risk.
- **Keep** whatever a session needs before touching that tool's flagged code — current architecture, *why* a check works the way it does (not just what it does), anything a `CLAUDE.md` pointer explicitly says to "read before touching X."
- **Archive** a closed, dated investigation for a bug already fixed, complete with its full citation/verification trail, that is no longer needed to understand the tool's current behavior and isn't a duplicate of an existing record elsewhere — the same "full investigative record for entries that are done" framing `BACKLOG_ARCHIVE.md`'s own opening paragraph already uses.

A confirmed duplicate is cut to a stub, never deleted outright and never left as a bare heading (a heading with no body text under it is easy to skim past, and if you run any documentation-search/indexing tooling over these files, it may not surface at all):
```
## <original heading>

<One real sentence: what the bug/fact was and how it was fixed/established.> Full detail:
`<citation file>`'s "<matching heading>" entry. <Optional: any residual fact the citation doesn't
carry, named in one clause.>
```

### Steps

1. Read the tool's `NOTES.md` in full and identify candidates against all three shapes above, duplicates first. Judgment call — stays in the main session, not `docs-writer`. For each duplicate candidate, independently re-read the cited location before confirming — don't trust a heading match or a prior survey's own citation. If uncertain whether a passage is still load-bearing for understanding current behavior, keep it rather than guess.
2. Delegate the mechanical move to **`docs-writer`**, announced explicitly, handing it the exact per-section verdict (duplicate-to-stub with citation, or archive-verbatim) rather than leaving it to judge:
   - For confirmed **duplicates**: replace the section in place with the stub format above, using the exact citation file/heading you verified in step 1.
   - For confirmed **archive** candidates: create the archive file if it doesn't exist yet — `<Tool>.NOTES.ARCHIVE.md` for a root-level tool, `<Folder>/NOTES.ARCHIVE.md` for a per-folder tool, matching whichever of the two naming shapes the source `NOTES.md` itself uses — header modeled on `BACKLOG_ARCHIVE.md`'s. Move each confirmed section verbatim in date order, leave a one-line pointer behind at its original location, same shape as the `MISTAKES.md` pointer above.
3. Re-read the trimmed `NOTES.md` afterward to confirm nothing a `CLAUDE.md` pointer still says to "read before touching X" got moved or stubbed by mistake, and that every stub carries a real body sentence (not a bare heading).
4. Commit as its own commit.
5. If your doc-size hook tracks a growth-ratchet baseline (see step 7 of "Pruning CLAUDE.md" above), record the new post-trim size for this `NOTES.md` now.

Same non-preemptive-scaffold rule as `MISTAKES_ARCHIVE.md` above — the archive file is born on first real use.

## Notes

- This mirrors what a personal-memory consolidation pass does (merge/prune/re-tighten), applied to project docs instead.
- Don't run this reflexively every session — it's a periodic pass, triggered by noticeable growth, an explicit ask, or a doc-size threshold hook nudging (if you have one wired up — see the `rules-doc-size` standalone hook — extended to cover `MISTAKES.md`/a tool's `NOTES.md` the same way), not a per-turn habit.
- Delegating the sweep itself to `docs-writer` keeps this mechanical, high-volume relocation work off the more expensive main-session model — see `methodology.md`'s tiered-work section for the reasoning. This applies to all three targets above, not just `CLAUDE.md`'s.
- If you keep a design-doc history, the full reasoning behind your own `MISTAKES.md`/`NOTES.md` size thresholds and archive destinations belongs there, not repeated in this file.
- **If your doc-size hook supports a growth-ratchet baseline, always record the post-trim size for whichever file(s) this pass actually shrank** — this is what lets the nudge fire at some multiple of that size instead of the original fixed threshold, so a file trimmed once doesn't have to regrow all the way back to the same absolute number before the next nudge. Skip it for a pass that found nothing to cut.
