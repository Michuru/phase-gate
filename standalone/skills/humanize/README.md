# humanize

A Claude Code skill that rewrites AI-flat text to mirror the statistical and stylistic
fingerprint of human writing — sentence-length variance, hedge density, punctuation habits,
and the RLHF "helpful assistant" voice that current detectors actually fire on. Grounded in
the same detection literature as the companion `ai-check` skill; full citations in
`references/research.md` (background only, not needed to run a rewrite).

**Zero configuration. Zero repository coupling.** This is a standalone component — it does not
assume anything about the repo it's installed into, and it carries no reference to any other
component in this export.

## Install

Copy the whole `humanize/` folder (including `references/research.md`) into your project's
`.claude/skills/humanize/` (or your user-level `~/.claude/skills/`). That's the whole
installation.

## Use

Ask Claude to "humanize this", "make this sound more human", or paste text and ask why it
reads as AI-flat or robotic. See `SKILL.md` for the full lever list, the rewrite protocol, and
the seven hard rules it enforces on every output.

## License

MIT — see [`LICENSE`](LICENSE). This component is **not authored by this repository's owner**;
it carries its own license and its own copyright holder. Do not replace this file with the
repo-root license.
