#!/usr/bin/env python3
"""Render a text file into a plain, line-numbered HTML review page.

The output page shows the source file's own bytes - decoded as UTF-8 and
HTML-escaped, nothing else - so a person can leave line-anchored comments
against it and the page can never drift from the file it was rendered
from. This script does not render Markdown or any other markup: it always
shows the raw source, one numbered line at a time.

Usage:
    python render_review_page.py <path> [--out <file>]

If --out is omitted, the output is written to the system temp directory
as "<source filename>.review.html". The output path is printed to
stdout on success.

Standard library only - no third-party imports.
"""

import argparse
import codecs
import datetime
import os
import subprocess
import sys
import tempfile

LINE_BREAK = "\n"


def escape_html(text):
    """Escape only '&', '<', '>' - the minimum needed for safe, literal display.

    Quotes are deliberately left alone: this text is never used as an
    HTML attribute value, only as element content, so escaping quotes
    would just make the on-page text differ from the source for no
    safety benefit.
    """
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def split_into_lines(text):
    """Split decoded text into display lines, matching editor/`` nl `` numbering.

    A line break is a bare "\\n" or a "\\r\\n" pair - never a lone "\\r" -
    so a CRLF file numbers identically to what its author sees in an
    editor (and to a tool like `` nl -ba ``, which also only breaks on
    "\\n"). Any carriage return that is not immediately followed by a
    line feed is left in place as ordinary line content, preserving the
    file's own line endings rather than normalizing them away.

    A trailing line break at end of file ends the last real line; it
    must not produce an extra, phantom, empty numbered line after it.
    """
    if text == "":
        return []

    lines = []
    current = []
    i = 0
    length = len(text)
    while i < length:
        ch = text[i]
        if ch == LINE_BREAK:
            lines.append("".join(current))
            current = []
            i += 1
        elif ch == "\r" and i + 1 < length and text[i + 1] == LINE_BREAK:
            lines.append("".join(current))
            current = []
            i += 2
        else:
            current.append(ch)
            i += 1

    if current:
        lines.append("".join(current))

    return lines


def compute_git_blob_hash(path):
    """Return the git blob hash for a tracked file, or None if unavailable.

    Never raises: git not being installed, the file living outside any
    repository, the file being untracked, or git erroring for any other
    reason are all treated the same way - no hash available - rather
    than a fatal error.
    """
    directory = os.path.dirname(os.path.abspath(path)) or "."
    filename = os.path.basename(path)

    try:
        inside = subprocess.run(
            ["git", "-C", directory, "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if inside.returncode != 0 or inside.stdout.strip() != "true":
            return None

        tracked = subprocess.run(
            ["git", "-C", directory, "ls-files", "--error-unmatch", "--", filename],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if tracked.returncode != 0:
            return None

        result = subprocess.run(
            ["git", "-C", directory, "hash-object", "--", filename],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return None

        blob_hash = result.stdout.strip()
        return blob_hash or None
    except (OSError, subprocess.SubprocessError):
        return None


PAGE_TEMPLATE = """<title>{title}</title>
<style>
:root {{
  --bg: #ffffff;
  --text: #1a1a1a;
  --muted: #5f6672;
  --border: #d8dbe0;
  --gutter-bg: #f3f4f6;
  --gutter-text: #8a8f98;
  --header-bg: #f6f7f9;
}}

@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    --bg: #1b1d22;
    --text: #e6e8eb;
    --muted: #9aa0aa;
    --border: #33363d;
    --gutter-bg: #232529;
    --gutter-text: #6d7280;
    --header-bg: #202226;
  }}
}}

:root[data-theme="dark"] {{
  --bg: #1b1d22;
  --text: #e6e8eb;
  --muted: #9aa0aa;
  --border: #33363d;
  --gutter-bg: #232529;
  --gutter-text: #6d7280;
  --header-bg: #202226;
}}

body {{
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font-family: -apple-system, "Segoe UI", Helvetica, Arial, sans-serif;
}}

.review-header {{
  padding: 14px 20px;
  background: var(--header-bg);
  border-bottom: 1px solid var(--border);
  font-size: 13px;
  color: var(--muted);
}}

.review-header .field {{
  margin: 2px 0;
}}

.review-header .field strong {{
  color: var(--text);
}}

.review-header code {{
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  color: var(--text);
}}

.review-scroll {{
  overflow-x: auto;
  max-width: 100%;
}}

table.review-table {{
  border-collapse: collapse;
  width: max-content;
  min-width: 100%;
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  font-size: 13px;
  line-height: 1.5;
}}

table.review-table td {{
  padding: 0 10px;
  vertical-align: top;
  white-space: pre;
}}

td.gutter {{
  user-select: none;
  -webkit-user-select: none;
  -moz-user-select: none;
  text-align: right;
  color: var(--gutter-text);
  background: var(--gutter-bg);
  border-right: 1px solid var(--border);
  position: sticky;
  left: 0;
}}

td.code {{
  color: var(--text);
}}
</style>
<div class="review-header">
{header_fields}
</div>
<div class="review-scroll">
<table class="review-table">
<tbody>
{rows}
</tbody>
</table>
</div>
"""


def render_page(source_path, lines, blob_hash, timestamp, normalizations):
    """Build the full page markup (title, style, header, numbered body)."""
    filename = os.path.basename(source_path)
    title = "Review: {}".format(escape_html(filename))

    header_fields = [
        '<div class="field"><strong>Source:</strong> <code>{}</code></div>'.format(
            escape_html(source_path)
        ),
    ]
    if blob_hash:
        header_fields.append(
            '<div class="field"><strong>Git blob hash:</strong> <code>{}</code></div>'.format(
                escape_html(blob_hash)
            )
        )
    header_fields.append(
        '<div class="field"><strong>Rendered:</strong> {}</div>'.format(
            escape_html(timestamp)
        )
    )
    header_fields.append(
        '<div class="field"><strong>Lines:</strong> {}</div>'.format(len(lines))
    )
    normalization_text = ", ".join(normalizations) if normalizations else "none"
    header_fields.append(
        '<div class="field"><strong>Normalization:</strong> {}</div>'.format(
            escape_html(normalization_text)
        )
    )

    rows = []
    for line_number, line in enumerate(lines, start=1):
        rows.append(
            '<tr id="L{n}"><td class="gutter">{n}</td><td class="code">{content}</td></tr>'.format(
                n=line_number, content=escape_html(line)
            )
        )

    return PAGE_TEMPLATE.format(
        title=title,
        header_fields="\n".join(header_fields),
        rows="\n".join(rows),
    )


def build_arg_parser():
    parser = argparse.ArgumentParser(
        prog="render_review_page.py",
        description=(
            "Render a text file into a plain, line-numbered HTML page for "
            "line-anchored review comments. Shows the raw source only - "
            "never renders Markdown or any other markup."
        ),
    )
    parser.add_argument("path", help="path to the text file to render")
    parser.add_argument(
        "--out",
        dest="out",
        default=None,
        help=(
            "output HTML file path (default: system temp directory, named "
            "after the source file with '.review.html' appended)"
        ),
    )
    return parser


def main(argv=None):
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    source_path = args.path

    if not os.path.isfile(source_path):
        print("error: not a file: {}".format(source_path), file=sys.stderr)
        return 1

    try:
        with open(source_path, "rb") as f:
            raw_bytes = f.read()
    except OSError as exc:
        print("error: could not read {}: {}".format(source_path, exc), file=sys.stderr)
        return 1

    normalizations = []
    if raw_bytes.startswith(codecs.BOM_UTF8):
        raw_bytes = raw_bytes[len(codecs.BOM_UTF8):]
        normalizations.append("UTF-8 BOM stripped")

    try:
        text = raw_bytes.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        print(
            "error: {} is not valid UTF-8 ({}); refusing to guess an "
            "encoding or silently replace characters".format(source_path, exc),
            file=sys.stderr,
        )
        return 1

    lines = split_into_lines(text)
    blob_hash = compute_git_blob_hash(source_path)
    timestamp = datetime.datetime.now().astimezone().isoformat(timespec="seconds")

    page = render_page(
        source_path=source_path,
        lines=lines,
        blob_hash=blob_hash,
        timestamp=timestamp,
        normalizations=normalizations,
    )

    out_path = args.out
    if out_path is None:
        out_path = os.path.join(
            tempfile.gettempdir(), os.path.basename(source_path) + ".review.html"
        )

    try:
        with open(out_path, "w", encoding="utf-8", newline="") as f:
            f.write(page)
    except OSError as exc:
        print("error: could not write {}: {}".format(out_path, exc), file=sys.stderr)
        return 1

    print(out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
