# Voice tells for documentation

> This file's vocabulary list (Part 1) and six hard rules (Part 2) are derived from
> an MIT-licensed prose skill by that author, Copyright (c) 2026 Harshaneel Gokhale.
> The rewrite levers (Part 3) and the checklist (Part 4) are original to this skill.
> The full license notice travels with this skill's own LICENSE file; this note is
> a pointer to it, not a substitute.

This file is read by two things: `scripts/voice_scan.py`, which parses Part 1 at
runtime to know what to count, and whoever is applying `V` findings by hand, who
reads Parts 2 through 5. Keep Part 1's format (`- \`term\` -> substitute`) exact,
one entry per line, so the two never drift apart.

---

## Part 1 -- vocabulary list with substitutes

### Seed catches (a real review cycle; not on any generic list)

These five came out of an actual multi-pass review of a real document, not a
compiled list of known AI tells. They recur in documentation specifically because
they sound precise while hiding the actual mechanism.

- `silent` -> name what was not shown, or "with no message" / "without warning"
- `silently` -> same as `silent`, or delete the adverb and state the fact plainly
- `quietly` -> same as `silent`, or delete it outright ("it deletes the file" instead of "it quietly deletes the file")
- `supersede` -> replace
- `supersedes` -> replaces
- `superseded` -> replaced
- `superseding` -> replacing
- `delve` -> look at, go into
- `delves` -> looks at, goes into
- `delved` -> looked at, went into
- `delving` -> looking at, going into

### Corporate and AI register

- `leverage` (verb) -> use
- `leverages` -> uses
- `leveraged` -> used
- `leveraging` -> using
- `utilize` -> use
- `utilizes` -> uses
- `utilized` -> used
- `utilizing` -> using
- `robust` -> reliable, or name what it handles correctly
- `robustness` -> reliability, or name what it handles correctly
- `comprehensive` -> complete, thorough
- `comprehensively` -> completely, thoroughly
- `streamline` -> simplify
- `streamlines` -> simplifies
- `streamlined` -> simplified
- `streamlining` -> simplifying
- `foster` -> encourage, support
- `fosters` -> encourages, supports
- `fostered` -> encouraged, supported
- `fostering` -> encouraging, supporting
- `facilitate` -> help, let, enable
- `facilitates` -> helps, lets, enables
- `facilitated` -> helped, let, enabled
- `facilitating` -> helping, letting, enabling
- `pivotal` -> key, central, or name why it matters
- `nuanced` -> detailed, specific
- `nuance` -> detail, specific point
- `nuances` -> details, specific points
- `multifaceted` -> has several parts, complex
- `crucial` (when overused) -> important, or state why it matters
- `crucially` -> importantly, or state why it matters
- `enduring` -> lasting, long-standing
- `endures` -> lasts
- `endured` -> lasted
- `garner` -> get, earn
- `garners` -> gets, earns
- `garnered` -> got, earned
- `garnering` -> getting, earning
- `vibrant` -> active, busy
- `vibrancy` -> activity, energy
- `tapestry` (figurative) -> mix, combination
- `tapestries` (figurative) -> mixes, combinations
- `testament` (figurative) -> proof, evidence
- `testaments` (figurative) -> proofs, evidence
- `interplay` -> interaction, relationship
- `intricate` -> detailed, complex
- `intricately` -> in detail
- `intricacies` -> details
- `intricacy` -> detail
- `landscape` (abstract noun) -> name the actual field or area
- `landscapes` (abstract noun) -> name the actual fields or areas
- `showcase` (verb) -> show, display
- `showcases` -> shows, displays
- `showcased` -> shown, displayed
- `showcasing` -> showing, displaying
- `highlight` (standalone verb) -> point out, show
- `highlights` (standalone verb) -> points out, shows
- `highlighted` (standalone verb) -> pointed out, shown
- `highlighting` (standalone verb) -> pointing out, showing
- `underscore` (standalone verb) -> confirm, show
- `underscores` (standalone verb) -> confirms, shows
- `underscored` (standalone verb) -> confirmed, shown
- `underscoring` (standalone verb) -> confirming, showing
- `align with` -> match, follow
- `aligns with` -> matches, follows
- `aligned with` -> matched, followed
- `aligning with` -> matching, following
- `additionally` (as an opener) -> also, and

### Hedge and softener clusters

- `it is important to note that` -> delete; state the fact
- `it is worth mentioning that` -> delete
- `notably` -> delete, or name what's notable
- `it's worth noting` -> delete
- `in many cases` -> often, or state the real proportion
- `generally speaking` -> delete, or name the exception directly
- `it can be argued that` -> delete; make the claim

### Filler openers and closers

- `in today's fast-paced world` -> delete
- `in conclusion` -> delete; end on the point itself
- `in summary` -> delete
- `to summarize` -> delete
- `it goes without saying` -> delete (then either say it, or don't)
- `needless to say` -> delete
- `at the end of the day` -> delete
- `at its core` -> delete, or name the core thing directly
- `under the hood` -> internally, in the implementation
- `simple enough on paper` -> delete, or state the actual gap

### Transition fingerprint

- `furthermore` -> delete, or "also"
- `moreover` -> delete, or "also"
- `it is clear that` -> delete; state the claim directly
- `this highlights` -> this shows
- `this underscores` -> this confirms
- `as previously mentioned` -> delete (don't repeat it, or say what changed)
- `it turns out that` -> delete; state the fact directly

### Significance inflation

- `stands as a testament to` -> shows, proves
- `marks a pivotal moment in` -> changed, started
- `indelible mark` -> lasting effect
- `evolving landscape` -> name what's actually changing
- `setting the stage for` -> leads to, makes possible
- `deeply rooted in` -> based on, comes from
- `plays a vital role` -> name why it matters
- `represents a shift in` -> changes

### Promotional register

- `nestled in the heart of` -> located in
- `in the heart of` -> in
- `breathtaking` -> delete; describe the actual thing
- `must-visit` -> worth visiting, or delete
- `stunning` -> delete; describe the actual thing
- `boasts a rich heritage` -> name the actual history
- `renowned for` -> known for
- `groundbreaking` (figurative) -> new, first of its kind -- and say why

### Quantifier inflation

- `a myriad of` -> many
- `a plethora of` -> many
- `in the realm of` -> in
- `the landscape of` (abstract) -> name the actual category

### Persuasive authority tropes

- `the real question is` -> delete; ask the actual question
- `what really matters` -> name what matters
- `fundamentally` -> delete, or state the claim directly
- `the deeper issue` -> name the issue
- `the heart of the matter` -> name the point directly

### Signposting and tutorial-voice scaffolding

- `let's dive in` -> delete
- `let's explore` -> delete
- `let's break this down` -> delete
- `here's what you need to know` -> delete
- `now let's look at` -> delete, or name the section directly
- `without further ado` -> delete
- `in this section we will` -> delete; state the content directly
- `this document will cover` -> delete, or give a one-line scope statement without "will cover"

### Acknowledgment and closing filler

- `great question` -> delete
- `that's an excellent point` -> delete
- `of course` -> delete
- `certainly` -> delete
- `i hope this helps` -> delete
- `let me know if you have any questions` -> delete, or name a real place to ask
- `whether X or Y` (as a clean binary opener) -> name the actual options, including any that aren't binary

---

## Part 2 -- six hard rules

1. **Em dashes (derived).** At most one per 300 words. Under 300 words, zero.
2. **Semicolons (derived).** None, unless a list item itself contains commas
   ("San Francisco, CA; Austin, TX; Portland, OR").
3. **Straight quotes and apostrophes only (derived).** Never curly. A curly
   quote or apostrophe anywhere in the text is a hit.
4. **Banned vocabulary (derived).** Anything on Part 1's list, above.
5. **No negation framing (derived).** "not just X", "not X, it's Y", "it's not
   about X, it's about Y", "more X than Y". Say what the thing IS instead of
   what it isn't.
6. **Sentence-length spread (derived).** In any passage over roughly 80 words,
   the longest sentence beats the shortest by 20 words or more, and fewer than
   half the sentences sit in the 10-to-20-word band.

**Word frequency is deliberately NOT a seventh hard rule.** It is a report-only
signal. A term of art recurs legitimately in technical writing, and cycling
through synonyms just to avoid repeating a term is itself a documentation tell
-- a reader trying to figure out whether "the config file" and "the settings
file" are the same thing is worse off than a reader who saw "the config file"
five times. The fix for a frequency hit is a named substitute at each specific
occurrence, or an explicit "keep: term of art" -- never a blanket cap on how
often a word may appear.

---

## Part 3 -- eight documentation-register rewrite levers

These are original to this skill: aimed at technical and process documentation
specifically, not at essays, marketing, or fiction.

1. **Say the number or the name instead of the abstraction.** A reader can
   check a number; they cannot check "significant."
   - Before: "The build got significantly faster after the change."
   - After: "The build dropped from 40 seconds to 6 seconds."

2. **One claim per sentence.** A sentence carrying two claims makes both harder
   to check, and hides which one a later edit actually addressed.
   - Before: "The script handles both cases and is also faster than the old one, which used a different algorithm."
   - After: "The script handles both cases. It also runs faster, because it uses a different algorithm than the old one."

3. **Name the actor.** "It fails" and "the file gets deleted" hide who or what
   is responsible; a reader troubleshooting needs the actor, not the passive
   voice.
   - Before: "The config is regenerated on every run."
   - After: "`build.py` regenerates the config on every run."

4. **Cut the hedge, or keep it once with a reason.** "Generally" and "in most
   cases" without a stated exception are noise; if the exception matters, name
   it instead of hedging around it.
   - Before: "This generally works, though results can vary."
   - After: "This works for files under 10MB. Larger files time out (see the size limit below)."

5. **Delete signposting.** "In this section we will..." tells the reader
   nothing they don't get from the heading itself.
   - Before: "In this section, we will walk through how to configure the tool."
   - After: "Configure the tool by editing `config.yaml`."

6. **Vary sentence length on purpose.** A run of same-length sentences reads
   as a checklist even when the content isn't one; break it up so the emphasis
   lands where it should.
   - Before: "The script reads the file. It parses each line. It checks the count. It writes the result."
   - After: "The script reads the file and parses each line. Then it checks the count and writes the result."

7. **Prefer the plain verb.** "Supersedes", "utilizes", and "facilitates" are
   not wrong, but the plain verb is faster to read and just as accurate.
   - Before: "This version supersedes the previous release."
   - After: "This version replaces the previous release."

8. **End when the point is made.** A reflexive closing paragraph that restates
   what the section just said adds length without adding information.
   - Before: "...and that's how the retry logic works. In summary, retries are handled automatically and the user doesn't need to intervene."
   - After: "...and that's how the retry logic works."

---

## Part 4 -- checklist for what the scanner cannot catch

`voice_scan.py` counts words, phrases, and patterns it can express as a regex
or a threshold. It cannot judge these; apply them by reading the flagged
passage and its surrounding paragraph:

- **Hedge stacking.** Two or three softeners in one sentence ("it's generally
  fairly common in most cases"), where any single one would pass unnoticed but
  the pile-up reads as evasive.
- **Tricolons.** A three-item rhythmic list with matching grammar ("faster,
  cleaner, and more reliable"), especially escalating in weight -- a rhetorical
  pattern, not a factual one.
- **Signposting openers.** "In this section, we will..." style openers that
  the vocabulary list doesn't catch verbatim but that do the same job.
- **Reflexive summaries at section ends.** A closing paragraph that restates
  the section's content rather than adding to it (Lever 8 above is the fix;
  this is the thing to look for).
- **Unassigned "it" / "this".** A pronoun where the reader has to scroll back
  to figure out what it refers to, especially across a paragraph break.
- **Uniform paragraph length.** Every paragraph running three to four sentences
  of similar length reads as templated even when the sentence-length spread
  check (hard rule 6) passes within each one.

---

## Part 5 -- the rewrite-then-rescan gate

After rewriting a flagged passage with the levers in Part 3, re-run
`voice_scan.py` on the result and show the before and after counts side by
side. A rewrite that does not move the numbers is reported as exactly that --
not declared done because the prose reads better to whoever wrote it.

Rewrites under this gate change expression only. Any factual content in the
passage -- a count, a claim, a cross-reference -- is checked against its
source the same way any other correctness finding is, and that check is
separate from this gate.
