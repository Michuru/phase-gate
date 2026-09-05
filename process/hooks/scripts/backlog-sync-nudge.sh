#!/bin/sh
# PostToolUse (Write|Edit) hook: nudge toward syncing the rules doc whenever the backlog file
# is edited. Docs-sync is a hard requirement per docs/methodology.md section 7, not optional
# cleanup - this catches the moment it's easiest to remember, right after the edit that might
# need it, rather than relying on someone remembering later.
#
# CONFIGURE ME - match your variables.json / PORTING.md values if you renamed either file.
BACKLOG_FILE="BACKLOG.md"
RULES_DOC="CLAUDE.md"

input=$(cat)
echo "$input" | grep -qE "\"file_path\":\"[^\"]*${BACKLOG_FILE}\"" || exit 0

printf '{"systemMessage": "%s updated. If anything shipped this session changed how something behaves, consider updating %s too, so the docs stay in sync."}' \
  "$BACKLOG_FILE" "$RULES_DOC"
exit 0
