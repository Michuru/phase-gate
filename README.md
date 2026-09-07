<p align="center">
  <img src="assets/phase-gate.svg" alt="Phase-Gate: a two-axis diagram. The work axis chains /backlog, /spec, /build, /verify, and /ship left to right, fed by an /initiate dispatcher and looping back from /ship to /backlog for the next item. A session axis below lists /handoff and /end-task, running alongside any phase." width="600">
</p>

# Phase-Gate

A working method for AI-assisted development. The idea is simple: decide how much ceremony a change
earns before you start it, then make the expensive parts cheap by handing them to fresh-context
subagents instead of doing everything inline. Read [`docs/methodology.md`](docs/methodology.md) for
the full argument. It's short, and the rest of this repo only makes sense once you've read it.

Want to explain the idea itself — not the mechanics — to someone who isn't going to run these
commands, like a PM, a BA, QA, or an exec? [`docs/methodology-explainer.pdf`](docs/methodology-explainer.pdf)
(source: [`docs/methodology-explainer.html`](docs/methodology-explainer.html)) is a short,
plain-language version built for exactly that.

This repo ships two things, and either one works without the other:

- **`process/`**: the complete method. Fifteen skills, two subagents, a workflow script, and the hooks
  that enforce it. Opinionated software: it assumes a backlog file, a tier discipline, and a handful
  of standing conventions, and its pieces reference each other. A design doc feeds an execution
  plan, which feeds a work queue. A QA gate delegates to a review agent. Adopt it whole and you get
  a consistent process instead of one that only happens when someone remembers it.
- **`standalone/`**: a pick-and-choose catalog. Seven components (four hooks, a statusline, two
  skills), each working completely on its own. Zero adaptation, zero cross-references. Take exactly
  the piece you want and skip the rest.

Neither one is the "real" version. Most people's honest first move is raiding `standalone/` for a
hook or two. The full method sits there waiting when you want it.

## Requirements

This is a capability check, not a plan-tier claim. Claude Code's own plans and feature availability
shift independently of this document, so verify directly instead of trusting a name here.

- **Claude Code CLI**, with skills enabled. That's it for `standalone/` components individually.
- **To run the installer** (below): Sonnet-class reasoning or above. The grounded, multi-file,
  citation-checked reading it does is a materially higher bar than casually skimming file contents.
- **To use `implement-queue`** (part of `process/`): the `Workflow` tool with worktree-isolation
  support. Check via `/config` that Dynamic workflows is on. There's no reduced or sequential
  fallback. This one's a hard requirement, stated up front instead of discovered mid-run.
- **To use `review-pr`** (part of `process/`): `gh` (the GitHub CLI), installed and authenticated,
  plus the `code-review`/`security-review` skills that ship with Claude Code itself (assumed
  present, not installed by this repo).
- **`git`**, obviously.

## What installing actually does

There's no session-only or ad-hoc mode. Running the installer in `apply` mode writes real files
into your repo: skills, agents, hook scripts, a `.claude/settings.json`. Those persist across every
future session, including a standing local auto-commit authorization
(`backlog`/`docs/methodology.md` §6) once installed. Want to see what would apply without
committing to any of it? `recommend-only` is the actual lightweight option. It writes two small
JSON files under `.claude/phase-gate-install/` and nothing else (see Install, below). Want to try
exactly one `standalone/` piece with zero install ceremony? Read that piece's file directly instead
of running the installer.

## Install

```
git clone <this-repo's-clone-url> /path/to/phase-gate
```

Then, **in the repo you actually want phase-gate installed into**:

```
cp -r /path/to/phase-gate/installer/phase-gate-install .claude/skills/
```

(or the Windows equivalent: copy the whole folder, not the file alone). Then run:

```
/phase-gate-install /path/to/phase-gate
```

The installer skill (`installer/phase-gate-install/SKILL.md`) reads your repo, proposes a grounded,
citation-backed plan of what applies to you, and writes nothing until you confirm. See the skill's
own file for the full step-by-step: provenance check, two modes, four risk classes, a mandatory
deterministic checker. It's the one file in this export that reads untrusted input and writes to
your machine, and it holds itself to that standard.

Starting from scratch? If the target directory isn't a git repo yet, the installer asks for
confirmation and your intended default branch name, then initializes the repo via `git init -b <name>`.
The normal case — installing into an existing repo — works as described above.

## What's in each shelf

**`process/`**: `backlog`, `spec`, `initiate`, `adopt`, `build`, `execution-gate`, `verify`, `ship`,
`implement-queue`, `consolidate-docs`, `end-task`, `wrap-up-session`, `commit`, `handoff`, and
`review-pr` as skills (`wrap-up-session`/`commit` are now 5-line redirect stubs pointing at
`end-task`, kept for one cycle for backward compatibility), plus `code-reviewer` and `docs-writer`
as subagents, one workflow script, and the hooks that
nudge the docs-sync/mistakes-log habits `docs/methodology.md` describes. Read
[`docs/WORKFLOW.md`](docs/WORKFLOW.md) to see how the pieces chain into two axes, and
[`docs/PORTING.md`](docs/PORTING.md) for every value you can configure: file names, branch, test
command, and more, all detected or asked at install time and never hardcoded.

**`standalone/`**: four hooks (`block-dangerous-commands`: hard-blocks a short list of
catastrophic Bash commands regardless of permission mode; `hooks-health-check`: reports, never
blocks, when your git-hooks configuration has drifted; `context-usage-nudge`: fires as a session's
context usage climbs, nudging you to write yourself a handoff or continuation note before it runs
out; `update-notification`: passively checks whether phase-gate has new commits upstream since install, throttled and fail-open, never fetches or applies anything itself), a statusline (context-window usage, session cost, session duration), and two skills
(`ai-check`: forensic AI-text detection; `humanize`: rewrites text to read less like an AI wrote
it). Each ships in its own folder with its own README and settings fragment. Copy exactly the one
you want.

**`ai-check` and `humanize` ship under their own `LICENSE`, not this repo's.** They were adopted
from elsewhere, not authored here. See each folder's own README and LICENSE for attribution. Every
other component in this repo is under the root [`LICENSE`](LICENSE) (MIT).

## Updating

If you installed the `update-notification` component (`standalone/`, on by default in `process/`
installs), you'll get a passive nudge in Claude Code when a new commit lands upstream — it never
fetches or applies anything itself. See [`CHANGELOG.md`](CHANGELOG.md) for what changed, tagged as
GitHub releases (this project is still pre-1.0, tagged `0.x.y` — `v1.0.0` is reserved for the first
release actually considered stable). To actually pick up an update:

1. Pull the phase-gate clone (or re-clone it).
2. Run `/phase-gate-install /path/to/phase-gate` in your repo. Before applying anything, the installer
   checks whether this clone's current commit differs from your prior receipt's recorded `source_commit`
   (if one exists). If the installer's own file needs updating, this run refreshes only that file and
   stops — you'll see an instruction to re-invoke. Otherwise — the common case — all proposed updates
   apply in this single run. Review the grounded plan either way.
3. If step 2 refreshed the installer only, run `/phase-gate-install /path/to/phase-gate` again to
   apply everything else. Nothing you've locally edited gets silently overwritten.

No update-check component installed, or want to check by hand? Just `git log`/`git pull` the clone
and compare against what you last installed — there's no separate update channel.

## Credits

The `standalone/hooks/` idea, small single-purpose Claude Code hooks distributed individually
instead of one monolithic config, comes from
[`claude-code-templates`](https://github.com/davila7/claude-code-templates) (MIT, Daniel Ávila).
Nothing here is copied verbatim from that project. This repo's hook *implementations* are its own.
