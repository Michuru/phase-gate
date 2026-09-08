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

Three modes:
- Merge (default): give one or more fragment files. Optionally add --report-json to also write
  the exact (event, matcher, type, command) tuples this call's fragments define (each flagged
  newly_appended: true/false), plus the statusLine value if this call sets it with no conflict -
  the only correct source for a receipt's settings_merge.hook_entries_written/status_line_written
  fields (a model transcribing this script's own text diff cannot reliably tell
  appended-from-already-present).
- --unmerge <entries.json>: the reverse of merge. Give a JSON file shaped like
  {"hook_entries_written": [...], "status_line_written": {...}|null} (the same shape --report-json
  produces, merge-forward-accumulated in a receipt) instead of fragment files. Removes exactly
  those hook tuples and, if the current statusLine still matches, clears it. A statusLine mismatch
  under --unmerge is a WARNING (exit 0, hook removal still proceeds) - a materially different
  contract from merge mode's conflict (exit 2, nothing written), since nothing here is a *new*
  ambiguous write, only removing something already recorded as this export's own.

Exit codes (merge mode): 0 = success (dry-run or real apply, with or without changes). 2 = one or
more conflicts detected - nothing was written, even in --apply mode; the caller must resolve them
(drop the offending fragment, or ask the adopter) and re-run. 1 = a real error (bad JSON, a
fragment using an unsupported top-level key, a missing file).

Exit codes (--unmerge mode): 0 = success, always (a statusLine mismatch is a warning printed to
stderr, not a failure). 1 = a real error (bad JSON, a missing --unmerge file, fragments given
alongside --unmerge).
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
    more than one matcher-less group per event, and neither should a well-formed adopter file).
    None and an explicit null are also treated as the same key - callers passing matcher back in
    from JSON (--unmerge's input file) get null, not a missing key, for the matcher-less case."""
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


def compute_hook_report(existing_hooks: dict, fragment_hooks: dict) -> list:
    """Read-only mirror of merge_hooks_key's own matching logic: for every (event, matcher, type,
    command) tuple this fragment defines, report whether it was already present in existing_hooks
    before this merge (newly_appended: false) or is new (newly_appended: true). Never mutates
    anything - this is what --report-json actually emits, so a caller (the installer skill) never
    has to infer appended-vs-already-present from a text diff."""
    if not isinstance(fragment_hooks, dict):
        raise MergeError(f"a fragment's \"hooks\" value must be an object, got {type(fragment_hooks).__name__}")
    report = []
    for event_name, frag_groups in fragment_hooks.items():
        if not isinstance(frag_groups, list):
            raise MergeError(f"fragment \"hooks\".{event_name} must be a list of matcher-groups")
        existing_groups = existing_hooks.get(event_name, []) if isinstance(existing_hooks, dict) else []
        if not isinstance(existing_groups, list):
            existing_groups = []
        for frag_group in frag_groups:
            if not isinstance(frag_group, dict):
                raise MergeError(f"fragment \"hooks\".{event_name} entries must be objects")
            matcher = hook_entry_key(frag_group)
            target = next(
                (g for g in existing_groups
                 if isinstance(g, dict) and hook_entry_key(g) == matcher),
                None,
            )
            existing_keys = set()
            if target is not None and isinstance(target.get("hooks"), list):
                existing_keys = {hook_command_key(h) for h in target["hooks"] if isinstance(h, dict)}
            for h in frag_group.get("hooks", []):
                if not isinstance(h, dict):
                    raise MergeError(f"fragment \"hooks\".{event_name} hook entry must be an object")
                key = hook_command_key(h)
                report.append({
                    "event": event_name,
                    "matcher": matcher,
                    "type": h.get("type"),
                    "command": h.get("command"),
                    "newly_appended": key not in existing_keys,
                })
    return report


def merge_status_line(existing: dict, fragment_value: dict, *, source_label: str):
    """Returns (merged_value, conflict_message_or_None, newly_set)."""
    if "statusLine" not in existing:
        return copy.deepcopy(fragment_value), None, True
    if existing["statusLine"] == fragment_value:
        return existing["statusLine"], None, False
    conflict = (
        f"statusLine conflict from {source_label}: existing settings.json already has a "
        f"different statusLine configured. Existing: {json.dumps(existing['statusLine'])}. "
        f"Fragment wants: {json.dumps(fragment_value)}. Not touched - resolve manually, or drop "
        "this fragment from the merge."
    )
    return existing["statusLine"], conflict, False


def merge_one_fragment(settings: dict, fragment: dict, *, source_label: str):
    """Returns (new_settings, conflicts: list[str], status_line_report: dict|None). Does not
    mutate settings. status_line_report is {"value": ..., "newly_set": bool} when this fragment
    sets statusLine with no conflict, else None."""
    unknown = set(fragment.keys()) - SUPPORTED_TOP_LEVEL_KEYS
    if unknown:
        raise MergeError(
            f"{source_label} has unsupported top-level key(s) {sorted(unknown)} - this script "
            f"only merges {sorted(SUPPORTED_TOP_LEVEL_KEYS)}. Refusing to guess how to merge "
            "anything else into a file it doesn't fully understand."
        )

    result = copy.deepcopy(settings)
    conflicts = []
    status_line_report = None

    if "hooks" in fragment:
        result["hooks"] = merge_hooks_key(result.get("hooks", {}), fragment["hooks"])

    if "statusLine" in fragment:
        merged_value, conflict, newly_set = merge_status_line(
            result, fragment["statusLine"], source_label=source_label
        )
        result["statusLine"] = merged_value
        if conflict:
            conflicts.append(conflict)
        else:
            status_line_report = {"value": fragment["statusLine"], "newly_set": newly_set}

    return result, conflicts, status_line_report


def unmerge_hooks(existing_hooks: dict, entries: list) -> dict:
    """existing_hooks is the VALUE of the top-level "hooks" key (or {} if absent). entries is a
    list of {"event", "matcher", "type", "command"} dicts to remove - the same shape
    compute_hook_report emits. Returns a new dict (never mutates existing_hooks) with exactly
    those (type, command) pairs removed from their matching matcher-group, dropping a
    matcher-group that ends up with no hooks, and dropping an event that ends up with no groups.
    matcher absent and null are equal, matching hook_entry_key's own .get().

    Only ever inspects/prunes the specific (event, matcher-group) pairs this call actually
    targeted - an untouched matcher-group or event, even one that was ALREADY empty before this
    call, is left completely alone. A prior version pruned every empty group/event across the
    whole tree regardless of whether this call touched it, which could silently delete an
    adopter's own unrelated pre-existing empty group (or collapse the entire "hooks" key) that
    this export never wrote and has no business touching."""
    merged = copy.deepcopy(existing_hooks) if isinstance(existing_hooks, dict) else {}
    touched = []  # [(event, target_group_dict), ...] - only groups this call actually inspected
    for entry in entries:
        event = entry.get("event")
        groups = merged.get(event)
        if not isinstance(groups, list):
            continue
        matcher = entry.get("matcher")
        target = next((g for g in groups if isinstance(g, dict) and hook_entry_key(g) == matcher), None)
        if target is None:
            continue
        hooks_list = target.get("hooks")
        if not isinstance(hooks_list, list):
            continue
        removal_key = (entry.get("type"), entry.get("command"))
        target["hooks"] = [
            h for h in hooks_list
            if not (isinstance(h, dict) and hook_command_key(h) == removal_key)
        ]
        touched.append((event, target))

    for event, target in touched:
        groups = merged.get(event)
        if not isinstance(groups, list):
            continue
        if isinstance(target.get("hooks"), list) and len(target["hooks"]) == 0:
            groups[:] = [g for g in groups if g is not target]
        if not groups:
            merged.pop(event, None)
    return merged


def unmerge_settings(settings: dict, hook_entries: list, status_line_written):
    """Returns (new_settings, warnings: list[str]). Does not mutate settings. status_line_written
    is the {"value": ...} dict previously recorded by --report-json, or None if this export never
    set statusLine. A mismatch between the current value and the recorded one is a warning, not a
    failure - hook removal still proceeds regardless."""
    result = copy.deepcopy(settings)
    warnings = []

    if hook_entries:
        new_hooks = unmerge_hooks(result.get("hooks", {}), hook_entries)
        if new_hooks:
            result["hooks"] = new_hooks
        else:
            result.pop("hooks", None)

    if status_line_written is not None:
        recorded_value = status_line_written.get("value") if isinstance(status_line_written, dict) else status_line_written
        current = result.get("statusLine")
        if current == recorded_value:
            result.pop("statusLine", None)
        elif current is not None:
            warnings.append(
                f"statusLine mismatch: current value {json.dumps(current)} does not match the "
                f"recorded {json.dumps(recorded_value)} - left untouched, may have been edited "
                "since install."
            )
        # current is None: nothing to remove, not a warning either.

    return result, warnings


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
    parser.add_argument("fragments", type=Path, nargs="*", help="One or more settings.fragment.json / settings.hooks.json files to merge in. Not used with --unmerge.")
    parser.add_argument("--apply", action="store_true", help="Actually write settings_path. Without this flag, only prints the diff.")
    parser.add_argument("--report-json", type=Path, help="Merge mode only: write the exact (event, matcher, type, command) tuples this call's fragments define (each flagged newly_appended), plus the statusLine value if set with no conflict, as JSON to this path.")
    parser.add_argument("--unmerge", type=Path, help="Reverse mode: path to a JSON file shaped {\"hook_entries_written\": [...], \"status_line_written\": {...}|null} - the exact tuples/value to remove. Mutually exclusive with giving fragments.")
    args = parser.parse_args()

    if args.unmerge:
        if args.fragments:
            print("[merge_settings] ERROR: --unmerge does not take fragment files.", file=sys.stderr)
            sys.exit(1)
        try:
            unmerge_data = load_json(args.unmerge, required=True)
        except MergeError as e:
            print(f"[merge_settings] ERROR: {e}", file=sys.stderr)
            sys.exit(1)
        hook_entries = unmerge_data.get("hook_entries_written") or []
        status_line_written = unmerge_data.get("status_line_written")

        settings = load_json(args.settings_path, required=False)
        current, warnings = unmerge_settings(settings, hook_entries, status_line_written)

        diff_text = render_diff(settings, current, settings_path=args.settings_path)
        if diff_text:
            print(diff_text)
        else:
            print(f"[merge_settings] No changes - nothing recorded as phase-gate's own is present in {args.settings_path}.")

        for w in warnings:
            print(f"[merge_settings] WARNING: {w}", file=sys.stderr)

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

    if not args.fragments:
        print("[merge_settings] ERROR: no fragment files given (and --unmerge not used).", file=sys.stderr)
        sys.exit(1)

    try:
        settings = load_json(args.settings_path, required=False)
        current = settings
        all_conflicts = []
        report_hook_entries = []
        report_status_line = None
        for frag_path in args.fragments:
            fragment = load_json(frag_path, required=True)
            before = current
            current, conflicts, status_line_report = merge_one_fragment(current, fragment, source_label=str(frag_path))
            all_conflicts.extend(conflicts)
            if "hooks" in fragment:
                report_hook_entries.extend(compute_hook_report(before.get("hooks", {}), fragment["hooks"]))
            if status_line_report is not None:
                report_status_line = status_line_report
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

    if args.report_json:
        report = {"hook_entries_written": report_hook_entries, "status_line_written": report_status_line}
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        args.report_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"[merge_settings] Wrote report to {args.report_json}")

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
