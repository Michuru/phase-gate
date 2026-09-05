---
name: review-pr
description: Run a stranger's-eye GitHub PR review end-to-end — resolve the repo/PR, delegate finding-generation to the built-in code-review/security-review skills, post a real GitHub PR review via gh, check merge status factually, and hand the user an explicit merge-now-vs-hold decision. Use when the user wants to review a GitHub pull request, asks to check a PR's mergeability, or wants to merge one.
---

# Review a GitHub PR (stranger's-eye)

Orchestrates one full PR-review lifecycle per invocation, on whatever repo the user points it at (any
repo with a configured `gh` remote — not hardcoded to any one tool). It delegates all actual
finding-generation to the built-in `code-review`/`security-review` skills; its own job is resolving
ambiguity (which repo, which PR), sequencing the required user checkpoints, posting via `gh pr review`,
and reporting merge-blocking facts plainly. Design/rationale, including its cross-model review and
synthesized fixes, is folded directly into the steps below — there is no separate design doc in this
export.

**Out of scope for v1**: reviewing multiple open PRs in one pass; true per-line inline GitHub review
comments (the `gh api .../reviews` POST path is blocked by the Auto Mode permission classifier — see
Notes); writing to `BACKLOG.md` directly (always goes through `work-backlog`).

## Requirements

`gh` (GitHub CLI), installed and authenticated (`gh auth status`). The bundled `code-review` and
`security-review` skills, which this skill delegates all finding-generation to.

## Repo/PR resolution — never guess when ambiguous

Runs in the **invoking session's own current working directory** — decisive, not incidental, especially
in a nested-repo layout (a parent repo with zero GitHub remotes of its own, one or more nested sub-repos
each with exactly one, and a nested tool repo one level deeper that is its own git root). Always
announce which directory and remote resolved, so an unintended single-remote auto-bind is immediately
visible and correctable.

- Parse `git remote -v` for `github.com` URLs (both `https://` and `git@` forms), dedup by owner/repo,
  not remote name (a remote can be named anything, e.g. `foo` rather than `origin`).
  - 0 remotes → **multi-repo open-PR scan** (before falling back to asking): walk subdirectories of the
    current directory (depth 2, skipping `.git`/`node_modules`/hidden dirs) for other git roots, and
    collect each one's `github.com` remotes the same way. This is what makes invoking from a parent root
    with zero remotes of its own resolve without a manual pick every time, since the actual PR always
    lives in one of the nested repos. For every candidate repo found, run `gh pr list --repo O/R --state open
    --json number,title` (one call per repo; small N, fine to run sequentially).
    - No candidate repos found at all → ask for explicit `owner/repo` via `AskUserQuestion`, or stop.
    - Every candidate repo has 0 open PRs → report which repos were checked and that none have an open PR,
      then stop.
    - Exactly one candidate repo has ≥1 open PR → auto-use that repo, announcing *why* ("only repo among
      the `N` checked with an open PR") alongside the usual directory + remote + owner/repo announcement.
      Fall through to the PR-number resolution step below within that repo.
    - 2+ candidate repos each have ≥1 open PR → ask which repo, listing each with its open-PR count/titles
      so the choice is informed rather than a bare name pick.
  - Exactly 1 remote in the current directory itself → use automatically, announce directory + remote name
    + owner/repo (no scan needed — the common case when invoked from inside a sub-repo directly).
  - 2+ remotes in the current directory itself → ask which one.
  - User already named `owner/repo` explicitly → skip parsing and the scan, verify via `gh repo view` so a
    typo fails fast.
- PR number: explicit number → verify via `gh pr view`. No number → `gh pr list --state open`: 0 open →
  report and stop; 1 → use automatically; 2+ → ask which one (number/title/branch).

## Step-by-step flow

0. **[AUTO]** `gh auth status` first, unconditionally — stop before anything else if it fails,
   distinguishing "not logged in" from "gh not installed."
1. **[AUTO/ASK]** Resolve repo, then PR (above).
2. **[AUTO]** Pull full metadata in one call: `gh pr view N --repo O/R --json number,title,state,headRefName,headRefOid,baseRefName,url,isDraft,mergeable,mergeStateStatus,reviewDecision,commits,author` plus `gh pr diff N --name-only`. `headRefOid`, `commits`, `author`, and `reviewDecision` are needed by later steps — fetch them all here so nothing downstream has to re-fetch or assume.
3. **[AUTO check → conditional ASK]** If PR state is `MERGED`/`CLOSED`, report plainly and ask whether to
   still review for the record. If yes on a merged PR, skip step 4 (resume detection) and the
   merge-now-vs-hold question entirely — a merged PR can't be merged again.
4. **[AUTO check → conditional ASK] Resume detection.** Check `gh api --paginate repos/<O>/<R>/pulls/<N>/reviews`
   (`--paginate` matters — the endpoint pages at 30) for an existing review whose body starts with the
   `## Automated review (review-pr, ...)` marker (posted by this same skill in a prior invocation).
   - No such review → first-time run; proceed to step 5.
   - Found, `commit_id` matches current `headRefOid` (no new commits since) → report this plainly
     ("already has a review-pr review from `<date>`, verdict `<X>`, no new commits since"). Ask via
     `AskUserQuestion`: jump straight to the merge-now-vs-hold decision (default — this is the "held off,
     now ready to merge" case), or re-run the review anyway.
   - Found, `headRefOid` has moved on (or the old `commit_id` isn't in current history at all — e.g. a
     force-push) → report the old→new SHA change, default to a **follow-up pass** re-targeting the whole
     PR again (there's no scoped "commits since SHA X" grammar — see Notes), explicitly announced as a
     follow-up check, not indistinguishable from a first pass. Ask effort/scope, then continue normally.
5. **[ASK — one round-trip, first-time-review path only]**: effort level (low/medium/high/max); review
   scope (code-review only / security-review only / both).
6. **[Delegate, announced]** Invoke the built-in `code-review` and/or `security-review` skill per the scope
   answer, in **report-only mode** — never pass `--comment`/`--fix` (or any equivalent flag) to either.
   This skill's own step 10 CONFIRM is the *only* path allowed to post to GitHub or touch the working tree;
   a delegated skill posting or editing on its own initiative would be an unconfirmed, visible-to-others
   action hiding inside a step this design otherwise treats as safe.
7. **[AUTO]** Present findings as an explicit numbered list in response text (file:line + one-line
   description each) — never summarized prose under headers.
8. **[AUTO] Author-vs-viewer check, before deriving a verdict.** Compare the authenticated `gh` user
   (`gh api user --jq .login`) against the PR's `author.login` (from step 2). GitHub rejects
   `APPROVE`/`REQUEST_CHANGES` from a PR's own author (HTTP 422) — irrelevant on a third-party PR, but a
   hard failure on any repo where the user authors their own PRs (a normal case on some repos, not an
   error). If they match, the verdict below collapses to `comment` regardless of finding severity, stated
   explicitly ("posting as a comment, not request-changes/approve, since this PR is authored by the
   account being used to review it").
9. **[AUTO]** Derive a proposed verdict from the findings themselves — **unless step 8 already collapsed
   it to `comment`**: any high-confidence correctness/security finding → propose `request-changes`; only
   style/uncertain findings → propose `comment`; zero findings → propose `approve`.
10. **[CONFIRM — every time, no exceptions]** Show the exact review body text and verdict flag about to be
    sent. Offer two paths: post it now, or just display the body/verdict and stop without posting
    (rehearsal option). Stop for explicit confirmation before any `gh pr review` call, regardless of any
    prior session's approval — this is a visible-to-others action.
11. **[AUTO after confirmation]** Post via
    `gh pr review N --repo O/R --request-changes|--comment|--approve --body-file <scratchpad tmp file>` —
    the **only** posting mechanism; never attempt the classifier-blocked `gh api .../reviews` inline-comment
    route (see Notes). Body written to the template below. Immediately re-fetch
    (`gh pr view --json reviews`) to confirm the review actually landed rather than trusting a zero exit
    code alone.
12. **[AUTO]** Merge-status check (below), reported factually — **including this skill's own just-posted
    `reviewDecision`**, so a `CHANGES_REQUESTED` verdict is never silently absent from a "mergeable now"
    report.
13. **[ASK]** Present merge-now-vs-hold as an explicit question — never a recommendation the skill makes
    itself.
14. Branch: **merge now** → the merge sub-flow below; **hold** → delegate (announced) to `work-backlog`
    quick-capture mode with the note template below (if `work-backlog` isn't installed, just note this
    yourself in whatever tracking file your own workflow uses); **still deciding** → stay in conversation,
    re-ask this same question once resolved rather than letting further discussion substitute for answering
    it.

## Merge sub-flow ("merge now" branch)

Merging is a second, fully separate visible-to-others action from posting the review — its own checkpoint,
never inherited from the earlier one.

1. **[AUTO]** Pull `gh api repos/<O>/<R> --jq '{allow_squash_merge,allow_merge_commit,allow_rebase_merge,delete_branch_on_merge}'`
   plus re-check `gh pr view N --repo O/R --json commits,mergeStateStatus,mergeable`. Only offer merge
   methods the repo actually allows. Propose a strategy, never silently apply one:
   - Exactly 1 commit → propose `--squash`, but say plainly it still writes a new SHA and drops the
     original commit's trailers (including any mandated commit trailers your repo requires, e.g. a
     Co-Authored-By line) — not truly equivalent to a plain merge.
   - 2+ commits → propose `--squash` as the default, name `--merge` (preserves individual commits and
     their trailers) as the alternative.
2. **[ASK — one round-trip]**: merge method (only ones step 1 confirmed the repo allows, pre-selected per
   the proposal); whether to delete the source branch after merge, pre-selected from
   `delete_branch_on_merge` but always asked. Note explicitly: `--delete-branch` deletes **both** local and
   remote — the remote deletion is recoverable via GitHub's "Restore branch," the local one is
   reflog-only.
3. **[CONFIRM]** Check whether the PR has required status checks and whether they've all passed. If
   pending, warn explicitly: `gh pr merge` will **arm a persistent auto-merge instead of merging
   immediately** — ask whether to proceed on that basis or wait. Then show the exact command —
   `gh pr merge <N> --repo <O>/<R> --squash|--merge|--rebase [--delete-branch] --match-head-commit <headRefOid>`
   (the guard fails the merge rather than merging over a commit pushed during this confirmation
   round-trip) — offering the same rehearsal option as step 10. Stop for explicit confirmation.
4. **[AUTO after confirmation]** Execute, then **re-fetch**
   `gh pr view N --repo O/R --json state,merged,mergedAt,mergeCommit,autoMergeRequest` rather than trusting
   a zero exit code. `merged: true` → report success plainly, including the merge commit SHA.
   `merged: false` but `autoMergeRequest` now set → report plainly that auto-merge was **armed, not
   executed** — a different outcome than "merge now" implied — and ask whether that's acceptable or
   whether to disable it (`gh pr merge --disable-auto`).
5. **[AUTO]** If a matching `BACKLOG.md` entry exists for this PR, remind the user to close it out via
   `work-backlog` — a spoken reminder, not an automatic archive move.

## GitHub-posting body template

```
## Automated review (review-pr, <effort> effort<, + security-review>)

1. `path/to/file.ext:123` — <one-line finding>
2. `path/to/other.ext:45` — <one-line finding>
...
```
**Zero-findings (approve) case**: `--approve` accepts an empty body, but `--request-changes` does not — so
write one anyway even on approve, e.g. "## Automated review (review-pr, `<effort>` effort) — no findings;
see the diff reviewed at `<PR head SHA>`."

## Merge-status check (always both calls, always reported)

```
gh api repos/<owner>/<repo>/branches/<baseRefName>/protection
gh pr view <N> --repo <owner>/<repo> --json mergeStateStatus,mergeable,isDraft,reviewDecision
```
`mergeable` is a **string enum** (`MERGEABLE`/`CONFLICTING`/`UNKNOWN`), not a boolean — state it verbatim.
Cover all outcomes explicitly and factually, never as an implied recommendation:
- Protection call `404` → normal — no protection rule on this branch.
- Protection call `403 Upgrade to GitHub Pro` → private free-tier repo, protection unavailable on this plan.
- Protection call `403` for another reason → check the response body (often: authenticated user lacks
  admin rights) and report which 403 it actually was.
- Protection call `200` → state exactly what's required and whether the PR currently satisfies it.
- `mergeStateStatus: CLEAN` / `mergeable: MERGEABLE` → no conflicts, mergeable now.
- `mergeStateStatus: DIRTY`/`BLOCKED` / `mergeable: CONFLICTING` → state the actual value verbatim.
- `mergeStateStatus: BEHIND` → base has moved ahead; needs an update before merging.
- Either field `UNKNOWN` → GitHub is still computing this async — wait ~2s, re-check once; if still
  `UNKNOWN`, report that plainly rather than treating it as settled.
- `isDraft: true` → flagged separately — drafts typically can't merge regardless of the above.
- **`reviewDecision`** (`APPROVED`/`CHANGES_REQUESTED`/`REVIEW_REQUIRED`/absent) → always folded into the
  same report, even when `mergeStateStatus` says `CLEAN` — a `CHANGES_REQUESTED` review (including one
  this same skill just posted) must be named explicitly alongside "mergeable now."

## `work-backlog` handoff note (when the user pauses)

Literally invoke `work-backlog` quick-capture mode — never write `BACKLOG.md` directly. Note contents:
repo/PR identifier + URL; effort level and which pass(es) ran; whether the review already posted (verdict
used, pointer to the PR, not a duplicate findings copy); if not yet posted, the findings list itself; the
merge-status facts already gathered; where exactly the flow paused. If `work-backlog` isn't installed in
this repo, note the same information yourself in whatever tracking file your workflow uses instead.

## Notes

- **Known v1 limitation — no true "commits since SHA X" scoped review.** The built-in `code-review` skill's
  target grammar is diff/PR-number/branch/path, with no commit-range option — the resume-detection
  follow-up pass therefore re-runs against the whole PR again, just explicitly announced as a follow-up.
  A real scoped-diff review is a future improvement, not v1.
- **Known v1 limitation — the classifier-blocked `gh api .../reviews` POST path (inline per-line comments)
  is not retried automatically** if the underlying Bash permission rule is ever added later (e.g. via
  a settings/permissions-configuration skill) — this is a one-time interim call, not a permanent claim
  about `gh` or GitHub itself, worth revisiting if that permission rule changes. `GET` calls to the same API
  family are unaffected and already used throughout this skill (branch protection, resume detection).
- Edge cases handled above: no `gh` auth; PR already merged/closed; zero open PRs; no configured GitHub
  remote in the invoking directory (triggers the multi-repo scan of sibling git roots before falling back
  to asking); security-review-only run; a clean-PR approve path; insufficient permissions on the target
  repo (check actual `gh` exit status/output, don't assume success); multiple open PRs (ask, don't guess);
  multiple candidate repos each with an open PR (ask, don't guess); a repo that disables one or more merge
  methods; a force-pushed PR between runs.
