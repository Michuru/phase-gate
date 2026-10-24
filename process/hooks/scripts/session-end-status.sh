#!/bin/bash
# SessionEnd hook: warn-only reminder if anything's uncommitted when a session ends. Reports
# only - never stages or commits anything itself. Backstops docs/methodology.md section 6's
# "commit before ending a session" habit for the case where it got missed.
#
# Covers the project repo and any repo nested one directory below it (a parent folder whose
# sub-projects are their own git roots, the parent's .gitignore often excluding them, so a
# status taken at the parent alone never sees their work). A nested repo is a direct child
# directory holding a .git (directory or file) that is its own repo root and that the parent
# does not track as a submodule (the parent's own status already reports a submodule). Each
# nested repo lists its first SHOW paths, then "+N more".
#
# Output is one JSON object. Backslashes and quotes are escaped (git quotes odd file names with
# backslashes, which would otherwise break the JSON), tab and CR become \t and \r, a newline
# becomes a space, and any other control character is dropped (a nested directory's own name is
# printed as the shell sees it, so it can hold any of these).
SHOW=5
root="${CLAUDE_PROJECT_DIR:-$PWD}"
cd "$root" || exit 0

tab=$(printf '\t')
cr=$(printf '\r')
json_escape() {
  printf '%s' "$1" | tr '\n' ' ' | tr -d '\000-\010\013\014\016-\037' |
    sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' -e "s/$tab/\\\\t/g" -e "s/$cr/\\\\r/g"
}
join_lines() { awk 'NR>1 { printf "; " } { printf "%s", $0 }'; }

msg=""
add_msg() { if [ -n "$msg" ]; then msg="$msg | $1"; else msg="$1"; fi; }

status=$(git status --short 2>/dev/null)
if [ -n "$status" ]; then
  add_msg "Uncommitted changes remain in this repo: $(printf '%s\n' "$status" | join_lines)"
fi

for dir in */; do
  name="${dir%/}"
  [ -e "$name/.git" ] || continue
  # Its own repo root: --show-prefix is empty there; git would otherwise answer for the parent.
  prefix=$(git -C "$name" rev-parse --show-prefix 2>/dev/null) || continue
  [ -z "$prefix" ] || continue
  # A path the parent tracks as a submodule (mode 160000) is already in the parent's status.
  # ":(literal)" so a directory name holding * or [ is not read as a glob.
  if git ls-files --stage -- ":(literal)$name" 2>/dev/null | grep -q '^160000'; then continue; fi
  st=$(git -C "$name" status --short 2>/dev/null)
  [ -n "$st" ] || continue
  total=$(printf '%s\n' "$st" | wc -l | tr -d ' ')
  more=""
  if [ "$total" -gt "$SHOW" ]; then more=" +$((total - SHOW)) more"; fi
  add_msg "Uncommitted in $name ($total): $(printf '%s\n' "$st" | head -n "$SHOW" | join_lines)$more"
done

if [ -n "$msg" ]; then
  printf '{"systemMessage": "%s"}' "$(json_escape "$msg")"
fi
exit 0
