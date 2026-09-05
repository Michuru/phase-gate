#!/bin/sh
# PostToolUse (Write|Edit) hook: nudge toward the consolidate-docs skill once the rules doc
# crosses a line-count threshold. The rules doc loads in full every session regardless of task,
# so its size is a fixed per-session cost paid on every single request - this catches the
# moment it's grown past being worth that cost silently.
#
# CONFIGURE ME - match your variables.json / PORTING.md value if you renamed the rules doc, and
# adjust the threshold to taste (200 is this export's own starting point, not a universal rule).
RULES_DOC="CLAUDE.md"
LINE_THRESHOLD=200

input=$(cat)
echo "$input" | grep -qE "\"file_path\":\"[^\"]*${RULES_DOC}\"" || exit 0

target="${CLAUDE_PROJECT_DIR}/${RULES_DOC}"
lines=$(wc -l < "$target" 2>/dev/null) || exit 0
[ -n "$lines" ] || exit 0
[ "$lines" -gt "$LINE_THRESHOLD" ] 2>/dev/null || exit 0

printf '{"systemMessage": "%s is now %s lines (past the ~%s-line nudge threshold - consider running the consolidate-docs skill)."}' \
  "$RULES_DOC" "$lines" "$LINE_THRESHOLD"
exit 0
