# end-task: full-sync depth

Read from `SKILL.md`'s routing table when any docs-sync question was a yes. The commit rules and the push ask are in `SKILL.md` and apply to the commit pass below; they are not repeated here.

## Contents
- Docs pass
- Commit pass
- Cheat-sheet sync (conditional)
- Downstream-export drift check (conditional)
- Downstream-export new-component consideration (conditional)
- Close-out summary

## Docs pass

For each doc type, judge whether this session's work is actually reflected yet. This is a judgment call, not a mechanical sweep: skip anything already current.

- **Your rules doc**: a new tool, skill, structural fact or changed behavior not yet documented? If your setup has more than one (a shared parent plus per-repo ones), update the one that owns the content (cross-cutting process in the shared one, a specific repo's own structure in that repo's file). Use `Edit`, never `Write`. A one-line fix goes directly; anything more substantial (a new NOTES.md section) goes to the `docs-writer` subagent, announced explicitly.
- **Tool `NOTES.md`**: an architecture fact, live caveat or schema for a tool that has its own `NOTES.md`, not yet recorded? If so, delegate to `docs-writer`. Not dated fix narrative (that belongs in `BACKLOG_ARCHIVE.md` or the commit message, if your rules doc draws that same distinction).
- **`BACKLOG.md` / `BACKLOG_ARCHIVE.md`**: anything resolved and verified this session that was not archived? The `backlog` skill's own archive step normally handles this; this is a catch for anything that slipped through.
- **`MISTAKES.md`**: any process mistake surfaced this session and not yet logged? Usually already logged the same turn; this is a last-chance catch, not a re-investigation.
- **Size findings** (from the file sizes checked in the survey, for every repo touched): for any file past its threshold, either run `/consolidate-docs` now or tell the user it is pending. Never silently ignore an already-fired nudge.

## Commit pass

The commit rules and push ask in `SKILL.md`, for every verified complete change the docs pass identified plus anything the survey found.

## Cheat-sheet sync (conditional)

Only if you maintain a cheat-sheet artifact (a command-reference doc or a short daily-driver list), and only if this session added, removed or renamed a skill, or materially changed what an existing one does (not a wording tweak). Update it directly and, if it is a published artifact, republish it to its **existing** URL, never a new one. If you also keep a shorter daily-driver list, judge whether the changed, new or removed skill belongs on it (a renamed or removed skill already listed always needs its line updated or dropped; a brand-new skill earns a line only if a session would reach for it by name often); that judgment is independent of whether the larger cheat sheet changed. Skip if you maintain nothing like this or the roster did not change; do not edit or republish just to bump a date.

## Downstream-export drift check (conditional)

Triggered by question 7, and only if you maintain a downstream export (uncommon). If this session edited a skill, agent or hook file your export already tracks, run whatever drift-check mechanism you use and re-generalize whatever it flags (patch the exported file, update your own tracking record, re-run to confirm clean). Skip if you maintain no such export or none of its tracked files were touched.

## Downstream-export new-component consideration (conditional)

Only if question 6 was a yes: raise it explicitly instead of letting the session end without it. Ask whether the new skill, agent or hook should be ported now (generalize it, add it to your export's own tracking, confirm it is clean) or explicitly declined. Say the answer plainly and note it somewhere findable (a one-line `BACKLOG.md` or design-doc note is enough) so a later session does not re-ask with no record.

## Close-out summary

One message covering: commits made (hash and one line each, labeled by repo), which docs were touched and how, whether any cheat-sheet artifact was refreshed, and what is still open across `BACKLOG.md`, so the user can pick up next time without re-asking. Present the still-open part as a short numbered list, one line per item, with any item resolved this session shown struck through (`~~text~~`) in place rather than dropped; the `backlog` skill's still-open list convention (if you have that skill installed) is the model. Do not re-expand any item's investigation detail.
