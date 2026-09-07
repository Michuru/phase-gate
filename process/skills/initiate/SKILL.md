---
name: initiate
description: Session-start ranker — surveys the project's own tracked state (a live handoff primer, the BACKLOG.md implement-queue checklist, every Design Docs/ file's own Kind/Status record), sorts everything by actionability instead of stopping at the first matching signal, and closes by naming the correct next command for the top item. Use when the user types /initiate, asks "what's going on," "what should I work on," "what's in flight," or starts a session wanting to pick up wherever things left off.
---

# Initiate: the session-start ranker

Mirrors `end-task`'s own structure (if you have that skill installed) as its session-*start*
counterpart — survey → sort → report. Same discipline: **thin dispatcher, real delegation.** This
skill detects and routes; it never prints its own backlog list, never starts its own investigation,
and persists no state of its own between invocations. If you also have `end-task` installed, the two
bind the same "next-command contract" as the parent-level ranker/router pair: rank by actionability,
collapse what can't be acted on to one line, separate "waiting on someone else" from "waiting on your
decision," one screen.

## Step 1: Survey

Gather the raw facts Step 2 sorts, in this order:

1. **Invoke `handoff` incoming mode unconditionally** — don't pre-check its directory first.
   Detection *is* `handoff` Step 0's own scan; it already discovers every sibling repo dynamically,
   handles the zero-primer case gracefully, and lists multiple live candidates for the user to pick
   from rather than silently guessing the most recent. Reimplementing that scan here would just do
   it worse. **`handoff`'s own multi-candidate list is exempt from Step 3's ≤12-line budget** — it's
   `handoff`'s own interactive output, not this ranker's.
2. **Determine whether this project has any process history at all.** Check for `Design Docs/` and
   `BACKLOG.md` in **the current repo, resolved upward** — a sub-repo nested under a parent may have
   neither of its own (both may live only in the parent), so check upward through parent directories
   before concluding "none." A naive same-directory-only check false-fires on every sub-repo session.
   **Bounded, explicit algorithm** (a manual file-existence walk, not any harness-level rules-doc/
   skill upward-resolution mechanism — that kind of mechanism typically does *not* extend to
   `BACKLOG.md`-shaped files, only to specific filenames the harness itself recognizes): check the
   current directory first; if not found, check exactly **one** parent directory up and stop there.
   If your workspace nests sibling repos more than one level deep, extend this bound to match your
   actual layout — don't walk arbitrarily far by default.
3. **Read `BACKLOG.md`'s "Ready to implement" checklist section.** Note whether it's empty or has
   entries.
4. **Read every `Design Docs/*.md` file's `Kind:`/`Status:` line.** Collect every `Kind: work-item`
   doc, whatever its status — `running`, `blocked-on-user: <what>`, `blocked-on: <who/what>`, or the
   legacy plain `blocked: <detail>` form (per `spec/SKILL.md` Step 3.1, read as `blocked-on-user`).

## Step 2: Sort into A/B/C — no stop-at-first-match

**If no project history exists at all** (Step 1.2 came back empty) but the repo has real existing
code or a scope/spec document, that's the adopting-onto-an-existing-project case — say so in one
line and hand off to **`/adopt`** instead of running the sort below. Once `/adopt`'s inventory pass
has run for this project, this branch never fires again for it.

**If no project history exists AND the repo has no real existing code or scope/spec document
either** (a genuinely blank, brand-new project — no history to inventory and nothing for `/adopt`'s
scoping pass to do) — say so in one line and name **`/spec`** (the user already has something
specific in mind to build) or **`/backlog`** (nothing specific yet — start capturing ideas) as the
next command, rather than running the sort below on nothing and reporting an empty screen.

Otherwise, survey everything from Step 1 and sort every real item (a live primer, a checklist entry,
an in-flight design doc, an unblocked `BACKLOG.md` item) into exactly one bucket — never stop at the
first one found, the way a signal ladder would:

- **C — waiting on someone/something else.** Any `Status: blocked-on: <who/what>` item. Collapse to
  one line, named parties/events only — not routable, so don't rank these against A.
- **B — waiting on your decision.** Any `Status: blocked-on-user: <what>` item (including the legacy
  plain `blocked: <detail>` form). Cheap, high-leverage unblocks — one line each, named plainly. A
  decision only the user can make is functionally actionable, unlike bucket C.
- **A — actionable now.** Ranked: live `handoff` primer (Step 1.1) → `implement-queue` checklist
  (Step 1.3, if non-empty) → unblocked in-flight item (a `Kind: work-item` doc with `Status: running`
  and no `blocked-on`/`blocked-on-user`) → unblocked `BACKLOG.md` item (hand off to `/backlog` List
  mode for the raw list; don't reimplement it here).

## Step 3: Report — one screen, ranked, next command named

```
Waiting on others: a dependency's release, a teammate's review, an external event.
Waiting on you:    one pending go-ahead decision.

9 you can start now — top 3:
  1. <item> — <why it's ranked here>                          Design Docs/<slug>.md
  2. <item> — unblocked, not started
  3. <item> — stale since a related change, worth a refresh

Start #1 with /spec, or /backlog for the full list?
```

- **Bucket C, one collapsed line** — named parties/events, not a table, not one line per item; group
  by who/what they're waiting on.
- **Bucket B, one line each** — give these room even though they're technically "blocked."
- **Bucket A, ranked, top 3 shown with a real count of the rest** — never print the whole list here;
  that's `/backlog`'s job. If a live `handoff` primer exists, its own confirmation/multi-candidate
  output (Step 1.1) runs first and doesn't count against this screen's line budget.
- **Always report the open-backlog count too**, approximate, never exact — `BACKLOG.md` carries no
  structural open/closed marker, so superseded entries, pointer-only standing notes, and items whose
  real scope has moved elsewhere all still match. One deterministic call, no judgment:

  ```
  awk '/^## /{h=$0} /^- \*\*/{n++; s[h]=1} END{print n, length(s)}' BACKLOG.md
  ```

  ```
  Open backlog: ~16 tracked bullets across 7 sections (some may be superseded or
  pointer entries) — run `/backlog` for the real list.
  ```

- **Close by naming the next command** — the recommendation names the correct command for the top
  Bucket-A item's own phase (a primer resumes directly, a queued design goes to `/build`, a
  spec-stage item to `/spec`, a plain backlog item to `/backlog`); the named alternative is always
  `/backlog` for the full list. Never a full stop, never an open menu over every bucket at once.

## Notes

- **Stateless, re-derived every invocation.** This skill reads state that other phases wrote
  (`handoff` primers, `BACKLOG.md`'s checklist, Design Docs' own `Kind:`/`Status:` lines); it
  persists none of its own. This is why a scenario dry-run for cross-session state logic doesn't
  apply here — that's reserved for skills that do carry real state via an archive gate.
- **Cross-reference, never duplicate.** If your setup has `end-task`, `handoff`, `backlog`, `adopt`,
  and `implement-queue` skills, don't add a second copy here of anything those already own. If a
  bucket's handling needs more explanation than the routing line above, that explanation belongs in
  the skill it routes to, not here.
- **A clearly-biggest-tier planning request has skipped straight to `EnterPlanMode` without invoking
  `spec` at all before now.** Because neither skill ran, `spec`'s own Step 1 model-check never fired
  either — exploration and the first several plan drafts ran on the wrong model, and the user had to
  notice and request a model switch manually, mid-session. The fix is cheaper than "remember to
  invoke a skill": before calling `EnterPlanMode` for anything shaped like a plan/design/roadmap/
  new-tool request, check in your head whether this project has any process history at all, even
  with no skill file in front of you — the same check Step 2 above makes explicit.
- **Rewritten from a stop-at-first-match signal ladder to this rank-everything sort.** The ladder
  answered "which single condition fired first" when the real operator question is "what should I do
  now" — those diverged concretely in practice: a run fired on several in-flight items, most blocked
  on other people, crowding the one genuinely actionable item to the bottom before an open-ended
  question. Ranking by actionability instead of internal state category fixes this at the root
  rather than patching the report. The former adopting-onto-an-existing-project scoping pass moved
  out to its own skill, `/adopt` — see that skill and `spec/SKILL.md` Step 0.5.
- **Local-model fit: not applicable.** Every check in Step 1/2 is deterministic (file existence, a
  directory listing, a status-line read) — exactly the kind of check that's preferable over a
  probabilistic guess, and there's no generation step here for a local SLM to plausibly take over.
