# Publish and Comments

## Rendering the page

The renderer is `scripts/render_review_page.py`. Invocation: `python scripts/render_review_page.py <path>` with optional `--out <file>`. It prints the output path.

Output is an HTML page whose body is the source file's own bytes—HTML-escaped, in a numbered monospace block. No Markdown rendering. The header carries the source path, the git blob hash when the file is tracked, the render time, the line count, and any normalization applied (stripped UTF-8 byte order mark).

Bytes instead of rendered output ensures a line number in a comment means the same line in the file. Rendered pages and their sources drift; byte-for-byte output cannot.

## Publishing

Publish the rendered file with the `Artifact` tool, passing the rendered `.html` path as `file_path`. Give it a `favicon` on first publish (one or two emoji) and a one-sentence `description`.

Record the returned URL in two places: the response to the author, and a sidecar file named `<doc>.review-url` beside the reviewed document, containing just the URL.

Suggest the author add `*.review-url` to their ignore file if they do not want sidecars tracked.

## Republishing after edits

After any edit pass, re-run the renderer on the changed file and publish again with the same `file_path` used the first time. Same path means same URL. A different path claims a new URL and strands every existing comment thread.

Before the first republish in a new session, call the `Artifact` tool with `action: "read"` and the recorded URL. A publish to an artifact the current conversation has neither read nor published is refused. Reading it first surfaces any version published from elsewhere since.

If the sidecar is missing or its URL no longer resolves, call `action: "list"` and match on the artifact title, which the renderer derives from the source filename. Ask the author to confirm the match before publishing over it.

## Working the comment threads

1. Call `action: "comments"` with the URL to read the threads. Each thread reports whether a person has activated it for Claude.
2. For each thread: quote the comment, then locate the exact text it refers to in the source file.
3. Verify each suggestion against the source file—re-open it and read the actual sentence before changing anything. Decide: apply, reword, or reject.
4. Edit the source file, not the rendered page. The page is regenerated from the file.
5. Reply with `action: "reply"`, passing the thread id and plain text saying which of the three happened. For a reword or reject, cite the line that settled it. Replies land only on threads activated for Claude; an unactivated thread returns guidance rather than an error.
6. Mark a thread `action: "resolve"` only once it is actually dealt with, and only when it is activated for Claude. Never resolve a thread you did not act on.
7. Re-render and republish once the pass is done.

## What to report at the end of a pass

Report a tally: threads handled, applied, reworded, rejected.

List the reworded and rejected ones explicitly, each with the source line that settled it. These are the most valuable output of the whole loop, not an exception report—in the review cycle this skill was built from, three requested edits were wrong once checked, and one would have deleted half of a two-condition rule while looking like a simple word swap.

List any thread that could not be replied to because it was not activated for Claude, noting that a person with write access must send it to Claude before this skill can answer in the thread.

## Two things this loop must never do

Never treat a review interface's own acknowledgement as evidence an edit was right. An automatic "applied" confirmation says a message was received, not that the change was correct.

Never publish a document the reviewing session has not read in full. Publishing distributes content.
