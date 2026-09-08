---
name: doc-review
description: >
  Use when someone asks to review, check, or improve a written document — a README,
  guide, manual, design doc, report, or any prose deliverable. Triggers: "review this
  doc", "does this make sense to someone new", "check this README", "is anything in
  here wrong", "why does this read like a machine wrote it", "tighten this document".
  Also use before publishing or sharing documentation, when a document has grown long
  enough that its facts may have drifted from the files they came from, when the same
  word keeps turning up, or when working through review comments people left on a
  published copy of a document.
---

# doc-review

A document fails in three unrelated ways, and no single reader catches all three.

| Failure | Who catches it | Pass |
|---|---|---|
| A stranger cannot follow it | a reader with no context at all | **A — cold read** |
| A claim is wrong against its own source | a reader who opens the files it cites | **B — grounding** |
| It reads like a machine wrote it | a script that counts | **C — voice scan** |

Run all three, merge them into one numbered list, and change nothing until the
author says which findings to land.

## The one rule that outranks the rest

**Report first. Edit second. Never both in one move.**

Findings go in the response text, in full, as a numbered list. Not summarized, and not
written only to a file. A file on disk is not the same as showing someone. Then wait.

This is not caution for its own sake. In the review cycle this skill was built from,
three separate requested edits were wrong once checked against the source they came
from, and one of them would have deleted half of a two-condition rule while looking
like a word swap. Applying findings without a pause is how that lands silently.

## Step 0 — pick the mode

| Invocation | What runs |
|---|---|
| `<path> [<path>...]` | C, then A and B in parallel → one report → gated apply |
| `--cold <path>` | A only. The cheapest real check. Use it when only intelligibility is in question |
| `--ground <path>` | B only. Use for a factual sweep after edits |
| `--voice <path>` | C only. Free, no subagent. Use it as a last sweep before publishing |
| `--publish <path>` | Render the file to a review page and publish it for comments |
| `--comments <path>` | Work the comment threads on that file's published page |
| Pasted text, no path | Write it to a scratch file first, then treat it as a path: A and C run, B cannot (nothing to ground against) and the report says so. `--publish` and `--comments` need a real file |

**Several paths**: A reads them together and gives one restatement and one friction
log. B grounds each. C reports frequency per file, plus one cross-file check for
sentences repeated near-verbatim.

State which passes are about to run and on which models before spawning anything.

## Pass C — voice scan (runs first, costs nothing)

```
python scripts/voice_scan.py <path> [<path>...]
```

Stdlib only. It counts what a reader working section by section cannot see: word and
phrase frequency across the whole document, hits against the vocabulary list in
`references/voice-tells.md`, punctuation density, negation framing, and sentence-length
spread.

A word fires only when it clears both floors: **4 or more occurrences and at least 2
per 1,000 words**. Both, so a short note does not flag a word used twice and a long
one does not hide a word used eight times.

**Frequency is a signal, never a rule.** A term of art recurs legitimately, and
swapping in synonyms to avoid repetition is itself a tell. Every frequency finding
carries either a named substitute per occurrence or an explicit "keep: term of art".

Then read `references/voice-tells.md`'s checklist over the script's output for what a
regex cannot see: hedge stacking, three-item rhythmic lists, signposting openers,
reflexive end-of-section summaries, unassigned "it" and "this", uniform paragraph
length. Each becomes a `V` finding with all its line numbers and a proposed substitute.

## Pass A — cold read (clarity)

### Choosing the model

Independence is the whole point, so the reviewing model must differ from the one
running this session.

1. **State the current model.** Read it from the session environment. If it genuinely
   cannot be established, ask the author before spawning. Do not guess.
2. **If the project has a model-availability file**, resolved upward from the working
   directory (for example `.claude/phase-gate-install/variables.json`, if the project
   was set up that way), pick the strongest listed model that is not the current one.
   Never assume any particular model exists. Read the file.
3. **If it does not**, use this fixed order. Current model is the strongest tier, so
   spawn the mid tier. Current model is anything else, so spawn the strongest tier.
4. **If that still lands on the current model**, spawn it anyway in a fresh context and
   write `independence: same model, fresh context` in the report header. Weaker, still
   real, never labeled as more than it is.

The header names both models every time, so a reader can check the claim.

### The prompt

Spawn a fresh agent with the chosen model. Give it the document path(s) and
`references/finding-categories.md`, and tell it to read **nothing else**. Every extra
file it opens is context a stranger would not have.

> Read the attached document(s) and nothing else. You are a competent reader who has
> never seen this project. Judge whether the document is intelligible, not whether it
> is correct. Assume every factual claim is true.
>
> Return three things:
>
> 1. **Restatement.** In your own words: what is this document for, who is it for, and
>    what is the reader supposed to do first? Do not quote. Restate.
> 2. **Friction log.** Every point where you stopped and had a question. Quote the text
>    verbatim and write the question you had. Include these even for sections you would
>    otherwise pass. A section that reads fine but raised four questions is a worse
>    result than one that failed cleanly.
> 3. **Clarity findings** against the B-list in the checklist file, each tagged with its
>    id, the line, the problem, and a proposed fix.

**A wrong restatement is the most valuable finding this pass produces.** If the reader
cannot say what the document is for, no amount of correct detail saves it.

**Stated limitation**: a spawned agent still loads the host project's rules file
(`CLAUDE.md` or equivalent), so it is fresh but not fully cold. For anything going to
strangers, recommend the stronger version: the author pastes the same prompt into a
brand-new session with no project loaded. In the cycle this skill came from, that
direct read found 25 findings the spawned read had missed.

## Pass B — grounding (correctness)

Spawn a fresh general-purpose agent with read, search, and shell access (and web fetch
when available). Default it to a mid-tier model. This pass is mechanical checking, not
judgment.

> Extract every checkable claim in the attached document and verify each one against its
> actual source. Never confirm anything from memory. Open the file, run the count, fetch
> the URL. Check:
>
> - **Counts.** Re-derive every number by listing or grepping the thing being counted.
>   A number written from memory is wrong often enough to assume it is.
> - **Paths, files, commands, flags.** Confirm each exists. Sanity-check copy-pasteable
>   commands, and dry-run them where that is safe. Watch for commands that exit zero and
>   do the wrong thing.
> - **Cross-references.** Every "see section X" and every link: does it resolve, and does
>   what it points at actually answer the question it was cited for?
> - **Inventories.** Compare each list against the real roster and report actual versus
>   claimed, including anything missing from the list entirely.
> - **External URLs.** Fetch them, or mark them explicitly unverified.
> - **Status and "done" lines.** Check them against the version history.
> - **Figures and alt-text** against the prose they sit beside.
> - **Instructions naming two sources for one input**, and two sections stating one fact
>   differently.
> - **Rationale claims** of the form "X because Y" — is Y actually true of the thing it
>   is said of? A true mechanism with a false stated reason is still a defect.
>
> Return findings against the A-list and C-list in the checklist file. Every finding
> cites the source that contradicts the text.

## Consolidation

Merge every pass into one report and print it in the response, in full.

**Reconciliation** when passes land on the same span: correctness outranks clarity
outranks voice. Duplicates merge into one finding carrying both citations. A voice
finding on a line that also carries a correctness finding is held and marked `after #N`,
so a substitution never overwrites wording the grounding pass just verified.

```
DOC-REVIEW: <path(s)>   current: <model>   cold read: <model>   grounding: <model>   voice: script

READER'S RESTATEMENT
<Pass A's restatement, verbatim>

FINDINGS  (BLOCK / STRONG / JUDG · X=correctness  C=clarity  V=voice  P=policy · checklist id)
1. [X BLOCK] <file>:<line> — "<quoted text>" → <what is wrong> · source: <file>:<line> · fix: <proposed edit> · A1
2. [C STRONG] <file>:<section> — <problem> · fix: <proposed edit> · B10
3. [V JUDG] <file>:<lines 12, 40, 88> — "<word>" ×8 in 3,590 words (2.2/1k) · fix: "<substitute>" ×5, keep ×3 (term of art) · after #1
4. [C JUDG] <file>:<line> — curly quotes ×6 → straight · safe-to-apply

FRICTION LOG (verbatim)
- <file>:<line> "<quote>" — <the reader's question>

WHAT HOLDS UP
<what the passes examined and found sound, so the comparison is real>

APPLY? all / none / list of numbers
```

**`safe-to-apply` is mechanical and narrow**: punctuation, whitespace, straight-quote
normalization, and typos carrying no meaning. **Never a finding whose fix deletes or
substitutes a word.** That class looks like wording and is not: in the source cycle,
"drop this adjective" turned out to be half of a two-condition rule, and "cut this
adverb" turned out to be the precise word.

Write a `<doc>.review.md` sidecar only if asked. The response is the deliverable.

## Apply

Nothing is edited until the author names the findings to land. Then, for each one:

1. **Re-open the source sentence before editing**, including for the author's own
   requests. Decide apply, reword, or reject, and for a reword or reject say why and
   cite the line that settles it.
2. **A correctness fix triggers a sweep.** Grep the wrong claim across every sibling
   document first, list the hits, fix them together. A false claim that justified one
   thing usually justified three others.
3. **Counts: source and hedge, do not assert and renumber.** If a number is uncertain,
   say where it came from and when.
4. **Anything added resolves what it makes redundant, in the same pass.** A new summary
   beside the detailed text it summarizes is a defect, not a bonus.
5. **Verify an external URL before inserting it.**

### After applying

Say this plainly, every time:

> The model that found these also wrote the fixes. The changed text has had no
> independent read.

Then **run A and B again on the changed files**. This is the stated next step, and a
cold read on its own does not cover it. The failure this closes was a false rationale
that survived into four sibling files, and only the grounding pass catches that shape.
The cold read on the re-run **must use a different model than the one that applied the
fixes**. The header shows both. If the author declines, record "re-read declined".

Never commit. The host project's own conventions decide that.

## Publish and comments

`--publish` renders the file to a page whose content is the file's own bytes: numbered,
escaped, and never rendered as Markdown. A line reference in a comment always means the
same line in the file, and the page cannot drift from what it shows.

```
python scripts/render_review_page.py <path>
```

`--comments` works the threads on that page: quote the comment, locate the text, run the
same source check as Apply, then edit, reword, or reject with the reason cited, reply
saying which happened, and republish.

Full flow, including how a later session finds the page again:
`references/publish-and-comments.md`. Both modes need the artifact publishing tool. If
it is unavailable, say so rather than failing quietly. The three review passes do not
need it.

## Cost

A full run spawns two agents: the cold read on the chosen model and a mid-tier grounding
pass. The voice scan is a local script plus a short reading checklist. Name the actual
models before spawning. `--cold`, `--ground`, and `--voice` are the cheaper deliberate
choices, and `--voice` is free.

## What this skill does not do

- **Score how likely a text is machine-written.** Different job. If a project has a
  detection-scoring skill installed, that is where that goes.
- **Rewrite for non-documentation registers** such as essays, marketing, fiction, and
  correspondence. This skill's voice work covers documentation register and is complete
  on its own for it. A dedicated prose-rewriting skill goes deeper if the project has one.
- **Review code.** Findings are about a document's claims and readability, not an
  implementation's correctness.
- **Interview a human tester.** Watching a real person use a document is a different and
  more expensive instrument, and this does not replace it.
- **Decide.** It reports, and it edits what it is told to edit.
