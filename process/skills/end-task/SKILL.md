---
name: end-task
description: Close a session. Surveys what changed, checks first for unfinished work, then routes to /handoff (a primer for a fresh session) or to a wrap-up at narrow-commit or full-sync depth, always naming /handoff as the alternative. Use when the user types /end-task, or asks what to do before clearing, whether it is clean to clear, or to end the task.
---

# End-task: the parent-level close router

Survey, detect, route, report: the session's close-out counterpart to `initiate`, if you have that
skill installed. If you do, the two bind the same "next-command contract" as the parent-level
ranker/router pair: one screen, collapse what cannot be acted on, and **surface the fork to
`/handoff`, never silently pick it**. **Manual invocation only**: Claude Code has no `/clear` hook,
so nothing fires this; `/end-task` then `/clear` is the habit.

## Survey

**Once per repo actually touched this session.** Recall from the conversation which repo or repos had
any work land in them (if your workspace spans more than one, e.g. a parent repo plus nested
sub-repos, each its own git root). Name repos by recall; never survey a fixed list, so a deploy repo
or any other repo is covered without a special case. In each one, run `git status` (never `-uall`)
and `git diff --stat` to see the real on-disk picture. Dirty files can belong to another session, so
judge which of them this session edited by recall, and scope the verdict to those. A parent repo's
own `.gitignore` commonly excludes its nested sub-repos outright, so a survey at the parent root alone
will never see them: survey each by its own repo.

If a shared file (your rules doc, `BACKLOG.md`, `MISTAKES.md`) shows `MM`, or staged entries appear
that are not yours, flag it per your rules doc's multi-session guidance instead of folding it into the
verdict.

Also check, while surveying: whether any `Design Docs/` file edited this session is an unfinished
work-item design (the next section), and the sizes of the rules doc, the mistakes file and any
`NOTES.md`/`*.NOTES.md` in each repo touched (question 8 below).

## Unfinished-work check (first, before anything below)

**Work unfinished** fires, and nothing below runs, when any of these holds:

- A `Kind: work-item` design doc (under `Design Docs/`) was edited this session with no done
  `## QA gate`, **except** one that was reviewed and backlogged and whose `## Build` has not started
  (that is a design waiting its turn, not work in flight).
- An open Plan Mode plan exists with no matching saved `Design Docs/<slug>.md` yet.

Check this before the questions below, on purpose: a session mid-design or mid-build must never be
routed toward "commit and clear", even when the working tree happens to be clean at this moment.

## Docs-sync questions (only if nothing is unfinished)

Answer each concretely, by checking, not by impression (checking whether something is already
recorded beats assuming it is new):

1. **Your rules doc** (any repo): a new tool, skill, structural fact or changed behavior from this
   session not yet documented?
2. **Tool `NOTES.md`**: an architecture fact, live caveat or schema a future session needs, not yet
   recorded? Not dated fix narrative: that goes in `BACKLOG_ARCHIVE.md` or the commit message (if your
   rules doc draws that distinction, follow it).
3. **`BACKLOG.md` / `BACKLOG_ARCHIVE.md`**: an item resolved this session but not archived?
4. **`MISTAKES.md`**: a process mistake surfaced this session and not logged?
5. **A cheat-sheet artifact** (a command-reference doc or short daily-driver list, if you maintain
   one): was a skill added, removed, renamed or materially changed, with the cheat sheet not showing it
   yet? (Check the file directly; a session that already synced it answers no. Skip if you maintain
   nothing like this.)
6. **A downstream export of your own** (uncommon; skip this and question 7 unless you actually
   maintain one: a generalized copy of your customized skills, agents or hooks that you publish or copy
   into a separate project). Was a wholly new skill, agent or hook added (not merely edited)? If so,
   has "port it there or decline" actually been decided and recorded (the session's response, a
   `BACKLOG.md` entry or a design doc)? Not-yet-decided is a yes. Skip if nothing new was added.
7. **Drift on an already-exported component** (same "uncommon, skip if it does not apply" scope): did
   this session edit a skill, agent or hook your export already tracks? If so, has your drift check (a
   script, or a side-by-side diff) been run clean since? Not-yet-checked is a yes (a plain edit to an
   exported file otherwise answers no to every other question, so the drift check would never run).
   Skip if no exported file was touched.
8. **Size thresholds** (mechanical, not a judgment): if you have a hook or a habit that flags your
   rules doc, mistakes file or a `NOTES.md`/`*.NOTES.md` once it grows past a size, is any such file in
   a repo touched this session past that threshold? Read the actual sizes, never assume; a file past its
   threshold is an automatic yes. Skip if you track no size threshold.

When unsure whether a question is a yes, take the deeper mode: it is a superset of the narrow one, so
the wrong answer is cheap in exactly one direction.

## Route and report

| Detected state | Recommendation | Named alternative |
|---|---|---|
| Work unfinished | **`/handoff`**, to write a primer so a fresh session continues | wrap up anyway, if you are actually done despite the signal |
| Any yes in the questions | **Wrap up at full-sync depth** (read `${CLAUDE_SKILL_DIR}/references/full-sync.md` now) | **`/handoff`**, if you are actually still mid-task |
| Dirty repo or repos, no yes | **Wrap up at narrow-commit depth** (the commit rules below) | **`/handoff`**, if you are actually still mid-task |
| No dirty repos, no yes | `Clean — nothing pending. Clear to /clear.` | **`/handoff`**, if you are actually still mid-task |

`/handoff` appears in **every** row: that is what makes it discoverable to someone who does not know
it exists. State which row fired and why, the concrete signal and not just the verdict, before doing
that row's work.

## Commit rules (both depths)

For each verified, complete change the survey found, and anything else sitting modified that is
genuinely finished and not mid-edit: stage narrowly (`git add` named files, never `-A` or `.`) and
commit in the repo that file actually lives in, with a message describing the change; pass the commit
trailers the session's attribution reminder specifies. If it is unclear whether something is finished,
ask; never fold a half-done change into a commit just to clear the tree. Mid-investigation changes may
stay uncommitted.

**Ask about pushing, once per repo that has a remote configured: this is the only point in the session
that asks** (pushing is batched here, not asked after every commit-producing skill). Check each repo's
own `git remote -v` rather than assuming from another repo in the same workspace. Cover *every* commit
made in that repo this session, including those `ship` and `backlog` made earlier without asking, and
ask proactively whether to push now. It still needs an explicit yes.

**If a repo you maintain publishes versioned releases (a `CHANGELOG.md` plus git tags, or similar) and
this session just pushed to it, ask whether a release should be cut.** Look at the changelog's
unreleased section: if it has real content after this push, ask whether to cut one now or hold. Not
every push needs a release, but the question must never go unasked. Skip if you publish no versioned
releases from any repo touched this session.

**Report** per repo: commit hash and one line for anything committed, and an explicit call-out of
anything deliberately left uncommitted and why. Silence would look the same as "nothing was left
outstanding", which is the ambiguity this report exists to remove.

Out of scope: this skill does not change `handoff`'s own mechanics; it only routes to it.
