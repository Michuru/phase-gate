#!/usr/bin/env python
"""Deterministic, non-destructive merge of one or more settings fragments (the shape produced
by every settings.fragment.json / settings.hooks.json in this export) into an adopter's real
.claude/settings.json.

Design: prints a diff, never writes without an explicit --apply flag. This is the
"diff-then-confirm" pattern, not installer-time detection-and-substitution - closest verified
precedent is shadcn's --dry-run/--diff/--overwrite trio. Dry-run is the default specifically so
a caller can never write by accident by forgetting a flag.

Scope, deliberately narrow: this script only ever merges two top-level keys, "hooks" and
"statusLine" - the only two keys any fragment in this export actually contains. It refuses
(loudly, exit nonzero, no partial write) if a fragment contains any other top-level key, rather
than attempting a generic deep-merge of arbitrary JSON into a file whose other keys (permissions,
env, etc.) it has no business touching or understanding.

Merge algorithm:
- "hooks": for each event name (PreToolUse, PostToolUse, SessionStart, SessionEnd, Stop, ...),
  each fragment entry is matched against an existing entry by its "matcher" field (or by the
  ABSENCE of a "matcher" field, for events that don't use one). A match merges the "hooks"
  sub-array by (type, command) identity, skipping anything already present - this is what makes
  a second run of the same fragment a no-op. No match appends the whole entry as a new group.
- "statusLine": a single object, not a list. No existing value -> set it. Identical existing
  value -> no-op (idempotent). DIFFERENT existing value -> a genuine conflict this script cannot
  resolve on its own; report it and refuse to touch that key, rather than guessing which one the
  adopter wants.

Exit codes: 0 = success (dry-run or real apply, with or without changes). 2 = one or more
conflicts detected - nothing was written, even in --apply mode; the caller must resolve them
(drop the offending fragment, or ask the adopter) and re-run. 1 = a real error (bad JSON, a
fragment using an unsupported top-level key, a missing file).
"""
import argparse
import copy
import difflib
import json
import sys
from pathlib import Path

SUPPORTED_TOP_LEVEL_KEYS = {"hooks", "statusLine"}


class MergeError(Exception):
    pass


def load_json(path: Path, *, required: bool):
    if not path.exists():
        if required:
            raise MergeError(f"{path} does not exist")
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise MergeError(f"{path} is not valid JSON: {e}")


def hook_entry_key(entry: dict):
    """Identity for one matcher-group within an event's array: its matcher, or None if absent.
    Two entries both lacking "matcher" are treated as the same group (this export never emits
    more than one matcher-less group per event, and neither should a well-formed adopter file)."""
    return entry.get("matcher")


def hook_command_key(h: dict):
    return (h.get("type"), h.get("command"))


def merge_hooks_key(existing: dict, fragment: dict) -> dict:
    """existing and fragment are both meant to be the VALUE of the top-level "hooks" key (event
    name -> list of matcher-groups). Returns a new merged dict; does not mutate either input.
    Raises MergeError (never crashes with a raw traceback) on any shape that isn't what a real
    settings.hooks.json / an adopter's own hooks key actually looks like."""
    if not isinstance(fragment, dict):
        raise MergeError(f"a fragment's \"hooks\" value must be an object, got {type(fragment).__name__}")
    merged = copy.deepcopy(existing)
    for event_name, frag_groups in fragment.items():
        if not isinstance(frag_groups, list):
            raise MergeError(
                f"fragment \"hooks\".{event_name} must be a list of matcher-groups, got "
                f"{type(frag_groups).__name__}"
            )
        existing_groups = merged.setdefault(event_name, [])
        if not isinstance(existing_groups, list):
            raise MergeError(
                f"existing settings' \"hooks\".{event_name} must be a list of matcher-groups, "
                f"got {type(existing_groups).__name__} - the existing settings.json has an "
                "unexpected shape for this key; not attempting to merge into it"
            )
        for frag_group in frag_groups:
            if not isinstance(frag_group, dict):
                raise MergeError(
                    f"fragment \"hooks\".{event_name} entries must be objects, got "
                    f"{type(frag_group).__name__}"
                )
            frag_group_key = hook_entry_key(frag_group)
            target = next(
                (g for g in existing_groups
                 if isinstance(g, dict) and hook_entry_key(g) == frag_group_key),
                None,
            )
            if target is None:
                existing_groups.append(copy.deepcopy(frag_group))
                continue
            target_hooks = target.setdefault("hooks", [])
            if not isinstance(target_hooks, list):
                raise MergeError(
                    f"existing settings' \"hooks\".{event_name} matcher-group has a non-list "
                    f"\"hooks\" value ({type(target_hooks).__name__}) - not attempting to merge into it"
                )
            existing_keys = {hook_command_key(h) for h in target_hooks if isinstance(h, dict)}
            for h in frag_group.get("hooks", []):
                if not isinstance(h, dict):
                    raise MergeError(
                        f"fragment \"hooks\".{event_name} hook entry must be an object, got "
                        f"{type(h).__name__}"
                    )
                if hook_command_key(h) not in existing_keys:
                    target_hooks.append(copy.deepcopy(h))
                    existing_keys.add(hook_command_key(h))
    return merged


def merge_status_line(existing: dict, fragment_value: dict, *, source_label: str):
    """Returns (merged_value, conflict_message_or_None)."""
    if "statusLine" not in existing:
        return copy.deepcopy(fragment_value), None
    if existing["statusLine"] == fragment_value:
        return existing["statusLine"], None
    conflict = (
        f"statusLine conflict from {source_label}: existing settings.json already has a "
        f"different statusLine configured. Existing: {json.dumps(existing['statusLine'])}. "
        f"Fragment wants: {json.dumps(fragment_value)}. Not touched - resolve manually, or drop "
        "this fragment from the merge."
    )
    return existing["statusLine"], conflict


def merge_one_fragment(settings: dict, fragment: dict, *, source_label: str):
    """Returns (new_settings, conflicts: list[str]). Does not mutate settings."""
    unknown = set(fragment.keys()) - SUPPORTED_TOP_LEVEL_KEYS
    if unknown:
        raise MergeError(
            f"{source_label} has unsupported top-level key(s) {sorted(unknown)} - this script "
            f"only merges {sorted(SUPPORTED_TOP_LEVEL_KEYS)}. Refusing to guess how to merge "
            "anything else into a file it doesn't fully understand."
        )

    result = copy.deepcopy(settings)
    conflicts = []

    if "hooks" in fragment:
        result["hooks"] = merge_hooks_key(result.get("hooks", {}), fragment["hooks"])

    if "statusLine" in fragment:
        merged_value, conflict = merge_status_line(
            result, fragment["statusLine"], source_label=source_label
        )
        result["statusLine"] = merged_value
        if conflict:
            conflicts.append(conflict)

    return result, conflicts


def render_diff(before: dict, after: dict, *, settings_path: Path) -> str:
    before_text = json.dumps(before, indent=2, sort_keys=True).splitlines(keepends=True)
    after_text = json.dumps(after, indent=2, sort_keys=True).splitlines(keepends=True)
    diff = difflib.unified_diff(
        before_text, after_text,
        fromfile=f"{settings_path} (before)",
        tofile=f"{settings_path} (after)",
    )
    return "".join(diff)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("settings_path", type=Path, help="Path to the adopter's .claude/settings.json (need not exist yet)")
    parser.add_argument("fragments", type=Path, nargs="+", help="One or more settings.fragment.json / settings.hooks.json files to merge in")
    parser.add_argument("--apply", action="store_true", help="Actually write settings_path. Without this flag, only prints the diff.")
    args = parser.parse_args()

    try:
        settings = load_json(args.settings_path, required=False)
        current = settings
        all_conflicts = []
        for frag_path in args.fragments:
            fragment = load_json(frag_path, required=True)
            current, conflicts = merge_one_fragment(current, fragment, source_label=str(frag_path))
            all_conflicts.extend(conflicts)
    except MergeError as e:
        print(f"[merge_settings] ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    diff_text = render_diff(settings, current, settings_path=args.settings_path)
    if diff_text:
        print(diff_text)
    else:
        print(f"[merge_settings] No changes - {args.settings_path} already reflects every fragment given.")

    if all_conflicts:
        print("", file=sys.stderr)
        print("[merge_settings] CONFLICTS - nothing written, even with --apply:", file=sys.stderr)
        for c in all_conflicts:
            print(f"  - {c}", file=sys.stderr)
        sys.exit(2)

    if args.apply and diff_text:
        args.settings_path.parent.mkdir(parents=True, exist_ok=True)
        args.settings_path.write_text(
            json.dumps(current, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"[merge_settings] Wrote {args.settings_path}")
    elif args.apply:
        print(f"[merge_settings] --apply given but nothing to write (already up to date).")
    else:
        print(f"[merge_settings] Dry run only - nothing written. Re-run with --apply to write {args.settings_path}.")

    sys.exit(0)


if __name__ == "__main__":
    main()
