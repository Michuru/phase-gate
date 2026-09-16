---
name: implement-queue
description: Implement several already-approved design docs in parallel via the saved implement-queue workflow, replacing manually running 2-3 Claude Code windows side by side. Use when the user invokes /implement-queue, or asks to run/build/ship what's queued up in BACKLOG.md's "Ready to implement" checklist.
---

# Implement the queue

This skill only replaces the *implementation* phase of already-approved designs; planning and
`spec` stay fully manual, unchanged. **`execution-gate` is the upstream skill that decides a
design's own execution strategy** — this checklist section is for whole separate designs, each its own
`{designDocPath, backlogEntryText, toolName}` unit, never a task fragment of one design, even one
`execution-gate` flagged as internally parallelizable.

**`designDocPath` convention**: a bare path relative to `design_docs_dir` (e.g. `<slug>.md`, not
`Design Docs/<slug>.md` and not an absolute path) — the workflow script joins it against `design_docs_dir`
itself. Keep every checklist entry and every design doc reference to this convention consistently; a mixed
convention (some entries bare, some with the folder prefix) is exactly the kind of drift this field exists
to prevent.

## Step 1: Read the queue

Read `BACKLOG.md`'s **"Ready to implement" checklist section** — this is the queue, an explicit list,
not a grep. Per that section's own rule, an item only appears here if it has **no unmet prerequisite**.
For a Tier 1/2 design, a pending cross-model review is satisfied automatically once `spec`'s
Step 3.4 has actually run and recorded a clean or found-something outcome — it's still a real, unmet
prerequisite only when that review was declined or failed without a successful rerun. Other unmet
prerequisites (a blocked question, user input not yet given) work as before, and an item with one
stays in its own tool section instead of being listed here at all. So every line in the checklist
section is, by construction, eligible; there's no separate ineligible-but-listed state to filter.

## Step 2: Resolve each candidate's repo root — never mix repos in one batch

**Only applies if this repo sits inside a nested workspace of sibling repos** (the same structure
`handoff`'s own sibling-discovery check looks for) — most adopters running this from a single
standalone repo can skip straight to Step 3, where `repoRoot` is simply this repo. If you do use a
multi-repo split (a tool's real code/docs live in one of several sibling repos, not the one this
skill runs from), resolve each candidate's `repoRoot` per your own repo-to-tool mapping — whichever
sibling repo directly contains a file or directory named exactly `toolName` wins; if none matches,
`repoRoot` is this repo itself (a cross-cutting or design-docs-only item).

**This isn't cosmetic.** `Workflow`'s `agent(..., {isolation: 'worktree'})` creates its sandbox against
whatever repo the orchestrating session's own cwd is rooted in at the moment `Workflow` is called — not
per item, and with no override available to the script. A batch whose items resolve to different
`repoRoot`s can't run together in one `Workflow` call: the implement stage for any item outside that one
repo can Read its files but has every mutating tool refused by the harness's worktree-isolation guard.
**Group batches so every item in one batch shares the same `repoRoot`** — split an otherwise-eligible
batch across repos rather than mixing them, even if that means a repo-only batch smaller than 3.

## Step 3: Pre-run cleanliness check

For each eligible candidate, run `git status` against that tool's own files (from within its resolved
`repoRoot`). Any candidate whose target files are already dirty is a signal another session may be
mid-edit on it (per your rules doc's multi-session guidance) — flag it and exclude it from this round
rather than silently proceeding.

**Also capture this batch's single `baseCommit` now, before calling `Workflow`**: `git -C <repoRoot>
rev-parse HEAD`. Record that exact hash and reuse it — never re-resolve your default branch name per
item — for every item's Step 6 checks in this batch. Step 6 harvests items sequentially and each commit
advances that repo's real `HEAD`, so re-resolving a branch name mid-batch would diff item 2 against a
tree that already contains item 1's just-applied changes, not the common ancestor every worktree
actually branched from — corrupting the diff for any file more than one item touches.

## Step 4: Confirm the queue, batches of 3

Show the clean, eligible candidate list to the user and let them add/remove/reorder before running —
never trust the list silently. **Repo grouping (Step 2) takes priority over batch sizing**: first
partition the confirmed list into groups by `repoRoot`, preserving the user's order within each group;
only *then*, within each repo-group, split into **sequential batches of 3**. Two items with different
`repoRoot`s are always in different batches, even when the combined total is 3 or fewer — a repo-only
batch smaller than 3 is expected, not an error. For the batch about to run, state the agent count (3 per
item, more if a QA fix loop fires) and that it's roughly `3 × items` fresh-context agents, so the yes is
informed by real spend — then get an explicit go-ahead before calling `Workflow`.

## Step 5: Run the batch

**Before calling `Workflow`, `cd` this session into the batch's shared `repoRoot`** (all items in one
batch share one, per Step 2) and confirm it actually landed there (`pwd` or
`git rev-parse --show-toplevel`) — a prior command in the same turn can leave cwd somewhere unexpected.
Then call `Workflow({ name: 'implement-queue', args: batchItems })`, where `batchItems` is
`[{designDocPath, backlogEntryText, toolName}, ...]` for just this batch (no `tier` field — nothing
downstream reads it). Wait for the result; don't poll.

## Step 6: Harvest and commit — sequential, never inside the workflow

**This step is the real enforcement boundary for `GIT_BOUNDARY`, not just a formality.** A prompt telling
an agent not to commit or touch shared docs is advisory only — a confirmed real case exists of an
implement-stage agent doing exactly that anyway (editing `BACKLOG.md` and running `git commit` inside
its own worktree). Nothing in this harness lets a stage's own tool calls be structurally blocked
mid-turn, so the boundary has to hold here instead, at the one point fully under your control before
anything reaches the main tree.

**Run the anomaly checks below for every item in the batch's results first, regardless of its reported
status** — a `blocked` item's worktree gets exactly the same scrutiny as a `done` one. This is
deliberate: that incident's forbidden commit reached the default branch only after a later session, while
manually resolving what it treated as an ordinary blocked/loose-end item, fast-forwarded that worktree's
branch in by hand. An item whose *reported* status is `blocked` is precisely the case a future session
is most likely to handle by hand later, outside this skill's own Step 6 apply path — so it's the case
that most needs an automated, visible flag now, not less.

For **every** item in the batch's results, in this order:

0. **First, `git -C <worktreePath> add -N .`** (intent-to-add — registers every untracked path so it
   shows up in a diff, but stages none of its actual content; confirm with `git -C <worktreePath> status
   --short` that no path shows as anything other than its prior state or a fresh `A`). Do this before
   either check below. **Plain `git diff` never shows genuinely untracked files, no matter what base
   it's compared against** — a real implement stage can create new files, and `git diff <baseCommit>
   --name-only` without this step would silently omit all of them. This isn't just an incomplete
   harvest — it means the forbidden-path check in step 2 below could miss a real `GIT_BOUNDARY`
   violation too, if a stage created a *new* file directly under a forbidden path instead of editing an
   existing one.
1. **Check for stray commits**: `git -C <worktreePath> rev-list <baseCommit>..HEAD` (the `baseCommit`
   captured once in Step 3, not re-resolved here). This must come back empty — `GIT_BOUNDARY` forbids
   every stage from committing inside its own worktree. Any commit hash here is itself an anomaly.
2. **Check for forbidden-path edits**: `git -C <worktreePath> diff <baseCommit> --name-only` — list
   every changed path (now including new files, per step 0). It's an anomaly if this list includes
   `CLAUDE.md`, `BACKLOG.md`, `BACKLOG_ARCHIVE.md`, `MISTAKES.md`, or anything under `.claude/` (skills,
   workflows, settings, hooks) — those are exactly the shared/config files `GIT_BOUNDARY` tells every
   stage never to touch.

**If either check finds an anomaly**: this item's worktree is tainted, regardless of what status it
reported. Don't harvest, apply, or touch its files at all — leave the worktree exactly as-is — and add
it to Step 7's batched questions as its own distinct anomaly (not folded into an ordinary `blocked`
write-up), explicitly telling the user: don't `git merge`/`rebase`/fast-forward this worktree's branch
by hand to "resolve" it — that exact action is what let the original incident's forbidden commit reach
the default branch. Report which check tripped and the offending commit hash / path list so the user can
inspect the worktree directly before deciding anything.

**If neither check finds an anomaly and the item's status is `done`**, proceed:

3. `git -C <worktreePath> diff <baseCommit>` is the authoritative patch (not any stage's self-reported
   `filesChanged`, and not the tainted-worktree case above). Apply it to the main tree, stage exactly
   those paths, commit with a message drafted from the design doc and its `BACKLOG.md` entry. **Never
   `git merge`, `git rebase`, fast-forward, or otherwise bring the worktree's own branch/commits into
   the default branch wholesale** — always this scoped patch, never the branch itself.
4. **If this design's tool has a deploy target (a `publish-*` skill exists for it), invoke `/ship`
   instead** — it now owns the archive-and-commit step for anything it publishes, per
   `ship/SKILL.md` Step 2. Otherwise, move the item's `BACKLOG.md` entry (both its checklist line
   and its full tool-section entry) to `BACKLOG_ARCHIVE.md`, per `backlog`'s existing cut-and-paste
   convention, **and write `## Shipped — done` into this item's `Design Docs/<slug>.md` file first**
   (same write-on-entry instruction `ship/SKILL.md` Step 2 uses for the deploy-target case) — this
   design doc always exists here (this checklist only ever holds items that went through `spec`),
   so this write is never skippable in this branch the way it can be for a plain `BACKLOG.md`-only
   item elsewhere.
5. Report the commit hash.
6. Check whether the worktree needs explicit removal after a changed-then-harvested state (undocumented
   by the workflow tool for this case) — remove it if so. **If `git worktree remove` fails with a
   permission/busy error, don't retry blindly**: a live-verification sub-step may have started a local
   dev/test server inside the worktree that never got stopped, holding a file lock. Find and stop it by
   its exact PID (never by image name, which can kill an unrelated process with the same name) before
   retrying removal.

**If neither check finds an anomaly and the item's status is `blocked`**, don't touch its files or
`BACKLOG.md` entry yet — collect it for Step 7 as an ordinary blocked question.

## Step 7: Blocked-item questions, batched

If any items in the batch are `blocked`, present all of them together via `AskUserQuestion` (chunk into
groups of ≤4 if there are more). Once answered, either resume via
`Workflow({ name: 'implement-queue', resumeFromRunId })` (same saved-workflow invocation as the
initial call in Step 5, not a raw `scriptPath`) with the **same full
batch array**, the answer folded into that item's `designDocPath`/prompt context (never a filtered
array — that invalidates every downstream cache entry), or, if it's a single simple item, just finish
it directly in the main session instead of spinning up a resume run.

## Step 8: Between-batch checkpoint

If another batch remains: report what this batch shipped (hashes) and what's still blocked, then ask
whether to proceed with the next batch as originally ordered, reorder it, or stop here. Don't
auto-continue.

## Step 9: Final summary

Once the confirmed batches are done (or the user stops early): commits made (hash + one-liner each),
anything still blocked and awaiting an answer, and what's still open across `BACKLOG.md`/`Design Docs/`
— same "show what's open" convention every other backlog-touching skill in this repo ends with.
