<p align="center">
  <img src="assets/phase-gate.svg" alt="Phase-Gate: a circular loop of Backlog Triage, Design Gate, Execution Router, Parallel Queue, and Closeout" width="480">
</p>

# Phase-Gate

A working method for AI-assisted development, built around one idea: **decide how much ceremony a
change earns before you start it**, then make the expensive parts cheap by delegating them to fresh-context
subagents instead of doing them inline. Read [`docs/methodology.md`](docs/methodology.md) for the full
argument — it's short, and everything else in this repo only makes sense once you've read it.

This repo ships two things, and you can take either one without the other:

- **`process/`** — the complete method: nine skills, two subagents, a workflow script, and the hooks that
  enforce it. This is opinionated software — it assumes a backlog file, a tier discipline, and a few
  standing conventions, and its pieces reference each other (a design doc feeds an execution plan, which
  feeds a work queue; a QA gate delegates to a review agent). Adopt it whole, and you get a consistent
  process instead of one that only happens when someone remembers it.
- **`standalone/`** — a pick-and-choose catalog. Six components (three hooks, a statusline, two skills)
  that work completely on their own, zero adaptation, zero cross-references. Take exactly the piece you
  want and ignore the rest.

Neither is the "real" one. Most people's honest first move is raiding `standalone/` for a hook or two; the
full method is there when you want it.

## Requirements

This is a capability check, not a plan-tier claim — Claude Code's own plans and feature availability
change independently of this document, so verify directly rather than trusting a name here.

- **Claude Code CLI**, with skills enabled. That's it for `standalone/` components individually.
- **To run the installer** (below): Sonnet-class reasoning or above. The grounded, multi-file,
  citation-checked reading it does is a materially higher bar than casually skimming file contents.
- **To use `implement-queue`** (part of `process/`): the `Workflow` tool with worktree-isolation support.
  Check via `/config` that Dynamic workflows is on. There is no reduced/sequential fallback — this is a
  hard requirement for that one skill, stated up front rather than discovered mid-run.
- **To use `review-pr`** (part of `process/`): `gh` (the GitHub CLI), installed and authenticated, plus the
  `code-review`/`security-review` skills that ship with Claude Code itself (assumed present, not installed
  by this repo).
- **`git`**, obviously.

## Install

```
git clone <this-repo's-clone-url> /path/to/phase-gate
```

Then, **in the repo you actually want phase-gate installed into**:

```
cp -r /path/to/phase-gate/installer/phase-gate-install .claude/skills/
```

(or the Windows equivalent — copy the folder, not just the file). Then run:

```
/phase-gate-install /path/to/phase-gate
```

The installer skill (`installer/phase-gate-install/SKILL.md`) reads your repo, proposes a grounded,
citation-backed plan of what applies to you, and writes nothing until you confirm — see the skill's own
file for the full step-by-step (provenance check, two modes, four risk classes, a mandatory deterministic
checker). It is the one file in this export that reads untrusted input and writes to your machine, and it
holds itself to that standard explicitly.

## What's in each shelf

**`process/`** — `work-backlog`, `design-gate`, `execution-gate`, `implement-queue`, `consolidate-docs`,
`wrap-up-session`, `commit`, `handoff`, `review-pr` (skills); `code-reviewer`, `docs-writer` (subagents);
one workflow script; the hooks that nudge the docs-sync/mistakes-log habits `docs/methodology.md`
describes. Read [`docs/WORKFLOW.md`](docs/WORKFLOW.md) for how the pieces chain into one pipeline, and
[`docs/PORTING.md`](docs/PORTING.md) for every value you can configure (file names, branch, test command,
and more — all detected or asked at install time, never hardcoded).

**`standalone/`** — three hooks (`block-dangerous-commands`: hard-blocks a short list of catastrophic Bash
commands regardless of permission mode; `hooks-health-check`: reports, never blocks, when your git-hooks
configuration has drifted; `context-usage-nudge`: fires as a session's context usage climbs, nudging you to write
yourself a handoff/continuation note before it runs out), a statusline (context-window usage, session cost,
session duration), and two skills (`ai-check`: forensic AI-text detection; `humanize`: rewrites text to
read less like an AI wrote it). Each ships in its own folder with its own README and settings fragment —
copy exactly the one you want.

**`ai-check` and `humanize` ship under their own `LICENSE`, not this repo's.** They were adopted from
elsewhere, not authored here — see each folder's own README and LICENSE for attribution. Every other
component in this repo is under the root [`LICENSE`](LICENSE) (MIT).

## Credits

The `standalone/hooks/` idea — small, single-purpose Claude Code hooks distributed individually rather
than as one monolithic config — is adapted from
[`claude-code-templates`](https://github.com/davila7/claude-code-templates) (MIT, Daniel Ávila). Nothing
here is copied verbatim from that project; this repo's hook *implementations* are its own.
