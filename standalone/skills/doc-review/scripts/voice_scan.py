#!/usr/bin/env python3
"""Count document-level voice tells in one or more text files.

Standard library only -- no third-party imports.

This script implements the Pass C voice scan: word and phrase frequency,
hits against the vocabulary list in ../references/voice-tells.md, punctuation
density, negation-framing patterns, sentence-length spread, and a cross-file
check for near-verbatim repeated sentences.

The vocabulary list is parsed from voice-tells.md at runtime rather than
duplicated here, so the two files cannot drift apart.

Usage:
    python voice_scan.py <path> [<path>...] [--threshold N] [--top N] [--raw-floor N] [--json] [--show-stoplist]

--threshold N   overrides the per-1,000-word rate floor for single-word hits
                (default 2.0). Does not change the raw-count floor.
--top N         how many entries the generic frequency scan reports per file
                (default 20). Vocabulary-list hits are always reported in full.
--raw-floor N   overrides RAW_FLOOR_WORD/RAW_FLOOR_PHRASE for vocabulary-list
                hits only (default: the built-in floors, 4 and 3). At the
                default floor the vocabulary check cannot fire at all on
                typical review-length prose (~150-300 words) -- confirmed
                empirically, see perf-review-assistant's design review
                finding 1. Pass a lower floor (e.g. 1) for short documents.
--json          machine-readable output instead of the default text report.
--show-stoplist print the in-script stop-list and exit.

Programmatic use (no file, no path, no tempfile -- for a caller scanning an
in-memory string, e.g. a not-yet-saved draft):
    from voice_scan import scan_text
    result = scan_text(my_text, raw_floor=1)
"""

import argparse
import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Raw-occurrence floor for a single word to be reported (frequency scan and
# vocabulary-list hits alike).
RAW_FLOOR_WORD = 4
# Default per-1,000-word rate floor for a single word. Overridden by --threshold.
DEFAULT_RATE_FLOOR = 2.0
# Raw-occurrence floor for a multi-word phrase (2 words or more).
RAW_FLOOR_PHRASE = 3

# A short stop-list: articles, prepositions, pronouns, auxiliaries, and a
# handful of the most common verbs. Words on this list never appear as
# generic-frequency hits (they would dominate every document). Vocabulary-list
# entries are matched regardless of this list, since a hit there is already a
# deliberate, curated flag rather than an accident of English's own frequency.
STOP_WORDS = {
    "a", "an", "the", "and", "or", "but", "nor", "so", "yet",
    "in", "on", "at", "by", "for", "with", "about", "against", "between",
    "into", "through", "during", "before", "after", "above", "below",
    "to", "from", "up", "down", "of", "off", "over", "under", "out",
    "again", "further", "then", "once", "here", "there", "when", "where",
    "why", "how", "all", "any", "both", "each", "few", "more", "most",
    "other", "some", "such", "no", "not", "only", "own", "same", "than",
    "too", "very", "as", "if", "because", "while", "until", "although",
    "i", "me", "my", "mine", "we", "us", "our", "ours",
    "you", "your", "yours", "he", "him", "his", "she", "her", "hers",
    "it", "its", "they", "them", "their", "theirs", "this", "that",
    "these", "those", "who", "whom", "whose", "which", "what",
    "am", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "having", "do", "does", "did", "doing",
    "will", "would", "shall", "should", "can", "could", "may", "might",
    "must", "ought", "one", "also", "just", "get", "gets", "got",
    "make", "makes", "made", "use", "used", "using",
}

WORD_TOKEN_RE = re.compile(r"[A-Za-z]+(?:['\-][A-Za-z]+)*")
HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s")
FENCE_RE = re.compile(r"^\s*(```+|~~~+)")
URL_RE = re.compile(r"\b\w+://\S+|\bwww\.\S+", re.IGNORECASE)
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
PATH_TOKEN_RE = re.compile(r"\S*[\\/]\S*")
CAMEL_RE = re.compile(r"[a-z][A-Z]")
CURLY_QUOTE_CHARS = "“”‘’"
EM_DASH = "—"
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")

NEGATION_PATTERNS = [
    ("not just X", re.compile(r"\bnot just\b", re.IGNORECASE)),
    (
        "not X, it's Y",
        re.compile(r"\bnot\b[^.!?]{0,60}?,\s*it'?s\b", re.IGNORECASE),
    ),
    (
        "isn't about X, it's about Y",
        re.compile(r"\bisn'?t about\b[^.!?]{0,60}?\bit'?s about\b", re.IGNORECASE),
    ),
    # Targets the rhetorical "more a X than a Y" pivot, not ordinary comparatives.
    # Requires an article or determiner after "more", which "more than" and
    # "more useful than" (a plain comparison) do not have.
    (
        "more X than Y",
        re.compile(
            r"\bmore\b\s+(?:a|an|the|of)\b[^.!?]{0,40}?\bthan\b",
            re.IGNORECASE,
        ),
    ),
]


# ---------------------------------------------------------------------------
# Vocabulary-list parsing (from references/voice-tells.md)
# ---------------------------------------------------------------------------

# The optional non-capturing group tolerates a human-readable qualifier
# between the term and the arrow, e.g. "`leverage` (verb) -> use" -- without
# it, every entry carrying one of these silently fails to match and is
# dropped from the scanned vocabulary list entirely (confirmed: 12 of 94
# entries, including `leverage`, `highlight`, `landscape`, `additionally`).
VOCAB_ENTRY_RE = re.compile(r"^-\s*`([^`]+)`(?:\s*\([^)]*\))?\s*->\s*(.+?)\s*$")


def load_vocab_list(script_path):
    """Parse Part 1 of references/voice-tells.md into [(term, substitute), ...].

    Reads the sibling references/voice-tells.md file relative to this script,
    so the vocabulary list is never duplicated in this file. Returns an empty
    list (with a warning on stderr) if the reference file cannot be found or
    parsed, rather than falling back to a hardcoded copy.
    """
    ref_path = script_path.resolve().parent.parent / "references" / "voice-tells.md"
    if not ref_path.is_file():
        print(
            "warning: could not find references/voice-tells.md next to this "
            "script; vocabulary-list hits will not be reported.",
            file=sys.stderr,
        )
        return []

    text = ref_path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    in_part1 = False
    entries = []
    for line in lines:
        stripped = line.strip().lower()
        if stripped.startswith("## part 1"):
            in_part1 = True
            continue
        if stripped.startswith("## part 2"):
            break
        if not in_part1:
            continue
        match = VOCAB_ENTRY_RE.match(line)
        if match:
            term, substitute = match.group(1), match.group(2)
            entries.append((term, substitute))
    return entries


# ---------------------------------------------------------------------------
# Line-level classification and cleaning
# ---------------------------------------------------------------------------


def classify_lines(lines):
    """Return a list of per-line tags: one of

    'frontmatter', 'fence', 'table', 'heading', 'prose'

    Frontmatter, fenced code blocks, and table rows are removed entirely
    before counting anything. Headings count toward the document's total
    word count but are exempt from producing tells. Everything else is
    ordinary prose.
    """
    tags = [None] * len(lines)

    # YAML frontmatter: a leading '---' line, up to the next bare '---' line.
    idx = 0
    if idx < len(lines) and lines[idx].strip() == "---":
        tags[idx] = "frontmatter"
        idx += 1
        while idx < len(lines) and lines[idx].strip() != "---":
            tags[idx] = "frontmatter"
            idx += 1
        if idx < len(lines):
            tags[idx] = "frontmatter"
            idx += 1

    in_fence = False
    for i in range(idx, len(lines)):
        line = lines[i]
        if FENCE_RE.match(line):
            tags[i] = "fence"
            in_fence = not in_fence
            continue
        if in_fence:
            tags[i] = "fence"
            continue
        if is_table_row(line):
            tags[i] = "table"
            continue
        if HEADING_RE.match(line):
            tags[i] = "heading"
            continue
        tags[i] = "prose"

    return tags


def is_table_row(line):
    """A line whose content is dominated by '|' -- a Markdown table row or
    its separator ('|---|---|', ':---:' style)."""
    stripped = line.strip()
    if not stripped:
        return False
    if re.fullmatch(r"[\s|:\-]+", stripped):
        return True
    return stripped.count("|") >= 2


def clean_line(line):
    """Strip inline code spans, URLs, and file-path-like tokens from one line,
    replacing each with a single space so word boundaries survive. Returns
    the cleaned line, ready for word/phrase tokenization."""
    line = INLINE_CODE_RE.sub(" ", line)
    line = URL_RE.sub(" ", line)
    line = PATH_TOKEN_RE.sub(" ", line)
    return line


# ---------------------------------------------------------------------------
# Per-file scan
# ---------------------------------------------------------------------------


class FileScan:
    """Holds every intermediate structure needed to answer the checks for one
    file: raw lines, per-line tags, the prose text used for tells, and the
    running word count."""

    def __init__(self, path=None, *, text=None, source_name=None):
        """Either `path` (a Path, read from disk) or `text` (a raw string,
        scanned in memory -- no file touched) must be given, not both.
        `source_name` labels an in-memory scan in reports; ignored for a
        path-based scan, which always labels itself with the real path."""
        if (path is None) == (text is None):
            raise ValueError("FileScan needs exactly one of path or text")

        if path is not None:
            self.path = path
            raw = path.read_text(encoding="utf-8", errors="replace")
            # A leading BOM, if present, is invisible after decode with
            # utf-8-sig; re-read that way so it never shows up as a stray
            # character.
            try:
                raw = path.read_text(encoding="utf-8-sig")
            except UnicodeDecodeError:
                pass
        else:
            self.path = source_name or "<string>"
            # Strip a leading BOM, matching the path branch above -- without
            # this, a BOM-prefixed heading line misclassifies as "prose"
            # (HEADING_RE's anchor no longer matches at position 0), which
            # wrongly exposes it to vocabulary-list hits. Confirmed live
            # (code-reviewer QA pass, task 5): a BOM-prefixed "# ... robust
            # and comprehensive heading" fired 2 vocab hits; without the BOM
            # it correctly fired 0.
            raw = text.lstrip(chr(0xFEFF)) if text else text

        self.lines = raw.splitlines()
        self.tags = classify_lines(self.lines)

        self.total_word_count = 0
        # (word, line_number) for words eligible to produce tells: prose
        # lines only, proper nouns and code identifiers excluded.
        self.tell_words = []
        # cleaned prose text per prose line number, for phrase/pattern search
        # and punctuation counting.
        self.prose_by_line = {}

        self._build()

    def _build(self):
        at_sentence_start = True
        for i, line in enumerate(self.lines, start=1):
            tag = self.tags[i - 1]
            if tag in ("frontmatter", "fence", "table"):
                continue

            cleaned = clean_line(line)

            if tag == "heading":
                # Headings count toward the total word count but never
                # produce tells, and they reset sentence-start tracking
                # for whatever prose follows.
                self.total_word_count += len(cleaned.split())
                at_sentence_start = True
                continue

            # tag == 'prose'
            if not cleaned.strip():
                # Blank line: paragraph break, resets sentence-start state.
                at_sentence_start = True
                continue

            self.total_word_count += len(cleaned.split())
            self.prose_by_line[i] = cleaned

            for tok in WORD_TOKEN_RE.finditer(cleaned):
                word = tok.group(0)
                is_sentence_start = at_sentence_start and tok.start() == 0
                # Recompute sentence-start based on whatever text precedes
                # this token on the line (cheap: check the char right before).
                if tok.start() > 0:
                    preceding = cleaned[: tok.start()]
                    is_sentence_start = bool(re.search(r"[.!?]\s*$", preceding)) or (
                        at_sentence_start and not preceding.strip()
                    )
                exempt = False
                if word[0].isupper() and not is_sentence_start:
                    exempt = True  # proper noun
                elif CAMEL_RE.search(word):
                    exempt = True  # internal CamelCase code identifier
                if not exempt:
                    self.tell_words.append((word.lower(), i))
            # Update sentence-start state for the next line based on the
            # end of this one.
            at_sentence_start = bool(re.search(r"[.!?]\s*$", cleaned.rstrip()))

    # -- checks -------------------------------------------------------

    def word_frequency(self, threshold, top_n):
        """Generic single-word and 2-3 word phrase frequency, excluding the
        stop-list. Returns a list of hit dicts sorted by count descending,
        capped at top_n."""
        counts = {}
        lines_by_word = {}
        for word, lineno in self.tell_words:
            if word in STOP_WORDS:
                continue
            counts[word] = counts.get(word, 0) + 1
            lines_by_word.setdefault(word, []).append(lineno)

        hits = []
        total = max(self.total_word_count, 1)
        for word, count in counts.items():
            rate = count / total * 1000
            if count >= RAW_FLOOR_WORD and rate >= threshold:
                hits.append(
                    {
                        "term": word,
                        "count": count,
                        "rate_per_1000": round(rate, 2),
                        "lines": sorted(set(lines_by_word[word])),
                    }
                )

        # 2- and 3-word phrases from the same tell-eligible word stream,
        # built per contiguous run (a run breaks whenever a word was
        # excluded, e.g. a proper noun sat between them).
        phrase_counts = {}
        phrase_lines = {}
        seq = self.tell_words
        for n in (2, 3):
            for i in range(len(seq) - n + 1):
                words = [seq[i + k][0] for k in range(n)]
                lines_ = [seq[i + k][1] for k in range(n)]
                if all(w in STOP_WORDS for w in words):
                    continue
                # Require contiguity: consecutive tell_words entries came
                # from adjacent tokens only if their line numbers are equal
                # or increase by at most a couple of lines (words wrap).
                if lines_[-1] - lines_[0] > 1:
                    continue
                phrase = " ".join(words)
                phrase_counts[phrase] = phrase_counts.get(phrase, 0) + 1
                phrase_lines.setdefault(phrase, []).append(lines_[0])

        for phrase, count in phrase_counts.items():
            if count >= RAW_FLOOR_PHRASE:
                hits.append(
                    {
                        "term": phrase,
                        "count": count,
                        "rate_per_1000": round(count / total * 1000, 2),
                        "lines": sorted(set(phrase_lines[phrase])),
                    }
                )

        hits.sort(key=lambda h: h["count"], reverse=True)
        return hits[:top_n]

    def vocab_hits(self, vocab_list, threshold, raw_floor_word=None, raw_floor_phrase=None):
        """Hits against references/voice-tells.md's Part 1, matched literally
        (case-folded, no stemming) against prose text only.

        raw_floor_word/raw_floor_phrase override RAW_FLOOR_WORD/
        RAW_FLOOR_PHRASE for this call only, when given -- see scan_text()'s
        raw_floor parameter and the module docstring's --raw-floor entry.
        Defaulting to None (not the constants directly) keeps every existing
        caller's behavior byte-identical when it doesn't pass these."""
        floor_word = RAW_FLOOR_WORD if raw_floor_word is None else raw_floor_word
        floor_phrase = RAW_FLOOR_PHRASE if raw_floor_phrase is None else raw_floor_phrase
        hits = []
        total = max(self.total_word_count, 1)
        for term, substitute in vocab_list:
            term_lower = term.lower()
            is_multiword = len(term_lower.split()) > 1
            pattern = re.compile(
                r"\b" + re.escape(term_lower) + r"\b", re.IGNORECASE
            )
            lines_hit = []
            count = 0
            for lineno, text in self.prose_by_line.items():
                found = pattern.findall(text)
                if found:
                    count += len(found)
                    lines_hit.append(lineno)

            if count == 0:
                continue

            if is_multiword:
                fires = count >= floor_phrase
                rate = None
            else:
                rate = count / total * 1000
                fires = count >= floor_word and rate >= threshold

            if fires:
                hits.append(
                    {
                        "term": term,
                        "count": count,
                        "rate_per_1000": round(rate, 2) if rate is not None else None,
                        "lines": sorted(set(lines_hit)),
                        "substitute": substitute,
                    }
                )
        hits.sort(key=lambda h: h["count"], reverse=True)
        return hits

    def punctuation_density(self):
        em_dash_count = 0
        semicolon_count = 0
        curly_count = 0
        em_dash_lines = []
        semicolon_lines = []
        curly_lines = []
        for lineno, text in self.prose_by_line.items():
            ed = text.count(EM_DASH)
            sc = text.count(";")
            cq = sum(text.count(c) for c in CURLY_QUOTE_CHARS)
            if ed:
                em_dash_count += ed
                em_dash_lines.append(lineno)
            if sc:
                semicolon_count += sc
                semicolon_lines.append(lineno)
            if cq:
                curly_count += cq
                curly_lines.append(lineno)
        total = max(self.total_word_count, 1)
        return {
            "em_dash_count": em_dash_count,
            "em_dash_per_300": round(em_dash_count / total * 300, 2),
            "em_dash_lines": em_dash_lines,
            "semicolon_count": semicolon_count,
            "semicolon_per_300": round(semicolon_count / total * 300, 2),
            "semicolon_lines": semicolon_lines,
            "curly_quote_count": curly_count,
            "curly_quote_lines": curly_lines,
        }

    def negation_hits(self):
        results = []
        for name, pattern in NEGATION_PATTERNS:
            lines_hit = []
            examples = []
            for lineno, text in self.prose_by_line.items():
                for m in pattern.finditer(text):
                    lines_hit.append(lineno)
                    if len(examples) < 3:
                        examples.append(m.group(0).strip())
            if lines_hit:
                results.append(
                    {
                        "pattern": name,
                        "count": len(lines_hit),
                        "lines": sorted(set(lines_hit)),
                        "examples": examples,
                    }
                )
        return results

    def sentences(self):
        """All sentences drawn from prose lines, as plain strings (no line
        number attribution -- the sentence-length spread check reports only
        aggregate stats, per the tokenization contract)."""
        blob = " ".join(self.prose_by_line[k] for k in sorted(self.prose_by_line))
        blob = blob.strip()
        if not blob:
            return []
        parts = SENTENCE_SPLIT_RE.split(blob)
        return [p.strip() for p in parts if p.strip()]

    def sentence_stats(self):
        sents = self.sentences()
        if not sents:
            return {
                "count": 0,
                "longest": 0,
                "shortest": 0,
                "mean": 0.0,
                "pct_10_20_band": 0.0,
            }
        lengths = [len(s.split()) for s in sents]
        band = sum(1 for n in lengths if 10 <= n <= 20)
        return {
            "count": len(sents),
            "longest": max(lengths),
            "shortest": min(lengths),
            "mean": round(sum(lengths) / len(lengths), 1),
            "pct_10_20_band": round(band / len(lengths) * 100, 1),
        }

    def sentence_records_for_duplication(self):
        """(normalized_sentence, original_sentence, first_line) tuples for
        sentences of 8+ words, used by the cross-file duplication check."""
        records = []
        for lineno in sorted(self.prose_by_line):
            text = self.prose_by_line[lineno]
            for sent in SENTENCE_SPLIT_RE.split(text):
                sent = sent.strip()
                if not sent:
                    continue
                word_count = len(sent.split())
                if word_count < 8:
                    continue
                normalized = " ".join(sent.lower().split())
                records.append((normalized, sent, lineno))
        return records


# ---------------------------------------------------------------------------
# Programmatic entry point -- scan an in-memory string, no file
# ---------------------------------------------------------------------------


def scan_text(text, *, source_name="<string>", raw_floor=None,
              threshold=DEFAULT_RATE_FLOOR, top_n=20, vocab_list=None):
    """Scan a raw string directly -- no file, no path, no tempfile. Returns
    the same per-file result shape main()'s JSON output uses (word_count,
    frequency_hits, vocab_hits, punctuation, negation_hits, sentence_stats).

    `raw_floor`, when given, overrides both RAW_FLOOR_WORD and
    RAW_FLOOR_PHRASE for vocabulary-list hits -- at the built-in floors the
    vocabulary check cannot fire on typical review-length prose (~150-300
    words; confirmed empirically, perf-review-assistant's design review
    finding 1). Pass raw_floor=1 for that case. Leaving it None reproduces
    the CLI's existing default behavior exactly.

    `vocab_list` lets a caller pass an already-loaded list (e.g. loaded once
    per process rather than re-read from references/voice-tells.md on every
    call); defaults to loading it fresh, same as the CLI does per file.
    """
    if vocab_list is None:
        vocab_list = load_vocab_list(Path(__file__))
    scan = FileScan(text=text, source_name=source_name)
    return {
        # scan.path, not the raw source_name param -- FileScan already
        # resolves the "<string>" fallback; using source_name directly here
        # would diverge from it for a falsy-but-not-None source_name (e.g.
        # "").
        "file": scan.path,
        "word_count": scan.total_word_count,
        "frequency_hits": scan.word_frequency(threshold, top_n),
        "vocab_hits": scan.vocab_hits(
            vocab_list, threshold, raw_floor_word=raw_floor, raw_floor_phrase=raw_floor
        ),
        "punctuation": scan.punctuation_density(),
        "negation_hits": scan.negation_hits(),
        "sentence_stats": scan.sentence_stats(),
    }


# ---------------------------------------------------------------------------
# Cross-file check
# ---------------------------------------------------------------------------


def cross_file_duplicates(scans):
    if len(scans) < 2:
        return []
    by_normalized = {}
    for scan in scans:
        seen_in_this_file = set()
        for normalized, original, lineno in scan.sentence_records_for_duplication():
            if normalized in seen_in_this_file:
                continue
            seen_in_this_file.add(normalized)
            by_normalized.setdefault(normalized, []).append(
                {"file": str(scan.path), "line": lineno, "text": original}
            )

    duplicates = []
    for normalized, occurrences in by_normalized.items():
        files_involved = {occ["file"] for occ in occurrences}
        if len(files_involved) > 1:
            duplicates.append({"sentence": occurrences[0]["text"], "occurrences": occurrences})
    duplicates.sort(key=lambda d: len(d["occurrences"]), reverse=True)
    return duplicates


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------


def format_lines(lines):
    return ", ".join(str(n) for n in lines)


def render_text_report(results, vocab_available):
    out = []
    for result in results["files"]:
        out.append("=" * 72)
        out.append(f"FILE: {result['file']}")
        out.append(f"  word count: {result['word_count']}")
        out.append("-" * 72)

        out.append("WORD AND PHRASE FREQUENCY")
        if result["frequency_hits"]:
            for hit in result["frequency_hits"]:
                out.append(
                    f"  {hit['term']} -- {hit['count']} occurrences "
                    f"({hit['rate_per_1000']} per 1,000) -- lines {format_lines(hit['lines'])}"
                )
        else:
            out.append("  (none above threshold)")

        out.append("")
        out.append("VOCABULARY-LIST HITS")
        if not vocab_available:
            out.append("  (references/voice-tells.md not found -- skipped)")
        elif result["vocab_hits"]:
            for hit in result["vocab_hits"]:
                rate = f"{hit['rate_per_1000']} per 1,000" if hit["rate_per_1000"] is not None else "phrase"
                out.append(
                    f"  {hit['term']} -- {hit['count']} occurrences "
                    f"({rate}) -- lines {format_lines(hit['lines'])} -- substitute: {hit['substitute']}"
                )
        else:
            out.append("  (none above threshold)")

        out.append("")
        out.append("PUNCTUATION DENSITY")
        p = result["punctuation"]
        out.append(
            f"  em dashes: {p['em_dash_count']} ({p['em_dash_per_300']} per 300 words)"
            + (f" -- lines {format_lines(p['em_dash_lines'])}" if p["em_dash_lines"] else "")
        )
        out.append(
            f"  semicolons: {p['semicolon_count']} ({p['semicolon_per_300']} per 300 words)"
            + (f" -- lines {format_lines(p['semicolon_lines'])}" if p["semicolon_lines"] else "")
        )
        out.append(
            f"  curly quotes/apostrophes: {p['curly_quote_count']}"
            + (f" -- lines {format_lines(p['curly_quote_lines'])}" if p["curly_quote_lines"] else "")
        )

        out.append("")
        out.append("NEGATION-FRAMING PATTERNS")
        if result["negation_hits"]:
            for hit in result["negation_hits"]:
                out.append(
                    f"  {hit['pattern']} -- {hit['count']} occurrences -- lines {format_lines(hit['lines'])}"
                )
                for ex in hit["examples"]:
                    out.append(f'      e.g. "{ex}"')
        else:
            out.append("  (none found)")

        out.append("")
        out.append("SENTENCE-LENGTH SPREAD")
        s = result["sentence_stats"]
        out.append(
            f"  sentences: {s['count']}  longest: {s['longest']}  shortest: {s['shortest']}  "
            f"mean: {s['mean']}  in 10-20 word band: {s['pct_10_20_band']}%"
        )
        out.append("")

    if results.get("cross_file_duplicates"):
        out.append("=" * 72)
        out.append("CROSS-FILE NEAR-VERBATIM SENTENCES")
        for dup in results["cross_file_duplicates"]:
            out.append(f'  "{dup["sentence"]}"')
            for occ in dup["occurrences"]:
                out.append(f"      {occ['file']}:{occ['line']}")
        out.append("")

    return "\n".join(out)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Count document-level voice tells across one or more text files."
    )
    parser.add_argument("paths", nargs="*", help="file paths to scan")
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_RATE_FLOOR,
        help="override the per-1,000-word rate floor for single-word hits (default 2.0)",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=20,
        help="how many generic frequency hits to report per file (default 20)",
    )
    parser.add_argument(
        "--raw-floor",
        type=int,
        default=None,
        help="override RAW_FLOOR_WORD/RAW_FLOOR_PHRASE for vocabulary-list hits "
        "only (default: the built-in floors, 4 and 3)",
    )
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument(
        "--show-stoplist",
        action="store_true",
        help="print the in-script stop-list and exit",
    )
    args = parser.parse_args(argv)

    if args.show_stoplist:
        for word in sorted(STOP_WORDS):
            print(word)
        return 0

    if not args.paths:
        parser.error("at least one path is required (or use --show-stoplist)")

    script_path = Path(__file__)
    vocab_list = load_vocab_list(script_path)
    vocab_available = bool(vocab_list) or (
        script_path.resolve().parent.parent / "references" / "voice-tells.md"
    ).is_file()

    scans = []
    for raw_path in args.paths:
        p = Path(raw_path)
        if not p.is_file():
            print(f"error: not a file: {raw_path}", file=sys.stderr)
            return 1
        scans.append(FileScan(p))

    results = {"files": []}
    for scan in scans:
        results["files"].append(
            {
                "file": str(scan.path),
                "word_count": scan.total_word_count,
                "frequency_hits": scan.word_frequency(args.threshold, args.top),
                "vocab_hits": scan.vocab_hits(
                    vocab_list, args.threshold,
                    raw_floor_word=args.raw_floor, raw_floor_phrase=args.raw_floor,
                ),
                "punctuation": scan.punctuation_density(),
                "negation_hits": scan.negation_hits(),
                "sentence_stats": scan.sentence_stats(),
            }
        )

    duplicates = cross_file_duplicates(scans)
    if duplicates:
        results["cross_file_duplicates"] = duplicates

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print(render_text_report(results, vocab_available))

    return 0


if __name__ == "__main__":
    sys.exit(main())
