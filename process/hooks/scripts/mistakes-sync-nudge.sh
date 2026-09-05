#!/bin/sh
# PostToolUse (Write|Edit) hook: nudge toward promoting a durable rule out of the mistakes log
# whenever it's edited. docs/methodology.md section 7's mistakes-log habit is only as good as
# this promotion actually happening - most of the value of a "durable rule" entry is lost if it
# stays buried in a log nobody reads by default.
#
# CONFIGURE ME - match your variables.json / PORTING.md values if you renamed either file.
MISTAKES_FILE="MISTAKES.md"
RULES_DOC="CLAUDE.md"

input=$(cat)
echo "$input" | grep -qE "\"file_path\":\"[^\"]*${MISTAKES_FILE}\"" || exit 0

printf '{"systemMessage": "%s updated. If this entry (or its recurring-pattern note) reflects a durable rule - not just a one-off - consider adding it to %s directly, not just as history here."}' \
  "$MISTAKES_FILE" "$RULES_DOC"
exit 0
