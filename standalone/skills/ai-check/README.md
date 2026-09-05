# ai-check

A Claude Code skill for forensic AI-text detection. Scores a piece of writing across nine
signal categories (word predictability, sentence-length uniformity, hedge density, structural
tells, specificity, transition fingerprints, punctuation, voice, and rhetorical scaffolding),
grounded in the published detection literature, and outputs a structured evidence log rather
than a vague judgment.

**Zero configuration. Zero repository coupling.** This is a standalone component — it does not
assume anything about the repo it's installed into, and it carries no reference to any other
component in this export.

## Install

Copy `SKILL.md` into your project's `.claude/skills/ai-check/SKILL.md` (or your user-level
`~/.claude/skills/` for every project). That's the whole installation.

## Use

Ask Claude something like "does this sound AI?", "run ai-check on this", or "what gives this
away as AI" with the text in question. See `SKILL.md` for the full signal list, scoring
rubric, and output format.

## License

MIT — see [`LICENSE`](LICENSE). This component is **not authored by this repository's owner**;
it carries its own license and its own copyright holder. Do not replace this file with the
repo-root license.
