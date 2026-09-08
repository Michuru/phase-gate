# Finding categories

This is the checklist a reviewer works a document against, one pass for correctness and one for clarity. It exists so two different reviewers converge on the same vocabulary instead of each inventing their own labels, and so nothing gets missed just because it doesn't happen to have a name in the reviewer's head.

**Correctness (A) findings are claims about the world that can be checked against a source** — a count, a path, a command, a stated reason something works. An A finding is only real once it's been checked against that source; never mark one confirmed on the strength of the prose alone.

**Clarity (B) findings are about whether an actual reader, reading in order, can follow the document and do what it asks.** A B finding doesn't need a second source to check — the document itself, read cold, is the only evidence needed. Something can be entirely true and still be a clarity defect if a reader can't find it, can't parse it, or reasonably reads it two different ways.

**Policy (C) findings are neither** — a document can be accurate and perfectly clear and still contain something that shouldn't ship as written.

Use the ids (A1, B14, C2, …) to tag findings so they're traceable back to this list.

## A — correctness

**A1. False rationale** — a stated reason *why* a mechanism works is untrue, even though the mechanism itself is fine. *Example:* a setup guide claims a cache clears automatically on logout, when logging out never actually touches the cache.
**A2. Stale-claim propagation** — a wrong claim found in one file survives, word for word, in every other document that copied it. *Example:* a retired API's rate limit is repeated unchanged in three guides after the limit changed.
**A3. Inventory error** — a roster claims N items and ships M, or a whole feature is missing from a list claiming to be complete. *Example:* a README says "twelve plugins" and the plugins folder holds thirteen.
**A4. Count inconsistency** — the same document states two or three different numbers for the same thing. *Example:* the intro says "five steps" and the numbered list below it has six.
**A5. Contradicting instructions** — two different sources are named for the same input, and following the narrower one silently drops real data. *Example:* one section says configuration comes from a single file, another says it comes from a folder of files, and only the file is actually read.
**A6. Label/list mismatch** — a counting word doesn't match the list next to it. *Example:* "all four regions" followed by a list of five region names.
**A7. False default** — asserts a setting is on, or a capability is available, when it isn't. *Example:* "logging is enabled by default" when the shipped config has logging turned off.
**A8. Mechanism misidentified** — the reader ends up with the wrong mental model of what actually executes. *Example:* a doc calls a rule-based filter "the AI" when no model is involved anywhere in that step.
**A9. Command that silently misbehaves** — a copy-pasteable command runs, exits cleanly, and produces the wrong result. *Example:* a documented `move` command actually nests the folder inside itself instead of moving it, with no error printed.
**A10. Unsupported overclaim** — an assertion with no source behind it, often superlative or comparative. *Example:* "the fastest tool in its category," cited nowhere.
**A11. Version-dependent fact asserted as stable** — a menu label, version number, or environment detail is stated flatly when it will drift. *Example:* "click Settings > Advanced" for a menu that was renamed two releases ago.
**A12. Misassigned authority** — the document names the wrong artifact as the one that actually grants a permission. *Example:* a guide says a role grants write access when the real grant comes from a separate group membership.
**A13. Diagram/text mismatch** — a figure, table, or alt-text disagrees with the prose next to it, and readers trust the picture. *Example:* a flowchart shows step 3 looping back to step 1, but the prose says step 3 ends the process.
**A14. Broken pointer** — a link or "see section X" resolves somewhere that doesn't answer the question it was cited for. *Example:* "see Troubleshooting" links to a section that only covers installation.
**A15. Self-contradicting targets** — two stated goals or limits that cannot both hold at once. *Example:* "must run offline" and "requires a live connection to the licensing server" in the same requirements list.
**A16. Status line over an unfilled deliverable** — a "done" marker closes an item whose stated deliverable was never actually produced. *Example:* a changelog marks "test suite added — done" with no test files anywhere in the repository.

## B — clarity

**B1. Buried disclosure** — a fact the reader needs in order to consent is hidden mid-sentence or in a parenthetical. *Example:* "the tool syncs your files (to a third-party server)" tucked at the end of an unrelated paragraph.
**B2. Late scope qualifier** — the reader gets deep into a document before learning it doesn't apply to them. *Example:* page four reveals the whole guide only applies to the paid tier.
**B3. Warning in a skipped section** — a caution sits in a section the document itself tells most readers to skip. *Example:* the one warning about data loss is in "Advanced options," which the intro tells beginners to ignore.
**B4. Deferred discovery** — facts about a topic are only learnable from an unrelated later section. *Example:* the real disk-space requirement only appears inside a troubleshooting entry about a failed install.
**B5. Unexplained jargon** — a term of art is used before it's defined, with no glossary. *Example:* "enable idempotent mode" appears in step one with no explanation anywhere in the document.
**B6. Naming collision** — one word is used for two different things in the same document. *Example:* "project" means both the whole repository and a single config file, depending on the section.
**B7. Names-only inventory** — a list of bare names with no one-line description of what each one does. *Example:* a features list that's just eight product names with nothing beside them.
**B8. Missing worked example** — the document explains a process but never shows one running start to finish. *Example:* an API guide describes every parameter but never shows one complete request and response.
**B9. Missing section** — a section a reader of this genre expects is simply absent. *Example:* an install guide with no uninstall instructions anywhere.
**B10. Missing prerequisite step** — a later command assumes state that no earlier step established. *Example:* step four references a config file that no earlier step told the reader to create.
**B11. Requirement without owner or check** — a requirement is stated without saying what needs it or how to verify it's met. *Example:* "the port must be open" with no statement of which service needs it or how to confirm it is.
**B12. Buried hard requirement** — a genuine prerequisite is mentioned in passing prose instead of stated as a requirement with instructions. *Example:* "you'll also want an account with admin rights" dropped into a sentence about something else, with no setup steps.
**B13. Cross-section duplication** — the same fact is stated in two or more places, free to drift apart over time. *Example:* the supported version number is stated once in the intro and again in an appendix, and only one gets updated at the next release.
**B14. Inconsistent restatement** — the same thing is described differently in different places, and the reader can't tell which is authoritative. *Example:* one section calls a step optional, another calls the same step required.
**B15. Unstated negative behavior** — the document never says what will NOT happen, which is exactly the reader's actual question. *Example:* a migration guide never says whether old data is deleted or kept.
**B16. Apparently conflicting rules** — two rules a reader will read as contradicting each other, with no reconciliation offered. *Example:* "always back up before running this" next to "this command is always safe to run," with nothing explaining when each applies.
**B17. Missing orienting fact** — a basic "where does this live / what is this for" fact is never stated anywhere. *Example:* a script's own header never says what triggers it or where its output goes.
**B18. Audience mismatch** — the document addresses a different reader than the one actually holding it, or wobbles between audiences section to section. *Example:* an end-user quick start suddenly assumes the reader can read source code halfway through.
**B19. Local lesson framed as law** — a hard-won lesson from one narrow context is presented as a universal truth. *Example:* "always use this specific tool" stated flatly, when it was only chosen because of one team's particular constraint.
**B20. Mislabeled section** — a heading names something other than what the section actually contains. *Example:* a section titled "Configuration" that's actually a list of known bugs.
**B21. Wrong lead order** — the thing a reader does first isn't presented first. *Example:* the one required setup command appears on the last page after several optional ones.
**B22. Execution-context ambiguity** — the reader can't tell where a command is meant to run. *Example:* a snippet with no indication whether it runs in a terminal, inside an application's console, or in a browser address bar.
**B23. The differentiating idea absent** — the one thing that actually makes this approach different from the obvious alternative is never stated. *Example:* a tool's pitch never says what it does that a plain script couldn't.
**B24. The plainest objection unaddressed** — the first question a skeptical reader would ask has no answer anywhere in the document. *Example:* a pitch for a new process never says what happens when someone forgets to follow it.
**B25. Untranslatable term** — a term resists plain-language explanation and is used anyway with no plan for a reader who lacks the background. *Example:* a glossary entry that just restates the term in slightly different jargon instead of explaining it.
**B26. Unassigned actor** — the reader can't tell who or what performs an action, because the sentence never says. *Example:* "the file gets cleaned up automatically," with no statement of what process does the cleaning or when.
**B27. Multi-point intro or closing** — an opening or closing section carries several distinct points where it should carry one. *Example:* a summary paragraph that tries to restate five separate findings at once instead of pointing to them.
**B28. Additive summary** — a new summary, table, or diagram is added alongside the detailed text it makes redundant, instead of replacing it. *Example:* a status table added above a paragraph that already states the same numbers, so the two can now disagree.

## C — policy

**C1. Comparison that shouldn't be public** — a named comparison to a third party that was fine as internal research but shouldn't appear in a published document. *Example:* a draft that names a specific competitor's pricing, left in by accident when the document went public.
**C2. Unstated commit or install assumption** — the document is silent about something it will permanently add to a reader's own repository or machine. *Example:* a "quick start" that installs a service to run at every startup, with no mention that it's permanent until the reader notices it later.

## Boundary

This checklist does not cover word-level voice tells or prose rewriting — a sibling reference file in this same skill handles that. It does not score how AI-written a text sounds. And it does not cover code review: nothing here is about whether code is correct, only whether a document's own words are correct and clear.
