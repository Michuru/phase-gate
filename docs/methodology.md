# The methodology

This is the rulebook. Everything else in this repo — the skills, the agents, the hooks — exists to make
the rules below happen consistently instead of only when someone remembers them.

Read this once before installing anything. The skills will make sense afterwards, and won't before.

**On the filenames in this document.** `BACKLOG.md`, `BACKLOG_ARCHIVE.md`, `MISTAKES.md`, `CLAUDE.md`,
`Design Docs/` are defaults, not requirements. If you use different names, set them in
`installer/variables.json` and the installer rewrites every reference across the skills and this file to
match. See [PORTING.md](PORTING.md) for the full list. The *concepts* are load-bearing; the names aren't.

---

## 1. The core idea

Most AI-assisted development fails in one of two directions. Either every change gets the same heavy
process regardless of size, which nobody sustains past the first week — or nothing does, and you
accumulate confident-sounding work that was never actually checked.

This methodology's answer is to **decide how much ceremony a change earns before starting it**, using a
fixed set of tiers, and then to make the expensive parts cheap by delegating them to subagents with
fresh context rather than doing them inline.

Two claims underpin everything below, and both are worth stating plainly because the rules stop making
sense if you don't accept them:

1. **An assistant checking its own work is weaker than a second reader.** Not because it is careless,
   but because it re-derives the same reasoning and reaches the same conclusion. A fresh context reading
   the same code finds a different class of problem. This is why the QA gate exists and why it is a
   *separate* agent.
2. **"Verified" is a claim about evidence, not confidence.** The most common failure this process is
   built to prevent is work reported as verified on the strength of reasoning rather than a real check
   against a real source.

---

## 2. Tiers: decide the ceremony before you start

Self-assess every request against four tiers **before implementing** — not only when someone asks for a
"plan." State the tier out loud when you make the call, so it can be challenged before the work happens
rather than after.

| Tier | What it is | Design doc? | Cross-model review? | QA gate? |
|---|---|---|---|---|
| **4** — trivial | Single spot, single file. No new UI, no shared-schema change. | No — but state the plan in one sentence first | No | Only if it touches a flagged surface (§5) |
| **3** — medium, pattern-following | More than one file, new UI, or a shared data file's schema — **and it closely mirrors an already-shipped, already-tested pattern** in this codebase | Yes, short | Skipped | Yes |
| **2** — medium, real design judgment | Same shape as Tier 3, but **no clean existing pattern to mirror** | Yes, short | Standard practice | Yes |
| **1** — new component or major rewrite | A new tool from scratch, or rewriting/consolidating an existing one's architecture | Yes, fuller | Offered | Yes |

**The Tier 2/3 split is the one most worth getting right**, and it reduces to a single question, asked at
the same moment as the tier call itself:

> Is there an already-shipped, already-tested pattern here that I am directly copying — or am I making a
> real design choice?

If you're genuinely unsure, **default to Tier 2.** The cost of an unnecessary review is small; the cost of
a wrong architectural assumption discovered after implementation is not.

**Recognize tier from a request's shape, not its wording.** Nobody says "this is Tier 2." They say "can
you also make it do X," and X turns out to need a new data shape. Treat any mention of getting feedback
or comments on something as a signal to first check *what* that something is — a design still being
decided, or a deliverable already finished — before producing either.

**Tier 1 gets a model question first.** Real architectural ambiguity is the case where a wrong assumption
is expensive, which is what a stronger model is for. Ask about it **at the start of the design pass,
before any exploration or drafting** — asking after a design is drafted defeats the purpose, because the
drafting is the part that needed the judgment. Switch back afterwards: the stronger model is for the
design reasoning specifically, not a standing change for the whole session.

---

## 3. The QA gate

Any Tier 1, 2, or 3 work — and any Tier 4 fix touching a flagged surface — gets an **independent review
pass in fresh context** before it is marked done, archived, or committed.

Use the bundled `code-reviewer` agent. It matters that this is a separate agent rather than a
self-review step, for the reason in §1: same context, same conclusion.

Three rules about it:

- **Announce it explicitly.** Never fold a QA pass silently into other output. If a reviewer ran, the
  human reading the result should be able to tell.
- **It runs before the work is archived or committed**, not after. A review whose findings arrive after
  the commit is a report, not a gate.
- **A clean pass is a real result.** Don't manufacture findings to justify the call, and don't treat
  "no findings" as evidence the review didn't work.

**One narrow extra case.** If you are editing logic that maintains *state across sessions* — anything
with a marker file, a resume token, or bookkeeping that a later session reads — a code review is the
wrong instrument, because the bug class is "the instructions are ambiguous in an edge case," not "the
code is wrong." Instead, give a fresh agent a crafted interruption scenario and have it walk the edited
instructions literally, reporting what it would actually do. Deliberately narrow: most prose is
stateless and this cannot happen there.

---

## 4. Verification: against the real thing

**Verify against the real target, not a convenient stand-in.** A local preview, a mock, or a test
harness is fine for logic and calculation correctness, but it is a genuinely different runtime from the
real deployment — different origin, different storage permissions, different auth. A fix that depends on
one of those differences can look solid locally and fail in the only environment that matters. **If you
cannot test against the real target in this session, say so explicitly rather than reporting
"verified."**

**A confirmed fix to the logic does not confirm the data it operates on.** These are separate claims
needing separate checks. If real-world evidence contradicting a stored value surfaces mid-investigation,
check that value against its own source before treating the logic fix as the end of the investigation —
a wrong stored constant can survive several correct formula fixes in a row without anyone noticing.

**Make a capability's fallback path visible, not silent.** For any code depending on an optional
capability with a working fallback, "it fell back and still works" and "it silently reverted to a
known-broken mechanism" look identical from the outside unless the code says which happened. Give every
distinct failure and fallback branch its own visible signal, not just the one you expect.

**A fix that doesn't fully account for the size of the reported symptom isn't finished.** If the
explanation covers part of what was reported, ask rather than writing a plausible theory into permanent
documentation.

**When a technical finding is corrected mid-project, check every already-delivered document for the same
stale claim** — not just the one you're currently editing. Make the correction visible in place rather
than silently rewriting, so a reader can reconcile it against whatever version they already have.

---

## 5. Flagged surfaces

A **flagged surface** is a specific function, file, or module in *your* codebase with a documented
history of subtle bugs. Its only purpose is to escalate: a change that would otherwise be Tier 4 gets
the full QA gate anyway if it touches one.

**This list ships empty.** It has to — it's a property of your code, not of this methodology. Set it in
`installer/variables.json` (`flagged_surfaces`), and grow it the same way it's meant to be grown:

> When a bug turns out to have been subtle, and it was in the same place as a previous subtle bug, add
> that place to the list.

Don't populate it speculatively with everything that looks important. A list of twenty surfaces escalates
everything and therefore escalates nothing. The value is in it being short enough to mean something.

---

## 6. Commit conventions

**Commit automatically, without asking first, at three triggers.** This is a standing authorization for
*local* commits, and it deliberately overrides the usual "confirm before committing" default — because
the point is to leave recoverable checkpoints without adding a decision to every one of them. **Pushing
anywhere still needs explicit confirmation every time.**

1. **Whenever a `BACKLOG.md` item is marked done and verified.** One commit per resolved item, message
   drafted from that entry. A session that resolves four things gets four commits — that's correct, not
   excessive. Small drive-by fixes folded into the same entry ride along in the same commit.
2. **Immediately before any large or risky rewrite**, whether or not a backlog entry exists yet. This is
   the safety-net case, so it can't wait for the checkpoint above.
3. **Before ending a session or wrapping up a chunk of substantive work** — proactively check
   `git status` and commit anything narrowly-staged and verified, even without a matching backlog entry.

Mid-investigation uncommitted changes are fine. Nothing forces a commit before something is actually
done. But on any fix with several intermediate steps, treat "check `git status` and commit" as its own
explicit final step rather than letting it be absorbed into "I verified it, so it must be committed."

### Narrow staging

**Stage specific files. Never `git add -A` or `git add .`** Another agent, session, or person may have
unrelated work sitting uncommitted, and a broad add silently takes it hostage in your commit.

**Prefer an exact-match edit over a whole-file write on any shared file** — the rulebook, the backlog,
the mistakes log. An exact-string edit *fails safely* if something else already changed that spot; a
full-file replacement silently clobbers it. If there's any sign a file was touched since you last read
it, re-read it immediately before editing.

**Review what you actually staged.** After any broad add, check `git status` before committing, and if
anything looks unexpected — even with an innocuous filename — read the file's contents before it goes
anywhere.

### Permission allowlists leak credentials

Claude Code's per-machine allowlist (`.claude/settings.local.json`) accumulates the raw text of approved
commands across every session, and its redaction of captured values is best-effort rather than enforced.
This is a real, repeatedly-observed leak vector, not a theoretical one. It is gitignored in this repo's
`.gitignore` and should be in yours. If it ever gets force-added anyway, read the diff for values that
aren't redaction placeholders before letting the commit through. `.githooks/pre-push` is the backstop —
see `.githooks/secret-patterns.txt` for how to give it patterns worth having.

---

## 7. The four documents

| File | What it is | Read when |
|---|---|---|
| `CLAUDE.md` | Your rules doc — current-state facts and conventions for this codebase. Loaded in full every session. | Automatically, always |
| `BACKLOG.md` | **Open and actionable items only.** | When the task plausibly overlaps an existing item |
| `BACKLOG_ARCHIVE.md` | Resolved history with citations and verification steps. | On demand, never by default |
| `MISTAKES.md` | Process mistakes — false "verified" claims, wrong assumptions about how something runs. About *how the work was done*, not what's broken in the code. | Before making a "verified" claim resembling a past entry |

Four rules that keep these useful:

**Keep the rules doc lean.** It loads in full every session regardless of task, so its size is a fixed
per-session cost paid on every single request. When a section grows into session-by-session narrative
rather than current-state fact, split it into a companion notes file and leave a pointer. The
`consolidate-docs` skill does this sweep.

**The backlog holds only open items.** Resolved entries move to the archive as part of wrapping up. A
backlog that accumulates closed work becomes a session journal that gets re-read for nothing.

**The mistakes log is a history, not a default read** — so whenever an entry amounts to a durable rule
rather than a one-off, write that rule into the rules doc too, rather than leaving a future session to
rediscover it. This is the single most important habit for a log like this to be worth keeping.

**Docs-sync is a hard requirement, not optional cleanup.** If a change alters anything the rules doc
documents — a behavior, a threshold, an architecture note — the doc gets updated in the same pass.
Delegate the mechanical writing to the bundled `docs-writer` agent, and announce that delegation.

### One warning about delegating documentation

When a delegated write includes any verification-results or testing narrative, **either supply the exact
real numbers for the agent to transcribe, or name the exact files it must read and quote from, and tell
it not to state a count that isn't a direct read from one of those.** Left to summarize on its own, a
documentation agent will produce plausible-sounding, internally consistent completion figures rather than
ground truth — a confident "all nine applied, none remaining" when one of seven had actually run. Always
spot-check the diff it produced against the real files before treating its summary as confirmation.

---

## 8. When you don't know, ask

Ask rather than guessing or silently picking a default: an ambiguous target, an unconfirmed real-world
fact, a design choice between two reasonable approaches.

**A plan being approved is not a go-ahead to implement it now.** Exiting a planning mode approves the
*design*. Ask whether to build it immediately or record it for later.

**A complimentary remark about a plan is not approval of it.** "This looks great" is a reaction, not a
decision. Only an explicit yes counts.

**Report findings and ask; don't declare things settled.** Whether a discussion is resolved or a design
is ready is the human's call, not yours to assert.

**Present findings as an explicit numbered list**, not as summarized prose under headings. A list can be
responded to item by item; a paragraph can only be agreed or disagreed with wholesale.

**When a capability barrier appears** — a missing tool, an expired login — verify it's real, then ask
about fixing the root cause rather than quietly routing around it with a workaround that will need
maintaining forever.

---

## 9. Standing operational rules

**Never kill a process by image name when a PID is available** — and one almost always is, since
whatever spawned the process reported it. Matching by name matches every instance on the machine, not
just the one this session started. Clearing one hung headless browser this way can close every browser
window the human has open, including their real work.

**After any stash-push/stash-pop sequence used to compare a change against real data, confirm the file's
on-disk state before treating the work as done.** Never assume a pop happened because a push did. A
status check or a grep for the change's own signature settles it.

**Treat an authenticated external system as a standing capability for the rest of the session.** If a
login or a CLI tool was confirmed working earlier, check whether you already have direct access before
falling back to a manual walkthrough for a later related task.

**When several agents or sessions may be active at once**, the habits in §6 (narrow staging, exact-match
edits on shared files, re-read before edit) are what make that safe. If you learn another session is
editing a file you're also editing, message them your exact touch zones and ask for theirs — a status
line showing a file as modified doesn't say which lines are whose.

---

## 10. Nested repositories

If your repo contains other repos as subdirectories, two behaviors are worth knowing because they differ:

- **The rules doc resolves upward.** A session working in a subdirectory gets the parent's rules doc *in
  addition to* any local one. This is filesystem-based, not git-based — it doesn't care that the
  subdirectory is a separate repository. Skills resolve the same way, so a genuinely cross-cutting skill
  placed at the parent is available from every child.
- **`.claude/settings.json` does not inherit.** Hooks, statusline, and permissions are per-repo. Each
  repo needs its own copy.

Neither behavior extends to `BACKLOG.md` or `MISTAKES.md`. Those are only ever read because something
points at their exact path.

**`core.hooksPath` is local git config and does not survive a fresh clone.** Re-set it in every new
clone, or the hooks are silently absent — nothing errors, they simply never run. The bundled
`hooks-health-check` component reports this at session start rather than letting it go unnoticed.
