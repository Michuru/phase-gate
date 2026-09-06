---
name: periodic-audit
description: Runs the coverage-gap and structural-recurrence audit passes for one or more registered tools, on a threshold the audit-threshold-check hook already flagged as due. Use when that hook nudges (once out of calibration mode), or when the user explicitly asks to run a periodic/recurring code audit on a specific tool.
---

# periodic-audit

Companion hook and full schema reference: `standalone/hooks/periodic-audit-threshold-check/README.md`
(the hook that decides *whether* a pass is due; this skill is the runbook for actually running one).
If you kept your own design doc for this feature, read it before changing anything here — this file
is the runbook, that doc is the reasoning.

**Two independently-gated passes, each reports "not applicable: `<reason>`" rather than silently
skipping:**
- **Coverage-gap scan** — only applicable if the tool's `audit-config.json` entry declares a
  `regression_suite`.
- **Structural re-audit** — only applicable if `.claude/audit-ledger/<tool>.json` has at least one
  entry.

## Step 1: Read the registry

Read `<repo>/.claude/audit-config.json` for whichever repo/tool this run targets (named directly by
the user, or by the threshold hook's nudge, or — if invoked with no target — every repo's registry,
same as the hook checks). A repo with no `audit-config.json` at all has nothing to run; say so and
stop for that repo.

## Step 2: Check both gates per tool

For each tool in scope:
- Coverage-gap gate: `regression_suite` is non-null.
- Structural gate: read `.claude/audit-ledger/<tool>.json` — at least one entry in `entries[]`.

Report "not applicable: `<reason>`" for any gate that doesn't clear, and move on — this is an
honest, expected outcome for a tool you haven't fully seeded yet, not a failure.

## Step 3: Announce model + cost, then spawn

**First invocation of each pass ever, for this repo**: confirm the model via `AskUserQuestion`
rather than assuming — coverage-gap defaults to a cheap model (the same tier your docs-sync
delegation uses), structural defaults to your own review-model rule: the most different model
available from whichever model wrote most of the code being audited (the same "most different
model available" principle your design-review gate applies to a design doc, applied here to code
authorship instead — check commit `Co-Authored-By` trailers if you track them, else ask). **Every
invocation after the first**: just state the cost plainly before spawning (e.g. "this spawns one
Haiku coverage-gap pass and one Opus structural pass") — don't re-ask.

Spawn via `Agent`, `subagent_type: periodic-audit-coverage` or `subagent_type: periodic-audit-structural`,
with a `model` override matching the confirmed/stated choice above. Prompt each with exactly what
its own agent-definition file's "Before you start" section says it needs (file paths, function
names, the ledger's current entries) — don't make it re-derive what registry/ledger reading already
gave you.

**Deterministic pre-pass for coverage-gap, before spawning**: where the tool's regression suite
exposes a runtime assertion-collection function, compute the set-difference yourself (verdict
literals the flagged file can produce, minus assertion labels the suite actually checks) and hand
that diff to the coverage-gap agent as input, rather than leaving it to derive unaided from a cold
read. This is required, not optional — it's cheap, deterministic, and mitigates a cheap model's
fabrication risk on an otherwise-ungated task.

## Step 4: Relay findings

- **Clean** (both gates cleared, no findings): delegate a one-line record to your docs-sync agent,
  citing the exact date, the exact commit SHA this check ran against, and which pass(es) ran clean —
  supply these facts directly in the delegation prompt, never leave it to invent them.
- **Real finding** (either pass reports something): the main session decides fix-now vs. a
  backlog quick-capture — **ask the user, don't assume either way.** A structural finding marked
  `affected-pending` in the ledger is a real open bug; treat it with the same weight as any other
  backlog-worthy finding.

## Step 5: Update ledger + state

- For any structural-pass finding, write the function's new status (`clean` or `affected-pending`)
  into `.claude/audit-ledger/<tool>.json` directly — this is prose-free structured data, a normal
  edit, not routed through `audit_state.py` (that module owns only `audit-thresholds.json`, the
  threshold/bootstrap state, never the ledger).
- Write the run's completion back via `audit_state.py`'s CLI **only** —
  `python .claude/hooks/audit_state.py set <repo> <main_file> <pass> last_audited_commit <sha>` —
  never a free-hand edit on `audit-thresholds.json` itself, so the lock/atomic-write path is never
  bypassed.
- **After a real structural-pass run specifically, also record the ledger's new hash**:
  `python .claude/hooks/audit_state.py set <repo> <main_file> structural ledger_hash <sha256-of-the-ledger-file-you-just-edited>`.
  **This is the only thing allowed to clear a fired `ledger-growth` trigger** — the threshold hook
  (read-only) deliberately never overwrites a mismatched hash itself. Skipping this step leaves the
  hook nudging on every future session even after you've actually addressed the finding.
- Narrow commit: the ledger file, the `NOTES.md` pointer (if this is the first run and it doesn't
  exist yet), and whatever backlog/design-doc change resulted from Step 4 — never the state file
  itself (it's machine-generated and gitignored).

## Notes

- Never reuse a generic diff-scoped code-review agent for either pass — a structural re-audit needs
  a fresh, whole-function read, the opposite of what a diff-scoped default gives you.
- The threshold hook ships in calibration mode (logs what would fire, never nudges) until a real
  calibration period confirms the default commit threshold of 5 is sane for your own repo's commit
  cadence — check `.claude/state/audit-calibration-log.jsonl` directly if you want to see what it's
  been finding, rather than waiting for a live nudge.
- Local-model fit: not applicable for either pass — both are open-ended judgment with no
  deterministic gate on their own (the coverage-gap pass's deterministic pre-pass narrows its input,
  but the final judgment is still the model's).
