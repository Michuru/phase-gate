# Porting: every adopter-side variable

This is the human-readable twin of [`installer/variables.json`](../installer/variables.json). That file
is what the installer and `verify_citations.py` actually read. This one explains what each value means
and which ones will bite you if you get them wrong.

**You do not have to read this before installing.** The installer walks these with you and detects what
it can. Read it when you want to change something afterwards, or when something isn't behaving the way
the rulebook says it should.

---

## The short version

Seventeen variables, in four kinds:

| Kind | Meaning | What happens if you ignore it |
|---|---|---|
| **default** | Works out of the box | Nothing. Change only if your repo uses a different name |
| **detected** | Determined by running a command at install time | The installer fills it. **Never hardcode one.** |
| **required** | No sensible default exists | The dependent feature degrades, visibly |
| **optional** | Safe to leave empty | The dependent feature turns itself off |

---

## Defaults: file and section names

These are plain find-and-replace substitutions. If your repo already uses different names, set them and
the installer rewrites every reference across the skills, the agents, and `methodology.md`.

| Variable | Default | What it is |
|---|---|---|
| `rules_doc` | `CLAUDE.md` | Your always-loaded rules document. Every skill cites it. |
| `backlog_file` | `BACKLOG.md` | Open and actionable items only. |
| `archive_file` | `BACKLOG_ARCHIVE.md` | Resolved history with citations. Never read by default. |
| `mistakes_file` | `MISTAKES.md` | Process mistakes: how work was done wrongly, not what's broken in the code. |
| `design_docs_dir` | `Design Docs/` | Where `spec` saves design documents. |
| `notes_file_pattern` | `{tool}.NOTES.md` | Companion notes naming. `{tool}` is replaced with the component name. |
| `checklist_section` | `Ready to implement` | The backlog heading `implement-queue` reads as its work queue. |

Two notes:

- **`design_docs_dir` contains a space by default.** That's fine, but it means every shell command
  referencing it must keep it quoted. If you'd rather not think about that, `design-docs/` is a
  reasonable change.
- **`notes_file_pattern` supports a second shape.** If you prefer notes living inside each component's
  own folder rather than beside it, use `{tool}/NOTES.md`.

---

## Detected: never write these by hand

### `default_branch`

**Do not hardcode this.** `main` and `master` are both common, and getting it wrong doesn't error. It
silently targets a branch that doesn't exist, which surfaces much later as a confusing failure in
whatever step first tried to use it.

Detection, in order:

```sh
git symbolic-ref --short refs/remotes/origin/HEAD    # outputs origin/<branch> — strip the origin/ prefix
git branch --show-current                            # fallback
```

Two ways the preferred command fails, both worth recognizing:

- **No remote configured.** Nothing to ask. Falls through to the fallback.
- **`origin/HEAD` was never set.** Common in a clone made with `--single-branch`, and in some CI
  checkouts. Fix with `git remote set-head origin --auto`.

The fallback has a real caveat: `git branch --show-current` reports whatever is **currently checked
out**, which is only the default branch if that's what happens to be checked out at install time. The
installer confirms rather than assuming.

### `python_cmd`

Which interpreter the hook scripts use.

```sh
python3 -c "print(1)"    # preferred
python  -c "print(1)"    # fallback
```

**Test that it runs, exactly as shown above. Don't use `command -v python3`.** On Windows, `python3` is
frequently a Microsoft Store stub that resolves perfectly well on `PATH` and then fails the moment it's
executed. A resolve-only check therefore selects a broken interpreter and reports success, and the
failure shows up later inside a hook where it's much harder to attribute. `python` is the working
interpreter on most Windows installs.

---

## Required: no default is provided on purpose

### `test_command`

How to run your test suite, cited by the `code-reviewer` agent so it can actually re-run tests rather
than reasoning about whether they'd pass.

There's deliberately no default. A wrong test command doesn't fail loudly. It produces a review that
silently never tested anything and then reports clean, which is worse than no review at all: it carries
the authority of one.

Examples: `npm test` · `pytest -q` · `cargo test` · `go test ./...`

---

## Optional: empty is a valid answer

### `lint_command`

The linter for `.githooks/pre-commit`. **Empty by default, which disables the lint step entirely.** The
hook ships inert until you configure it.

One mechanical detail that will catch you out: the hook lints your *staged* content by materializing it
into a scratch directory and running from there, so **a bare relative path to a linter binary will not
resolve.** Use `$REPO_ROOT`, which the hook sets for you before evaluating your command:

```sh
LINT_COMMAND="$REPO_ROOT/node_modules/.bin/eslint --config $REPO_ROOT/eslint.config.js"
LINT_COMMAND="ruff check"
LINT_COMMAND="$REPO_ROOT/.venv/bin/flake8"
```

The hook is structurally warn-only: a missing linter, a failing linter, or a broken scratch directory
all report and then exit zero. It can never block a commit. That's deliberate. A hook that blocks every
commit because of an infrastructure problem gets disabled wholesale, and that also disables the
`pre-push` secret guard that genuinely matters.

### `flagged_surfaces`

Specific functions, files, or modules in *your* codebase with a documented history of subtle bugs. A
change that would otherwise be Tier 4 gets the full QA gate if it touches one. See
[methodology.md §5](methodology.md).

**Ships empty, necessarily.** It's a property of your code, not of this methodology. Grow it the way
it's meant to be grown:

> When a bug turns out to have been subtle, and it was in the same place as a previous subtle bug, add
> that place to the list.

**Resist populating it speculatively.** A list of twenty surfaces escalates everything and therefore
escalates nothing. Its whole value is being short enough to mean something.

Examples: `src/pricing/calculate.ts:applyDiscount` · `lib/parser.py:parse_header`

### `local_delegate`

Enables the [local-delegate component](../process/local-delegate/README.md)'s free local-model draft
before `/build` spends a turn on an eligible task. Unlike the other variables in this section, it's
**read live at call time**, not substituted into any file — the runner script reads it straight from
your resolved `.claude/phase-gate-install/variables.json`.

**Ships as an empty object, `{}`, and is not prompted at install.** With nothing configured, `/build`
behaves exactly as if this component weren't installed at all — every task runs on your main model.
Most adopters will never touch this, and that's the fully-supported default path.

Populated shape: `{"implement": "<your-model-name>"}`. Requires a local model runtime (e.g.
[Ollama](https://ollama.com)) serving an HTTP chat API on `localhost:11434`, with your chosen model
already pulled — see the component's own README for the full mechanism, prerequisites, and known
limitations before configuring this.

Examples: `{"implement": "qwen3-coder:30b"}` · `{"implement": "gemma3:27b"}`

---

## Behavioral config: read, not substituted

These four aren't find-and-replace targets. They're settings the skills consult.

### `available_models` and `fable_available`

Default: `available_models: ["haiku", "sonnet", "opus"]`, `fable_available: true`

**Rewritten 2026-09-05** (the two-axis SDLC redesign) — this pair replaces the old single
`review_model_families` variable, whose rule was different in a way worth stating plainly rather
than silently editing over: the old rule said *"if only one family is available to you, skip the
review visibly rather than running a same-family pass and calling it cross-model."* That's reversed
now. The design review always runs; target selection is **tier-conditioned, not uniform** (revised
again 2026-09-09 after a uniform Fable-first default was found to collapse the cost ladder to one
rung — Tier 2 fires just as automatically as Tier 1's rarer case, and Tier 2 is the common one):

**Tier 1** — preference order (1) **Fable**, when `fable_available` is `true` and the draft wasn't
itself written on Fable (a Fable-drafted design falls straight to option 2 — reviewing it with
Fable again would be a same-model pass at the top of a ladder meant to avoid exactly that); (2) **a
different Claude model than the one that drafted**, checked against `available_models` (ordered
weakest-to-strongest): sonnet- or haiku-drafted designs review on `opus`; opus-drafted designs
review on `sonnet`; Fable-drafted designs review on `opus` (the strongest `available_models` entry
— falling to the *strongest* Claude-mainline model, not just *a different* one, since a
Fable-drafted design already used the most differentiated option available); (3) **the same model,
in a fresh context** — only when nothing else is reachable at all.

**Tier 2** — preference order (1) a different Claude model than the one that drafted, same mapping
as above; (2) the same model, in a fresh context, only when no other Claude model is available.
Fable is **not** part of Tier 2's automatic default — it stays reachable as an explicit further
pass if wanted, same as any other "one more look."

Weakest option in either ladder is still real, never labeled as more than it is.

Every option here is a Claude model, Fable included; what buys the independence is the fresh
context plus a different model than the author, not a different vendor. **The point was always
independence, not a stronger model** — a more differentiated model reading in a fresh context finds
a different class of problem than the same model (or a closely-related one) re-checking its own
reasoning, and that's still true. What changed from the old rule is what happens when no different
model is available: the old rule treated a same-model pass as worse than no review at all ("worse
than a skipped one, because it gets counted as a gate that passed"). The new rule treats a
*mislabeled* pass as the actual problem, not the weaker pass itself — so the heading names the real
reviewing model every time (`## Design review — Opus, fresh context`, never bare "cross-model
review"), and the review simply never gets skipped for lack of a stronger option.

### `subagent_models`

Default: `code-reviewer: sonnet`, `docs-writer: haiku`

`docs-writer` is mechanical transcription and runs fine on the cheapest tier. `code-reviewer` needs real
reasoning, so it defaults higher.

Override per call when a pass warrants it. The clearest case: **code that will run on someone else's
machine deserves a stronger review, on a different model than whatever wrote it.**

### `update_check_enabled`

Default: `true`

Off-switch for the `update-notification` SessionStart hook (a bundled `standalone/` component — see
that component's own README for what it checks and how). Not asked about during install the way a
`required`-kind variable would be — the real opt-in moment is choosing to install the
`update-notification` component at all. Set this to `false` in your installed receipt if you want the
component present but the passive check disabled.

---

## Changing a variable after installing

Edit `.claude/phase-gate-install/variables.json` in your repo, then re-run the installer. It is
idempotent: a run that changes nothing writes nothing, and one that changes a substituted name rewrites
only the references affected. Run it in recommend-only mode first if you want to see the diff before
anything is written.
