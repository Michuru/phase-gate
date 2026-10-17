# handoff: the incoming path (resume from a primer)

Read from `SKILL.md`'s Direction section. "The scan" is `handoff_scan.py` and "the consume script" is `handoff_consume.py`; their exact commands are in `SKILL.md` (a variable in this file would not be substituted).

## Contents
- Discover the live primers
- Check each candidate for a closed thread
- Ask the other live sessions first
- Confirm, then act

## Discover the live primers

Run the scan (the command is in `SKILL.md`). It lists, one row per primer: the repo, filename, date, first heading and the full path. **Liveness is directory position only**: a primer is live when it sits at the top level of a repo's `.claude/handoffs/`; `archive/` is never live, and no file is opened to judge a thread (the scan reads only the first line, to flag a half-finished consume). The scan covers the repo you are in, every directory nested directly under it that has its own `.claude/handoffs/` (found by directory listing, so a new nested repo needs no edit), and the external repos on the list in its `EXTERNAL_REPOS` constant (or passed with `--external`); a repo outside your tree cannot be found by listing, so that list is maintained by hand. Add a repo there the first time a live primer turns up in one the scan missed.

Relay its `note:` lines (for example a listed external repo with no handoffs directory). A row marked "CONSUMED marker at top level" is a half-finished consume, not a live primer: say so and offer to finish it with the consume script. If you ever glob by hand, use forward slashes in the pattern (a backslash silently matches nothing and reads as "no primers exist").

- **No rows:** say so plainly and ask what to do instead. Never force a resume that is not there.
- **One row:** that is the candidate.
- **More than one row:** that is itself the ambiguity signal, however close or far apart the dates. Run the closed-thread check on **every** candidate before presenting the list (deferring it to "whichever gets picked" leaves the others unchecked, which is how two primers went stale unnoticed). List them all (filename, repo, date, one-line summary, and a "looks closed" note for any the check found closed) and let the user pick. Never take the most recent by modification time.

## Check each candidate for a closed thread

Read the primer, then check cheaply whether its thread is already closed. Both checks are targeted reads of what the primer points at, never a fresh investigation. Run check 1; run check 2 only if check 1 is inconclusive.

1. The primer names a source of truth (a `BACKLOG.md` entry, a design doc). Read just that and look for an explicit completion marker: Done, Closed, Archived, a Status saying so, or the entry moved to `BACKLOG_ARCHIVE.md`.
2. A targeted `git log --oneline` (optionally `--since=<the primer's date>`) in the repo the primer's files live in, looking for a commit that plausibly completes the described task. A missing marker is not proof the thread is open: work can ship without anyone writing one.

## Ask the other live sessions first

This section applies where your Claude Code provides the `ListAgents` and `SendMessage` tools; where it does not, skip it.

Standing rule: the user often works several handoffs at once, so a primer that looks stale or orphaned may be a live thread in another window, and git log and doc markers cannot tell you that. When the scan finds more than one live primer, or the one picked is not obviously this session's own:

1. Run `ListAgents` once (never in a loop). Sessions marked `offline` cannot be reached; say so rather than treating silence as agreement.
2. For each primer you might resume, consume or call closed, `SendMessage` the reachable peer that plausibly owns it, in the same pass as the closed-thread check and before any closed verdict reaches the user. Until the owner answers, a verdict is "unconfirmed with its owner". The owner is: a session the primer's own text names; else a session whose name matches its topic; else, only when nothing narrows it, any busy interactive session. **A named owner that is not listed is unreachable: do not redirect the question to an unrelated peer.** Send one message per peer covering all the primers it might own. Make the first line self-contained: which primer, what you found, and the question (still working it, done and safe to consume, or next step). Say you have not touched it, and never ask the peer to stop or change its work.
3. Do not consume, archive or resume a primer another session may hold until it answers or the user says to go ahead (the user's own "consume it" or "resume it" counts). A peer's silence is not consent. If no peer is reachable, tell the user which primers you could not check, naming any unreachable owner, and let them decide.

## Confirm, then act

With one live candidate identified (directly or by the user's pick) and its check run, confirm with the user before treating it as authoritative: state its filename, repo, date and a one-line summary, **and, if either check found evidence of closure, say so plainly** (for example "this thread looks closed per `BACKLOG.md` or git log; want me to consume it and pick something else, or is there a real tail left?"). If confirmed live, act on the primer directly: read what it points at (design doc, `BACKLOG.md` entry, file and line) and continue, changing into that primer's own repo first if it differs from the current cwd. The primer is the full briefing; nothing more is needed from this skill. If confirmed closed, consume it with the consume script (`--reason "thread closed, see <source>"`; exit codes are in `SKILL.md`) and ask what to work on instead.
