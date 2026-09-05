#!/bin/bash
# SessionEnd hook: warn-only reminder if anything's uncommitted when a session ends. Reports
# only - never stages or commits anything itself. Backstops docs/methodology.md section 6's
# "commit before ending a session" habit for the case where it got missed.
cd "${CLAUDE_PROJECT_DIR}" || exit 0
status=$(git status --short)
if [ -n "$status" ]; then
  list=$(printf '%s' "$status" | sed 's/"/\\"/g' | tr '\n' ';' | sed 's/;/; /g')
  printf '{"systemMessage": "Uncommitted changes remain in this repo: %s"}' "$list"
fi
true
