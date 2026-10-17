# spec: backlogging a saved design (option (b))

Read from `SKILL.md` before offering or acting on option (b), "file it as a `BACKLOG.md` item". Option (d) (hand off) does everything here too, and then runs `/handoff`, except the session-close line below, which `/handoff` replaces.

## The forbidden-path test (run first)

Run the same test `execution-gate` runs: if any task in the design's breakdown touches `CLAUDE.md`, `BACKLOG.md`, `BACKLOG_ARCHIVE.md`, `MISTAKES.md` or anything under `.claude/` (skills, workflows, settings, hooks), `/implement-queue`'s harvest step will flag the design as tainted and harvest nothing. Then do **not** add it to the checklist, whatever the tier or prerequisite state. Keep it tracked in its own tool's `BACKLOG.md` section (or a cross-cutting one such as "Environment / machine setup" for infra-shaped work), note the disqualification, and point at the design doc.

## The checklist line

Otherwise add a line to `BACKLOG.md`'s "Ready to implement" checklist: the design doc path, the tool name, the tier, and "no unmet prerequisite". For a Tier 1 or 2 design the prerequisite (the design review) is satisfied once the automatic review has actually run and recorded a clean or found-something outcome; it is never satisfied by construction. When the review was declined or failed without a successful rerun, do not add the line yet: add it once a review completes. For Tier 3 (which never runs the automatic review) the prerequisite is whatever else is genuinely unmet: a blocked question, user input not yet given. This is a deliberate queue entry, not a phrase to grep for: it is what makes the design pick-up-able by `/implement-queue` and not only by a human re-reading the tool's section. If `execution-gate` flagged a genuinely independent parallel subset (its rare Bucket E), that recommendation lives in the design doc's own `## Execution strategy` section, never as a separate checklist entry: the checklist holds whole, independently implementable designs only.

## Commit the doc and its pointer

Once the `BACKLOG.md` edit (the checklist line, or the tool-section note when the forbidden-path test disqualifies it) is written, **auto-commit it together with the design doc**, narrowly staged (`git add "Design Docs/<slug>.md" BACKLOG.md`, never `-A` or `.`), with no confirmation needed (the standing local-commit authorization in your rules doc's commit-conventions section covers it). A session that just closes the window afterward could otherwise lose or leave dirty a change that is already verified and complete in every sense that matters. This is scoped to this one combination: `backlog`'s plain quick-capture mode is deliberately not made to auto-commit every note.

## Close with an explicit session-close line

Never close option (b) with only the future `/build`: say whether this session is finished. After the auto-commit lands, check whether anything this session itself changed is still uncommitted. **If so, recommend `/end-task`. If not, say plainly that it is safe to `/clear` now** (the design doc and its `BACKLOG.md` pointer are the primer, and a fresh session's `/initiate` ranks the design on its own) and name `/build Design Docs/<slug>.md` as what to run after the clear. Either way, name `/handoff` as the one alternative, worth it only if this session holds decisions or context the design doc does not record. One recommendation, one alternative.
