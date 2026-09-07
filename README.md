<p align="center">
  <img src="assets/phase-gate.svg" alt="Phase-Gate: a two-axis diagram. The work axis chains /backlog, /spec, /build, /verify, and /ship left to right, fed by an /initiate dispatcher and looping back from /ship to /backlog for the next item. A session axis below lists /handoff and /end-task, running alongside any phase." width="600">
</p>

# Phase-Gate

A working method for AI-assisted development **with Claude Code specifically** — this repo installs
Claude Code skills, agents, and hooks, and won't do anything for you on another tool. The idea is
simple: decide how much ceremony a change earns before you start it, then make the expensive parts
cheap by handing them to fresh-context subagents (separate Claude instances, each starting with a
clean slate and only the specific task at hand — used so a review can't just re-confirm the same
reasoning that produced the work) instead of doing everything inline. Read
[`docs/methodology.md`](docs/methodology.md) for the full argument. It's short, and the rest of this
repo only makes sense once you've read it.

Want to explain the idea itself — not the mechanics — to someone who isn't going to run these
commands, like a PM, a BA, QA, or an exec? [`docs/methodology-explainer.pdf`](docs/methodology-explainer.pdf)
(source: [`docs/methodology-explainer.html`](docs/methodology-explainer.html)) is a short,
plain-language version built for exactly that.

**Terms used throughout this README, if you're new to Claude Code:** a **skill** is a reusable prompt
Claude Code loads when you type a matching slash command; a **subagent** is a separate Claude
instance with its own context window, spun up for one task and given only what it needs (see above);
a Claude Code **hook** is a shell command Claude Code itself runs automatically on some event (a
*different* thing from a **git hook** like `.githooks/pre-push`, which `git` runs — this repo has
both kinds, and it's always stated which); a **statusline** is the one-line status bar Claude Code
can show at the bottom of a session. Platform-level terms this repo uses but doesn't define —
**fresh context**/**turn**, the **`Workflow` tool**, **Plan Mode** — are Claude Code's own features;
see Claude Code's own docs or `/config` if any of those are unfamiliar.

This repo ships two things, and either one works without the other:

- **`process/`**: the complete method. Thirteen skills, two subagents, a workflow script, and the
  hooks that enforce it — see [What's in each shelf](#whats-in-each-shelf) below for what each one
  actually does. Opinionated software: it assumes a backlog file, a tier discipline, and a handful
  of standing conventions, and its pieces reference each other. A design doc feeds an execution
  plan, which feeds a work queue. A QA gate delegates to a review agent. Adopt it whole and you get
  a consistent process instead of one that only happens when someone remembers it.
- **`standalone/`**: a pick-and-choose catalog. Seven components (four hooks, a statusline, two
  skills), each working completely on its own. Zero adaptation, zero cross-references. Take exactly
  the piece you want and skip the rest.

Neither one is the "real" version. If you're unsure which to start with: trying one `standalone/`
hook costs nothing and asks for no commitment — see [What's in each shelf](#whats-in-each-shelf) for
what's there. The full method sits waiting for whenever you want it.

## What a session actually looks like

Say you ask for a new settings page. With `process/` installed, here's the shape of what actually
happens, not just the architecture:

1. Before writing anything, the agent states the size out loud — *"this touches three files and adds
   new UI with no existing pattern to mirror, so Tier 2"* — and writes a short design doc.
2. Saving that doc automatically fires a design review: a different model, in a fresh context with no
   memory of writing the doc, reads it cold and reports back findings as a numbered list — cited by
   file and line, not paraphrased.
3. You get those findings directly, in the conversation, before anything is built — not filed
   silently into a doc for you to go check.
4. The agent builds against the reviewed design, then hands off to an independent QA pass: another
   fresh-context read, checking the actual result against the design doc — not the same context
   grading its own work.
5. Only after that QA pass reports clean does the change get committed, with the review's outcome
   stated plainly either way.

Nothing here is hidden or automatic in the sense of "you don't see it happen" — every review and gate
announces itself explicitly in the conversation. What's automatic is that you never have to remember
to ask for one.

## Requirements

This is a capability check — what your Claude Code setup needs to be able to do — not a claim about
which subscription plan you need. Claude Code's own plans and feature availability shift independently
of this document, so verify directly instead of trusting a name here.

- **Claude Code CLI**, with skills enabled. That's it for `standalone/` components individually.
- **To run the installer** (below): **Sonnet-class reasoning or above** — Claude's mid-tier model
  (Sonnet) or a stronger one (Opus), not its fastest/cheapest one (Haiku). The grounded, multi-file,
  citation-checked reading it does is a materially higher bar than casually skimming file contents.
- **To use `implement-queue`** (part of `process/`): the `Workflow` tool with worktree-isolation
  support (a git feature: two working directories against one repo at once, used here so parallel
  agents don't step on each other's files). Check via `/config` that Dynamic workflows is on. There's
  no reduced or sequential fallback. This one's a hard requirement, stated up front instead of
  discovered mid-run.
- **To use `review-pr`** (part of `process/`): `gh` (the GitHub CLI), installed and authenticated,
  plus the `code-review`/`security-review` skills that ship with Claude Code itself (assumed
  present, not installed by this repo).
- **`git`**, obviously.

**Cost.** None of this is free relative to a plain conversation. Every Tier 1-3 change spawns at
least one extra fresh-context subagent pass (a design review, a QA pass, or both), and Tier 1 can
switch the whole session to a stronger, more expensive model for the design pass specifically. There's
no built-in spend cap — if you're budget-conscious, watch your usage manually, especially in the
first few sessions after installing, before you have a feel for the actual overhead on your own kind
of work.

## What installing actually does

**The installer is itself a Claude Code skill — an LLM reading your repo and deciding what to write,
not a plain script.** A separate, mandatory, deterministic checker re-verifies its citations
afterward (see Install, below) precisely because the thing proposing changes is a model, not code.

There's no session-only or ad-hoc mode. Running the installer in `apply` mode writes real files
into your repo: skills, agents, hook scripts, a `.claude/settings.json`. Those persist across every
future session.

**One consequence worth stating plainly, not as an aside: installing `process/`'s `backlog` skill
grants a standing authorization for the agent to commit locally without asking first**, at three
specific triggers (see `docs/methodology.md` §6 — pushing anywhere still always asks first,
regardless). This is a deliberate override of Claude Code's normal "confirm before committing"
default, not a side effect you'd otherwise miss.

Want to see what would apply without committing to any of it — including that authorization? Just
run `/phase-gate-install /path/to/phase-gate` and answer **recommend-only** when it asks which mode
you want (see Install, below) — it writes two small JSON files under
`.claude/phase-gate-install/` recording what it would propose, and nothing else. Want to try
exactly one `standalone/` piece with zero install ceremony at all? Read that piece's file directly
instead of running the installer.

## Install

```
git clone <this-repo's-clone-url> /path/to/phase-gate
```

Then, **in the repo you actually want phase-gate installed into**:

```
mkdir -p .claude/skills && cp -r /path/to/phase-gate/installer/phase-gate-install .claude/skills/
```

(or the Windows equivalent: make sure `.claude\skills\` exists first, then copy the whole folder, not
the file alone — `cp -r` silently does the wrong thing, nesting rather than creating, if the
destination folder doesn't already exist). Then, **from inside a Claude Code session, with the repo
you just copied into as your working directory**, run:

```
/phase-gate-install /path/to/phase-gate
```

This starts the installer skill (`installer/phase-gate-install/SKILL.md`) — it reads your repo,
proposes a grounded, citation-backed plan of what applies to you, and writes nothing until you
confirm. It will ask which mode you want, **`recommend-only`** (report only, writes nothing but its
own plan file — see "What installing actually does" above) or **`apply`** (real writes, one
before/after diff at a time, only after you confirm each). Answer `recommend-only` for a completely
safe first look with zero commitment. See the skill's own file for the full step-by-step: provenance
check, four risk classes, a mandatory deterministic checker. It's the one file in this repository
that reads untrusted input and writes to your machine, and it holds itself to that standard.

**"This export"** (used in a few places in this repo's own docs) means this repository as
distributed to you — generalized from the author's own working setup, not designed in the abstract.
`docs/methodology.md` §9 in particular is closer to hard-won operational habits than universal law;
read it that way rather than assuming every line is load-bearing for you specifically.

Starting from scratch? If the target directory isn't a git repo yet, the installer asks for
confirmation and your intended default branch name, then initializes the repo via `git init -b <name>`.
The normal case — installing into an existing repo — works as described above.

## What's in each shelf

This repo organizes everything into two **shelves** — `process/` (the full method, cross-referencing
skills) and `standalone/` (independent pieces) — pick whichever matches how much you want to adopt at
once.

**`process/`** — thirteen skills, each a slash command:

| Skill | What it does |
|---|---|
| `backlog` | Track open work items; list, add to, or pick one up |
| `spec` | Write a short design doc before implementing anything non-trivial |
| `initiate` | At session start, rank what's actionable across the project and name the next command |
| `adopt` | One-time inventory pass for adding this method onto a project with existing code but no history yet |
| `build` | Implement an approved design doc |
| `execution-gate` | Decide, task by task, how an approved design's work should actually run — direct, delegated, forked, or blocked on you |
| `verify` | Independent QA pass on a finished implementation, before it ships |
| `ship` | Publish (if there's a deploy target) and archive a finished work item |
| `implement-queue` | Build several already-approved designs in parallel, in isolated git worktrees |
| `consolidate-docs` | Periodic cleanup pass keeping your rules doc lean |
| `end-task` | Session-close checklist — commit, sync docs, or write a handoff, depending what's actually unfinished |
| `handoff` | Write a briefing so a fresh session can pick up in-progress work with no shared memory |
| `review-pr` | Independently review a GitHub pull request and post the findings |

Plus two subagents every gate above delegates to — `code-reviewer` (the independent QA pass) and
`docs-writer` (mechanical documentation sync, once decisions are already made) — one workflow script,
and the hooks that nudge the docs-sync/mistakes-log habits `docs/methodology.md` describes.
(`wrap-up-session`/`commit` still exist as short redirect stubs pointing at `end-task`, for anyone
following an older reference to them — treat them as aliases, not separate skills.) Read
[`docs/WORKFLOW.md`](docs/WORKFLOW.md) to see how the pieces chain into two axes, and
[`docs/PORTING.md`](docs/PORTING.md) for every value you can configure: file names, branch, test
command, and more, all detected or asked at install time and never hardcoded.

**`standalone/`**: four hooks (`block-dangerous-commands`: hard-blocks a short list of
catastrophic Bash commands regardless of permission mode; `hooks-health-check`: reports, never
blocks, when your git-hooks configuration has drifted; `context-usage-nudge`: fires as a session's
context usage climbs, nudging you to write yourself a handoff or continuation note before it runs
out; `update-notification`: passively checks whether phase-gate has new commits upstream since install
— checked on a throttle rather than every session, and fails silently rather than blocking anything if
the check itself can't run — never fetches or applies anything itself), a statusline (context-window
usage, session cost, session duration), and two skills
(`ai-check`: forensic AI-text detection; `humanize`: rewrites text to read less like an AI wrote
it). Each ships in its own folder with its own README and settings fragment. Copy exactly the one
you want.

**`ai-check` and `humanize` ship under their own `LICENSE`, not this repo's.** They were adopted
from elsewhere, not authored here. See each folder's own README and LICENSE for attribution. Every
other component in this repo is under the root [`LICENSE`](LICENSE) (MIT).

## Updating

If you installed the `update-notification` component (`standalone/`, on by default in `process/`
installs), you'll get a passive nudge in Claude Code when a new commit lands upstream — checked on a
throttle (not every session), and it fails silently rather than blocking anything if the check itself
can't run. It never fetches or applies anything itself. See [`CHANGELOG.md`](CHANGELOG.md) for what
changed, tagged as GitHub releases (this project is still pre-1.0, tagged `0.x.y` — `v1.0.0` is
reserved for the first release actually considered stable). To actually pick up an update:

1. Pull the phase-gate clone (or re-clone it).
2. Run `/phase-gate-install /path/to/phase-gate` in your repo. Before applying anything, the installer
   checks whether this clone's current commit differs from the `source_commit` recorded in your prior
   **receipt** (`.claude/phase-gate-install/receipt.json` — the installer's own record of exactly what
   it wrote last time, if it's run here before). If the installer's own file needs updating, this run
   refreshes only that file and stops — you'll see an instruction to re-invoke. Otherwise — the common
   case — all proposed updates apply in this single run. Review the grounded plan either way.
3. If step 2 refreshed the installer only, run `/phase-gate-install /path/to/phase-gate` again to
   apply everything else. Nothing you've locally edited gets silently overwritten.

No update-check component installed, or want to check by hand? Just `git log`/`git pull` the clone
and compare against what you last installed — there's no separate update channel.

## Uninstalling

There's no automated uninstall script — everything installed is plain files plus merged entries in
`.claude/settings.json`, so removing it is a manual but bounded job. `.claude/phase-gate-install/receipt.json`
is the exact, authoritative list of everything ever written by this installer, by path — start there,
not from memory:

1. Delete every path listed in the receipt's `components`/`repo_files` arrays (skills under
   `.claude/skills/`, agents under `.claude/agents/`, hook scripts under `.githooks/`, and any
   repo-root docs like `docs/methodology.md` you don't want to keep).
2. Remove the corresponding entries from `.claude/settings.json` — the installer merges these in
   rather than tagging them, so there's no automatic way to tell which lines came from phase-gate;
   compare against `.claude/phase-gate-install/plan.json`'s Class 3 rows (or the last diff you
   confirmed at install time) to identify them.
3. If you set `core.hooksPath` for this install and don't want git hooks anymore, unset it
   (`git config --unset core.hooksPath`).

Removing `standalone/` pieces you copied in by hand is simpler — just delete the specific file(s) you
copied and, if you added a settings fragment, remove that entry from `.claude/settings.json`.

## Credits

The `standalone/hooks/` idea, small single-purpose Claude Code hooks distributed individually
instead of one monolithic config, comes from
[`claude-code-templates`](https://github.com/davila7/claude-code-templates) (MIT, Daniel Ávila).
Nothing here is copied verbatim from that project. This repo's hook *implementations* are its own.
