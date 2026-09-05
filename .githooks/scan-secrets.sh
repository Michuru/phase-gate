#!/bin/sh
# .githooks/scan-secrets.sh - shared secret-shape scanner.
# Called by .githooks/pre-push (blocking) and .githooks/pre-commit (warn-only).
#
# Patterns live in .githooks/secret-patterns.txt (one ERE per non-comment,
# non-blank line) - see that file for why it ships empty, and why the patterns
# you add should track SHAPES of a credential form you have actually leaked
# rather than a generic "token=..." that fires constantly on your own prose.
#
# A matched value that is exactly one of Claude Code's own redaction
# placeholders (__TRACKED_VAR__, __CMDSUB_OUTPUT__, written into
# .claude/settings.local.json in place of a captured value) is never a real
# finding, so those are excluded before anything is reported.
#
# Usage:
#   scan-secrets.sh files <path>...     - scan specific files' current content
#   scan-secrets.sh objects <sha>...    - scan specific git blob objects'
#                                         content (materialized to a scratch
#                                         temp file each, then discarded)
#
# Exit code contract:
#   0 = clean, OR the scanner itself could not run (reported to stderr - an
#       infrastructure problem is never silently treated as a finding, nor
#       silently treated as clean without saying so)
#   1 = at least one real finding (see stdout for which pattern/file/line)

SELF_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd) || exit 0
PATTERNS_FILE="$SELF_DIR/secret-patterns.txt"
SAFE_PLACEHOLDERS_RE='__TRACKED_VAR__|__CMDSUB_OUTPUT__'

if [ ! -f "$PATTERNS_FILE" ]; then
  echo "[scan-secrets] pattern file missing ($PATTERNS_FILE) - scanner cannot run, not blocking" >&2
  exit 0
fi
if ! command -v grep >/dev/null 2>&1; then
  echo "[scan-secrets] grep not found - scanner cannot run, not blocking" >&2
  exit 0
fi

FOUND=0

scan_file() {
  # $1 = label to report, $2 = actual file path to scan
  _label="$1"
  _target="$2"
  [ -f "$_target" ] || return 0
  while IFS= read -r pattern; do
    case "$pattern" in
      ''|'#'*) continue ;;
    esac
    _matches=$(grep -naoE "$pattern" "$_target" 2>/dev/null | grep -vE "$SAFE_PLACEHOLDERS_RE")
    if [ -n "$_matches" ]; then
      echo "[scan-secrets] FINDING in $_label:"
      echo "$_matches" | sed 's/^/    /'
      FOUND=1
    fi
  done < "$PATTERNS_FILE"
}

MODE="$1"
if [ $# -gt 0 ]; then shift; fi

case "$MODE" in
  files)
    for f in "$@"; do
      scan_file "$f" "$f"
    done
    ;;
  objects)
    for sha in "$@"; do
      type=$(git cat-file -t "$sha" 2>/dev/null)
      [ "$type" = "blob" ] || continue
      tmp=$(mktemp 2>/dev/null) || {
        echo "[scan-secrets] mktemp failed - skipping blob $sha scan (infra, not a finding)" >&2
        continue
      }
      git cat-file -p "$sha" > "$tmp" 2>/dev/null
      scan_file "blob $sha" "$tmp"
      rm -f "$tmp"
    done
    ;;
  *)
    echo "[scan-secrets] usage: scan-secrets.sh <files|objects> <arg>..." >&2
    exit 0
    ;;
esac

if [ "$FOUND" = "1" ]; then
  exit 1
fi
exit 0
