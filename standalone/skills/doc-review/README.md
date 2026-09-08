# doc-review

A Claude Code skill for reviewing written documentation. Reads a document three ways at
once: a fresh model with no context reads it cold for clarity, a second reader opens
every file the document cites and checks its claims against them, and a script counts
document-level word repetition and machine-sounding register. Reports every finding as
one list and edits nothing until you say which to apply — each one checked against its
source again before it lands.

**Zero configuration. Zero repository coupling.** This is a standalone component — it
does not assume anything about the repo it's installed into, and it carries no
reference to any other component in this export. It does not need `ai-check` or
`humanize` installed; it is complete on its own for documentation register.

## Install

Copy the whole `doc-review/` directory into your project's `.claude/skills/doc-review/`
(or your user-level `~/.claude/skills/` for every project) — unlike a single-file
skill, this one needs its `references/` and `scripts/` subdirectories too.

**Requires Python 3** on `PATH`, for `scripts/render_review_page.py` and
`scripts/voice_scan.py` (both standard-library only, no packages to install).
Publishing a document for comments needs the Claude Code `Artifact` tool — the three
review passes themselves do not.

## Use

Ask Claude to review a document, or invoke directly:

- `/doc-review <path>` — full run: voice scan, cold read, and grounding check, merged
  into one report.
- `/doc-review --cold <path>` — clarity only, cheapest real check.
- `/doc-review --ground <path>` — correctness only, checked against cited sources.
- `/doc-review --voice <path>` — the free script pass, no subagent.
- `/doc-review --publish <path>` — render the document to a comment-ready page.
- `/doc-review --comments <path>` — work the comment threads on a published page.

See `SKILL.md` for the full mechanism, the model-selection rule, the report format,
and what this skill deliberately does not do (AI-detection scoring, non-documentation
prose registers, code review).

## License

MIT — see [`LICENSE`](LICENSE). Most of this skill is original work by this
repository's owner. One part is not: `references/voice-tells.md`'s vocabulary list
and six of its seven hard rules are adapted from a separate MIT-licensed skill by a
different author, whose notice is carried in full inside `LICENSE`'s "Third-party
notices" section and is not to be removed.
