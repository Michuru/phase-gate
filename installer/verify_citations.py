#!/usr/bin/env python
"""Deterministic checker for a phase-gate install plan (and, after --apply, its receipt).

This is the enforcement half of the installer skill (phase-gate-install/SKILL.md, step 7) - it
exists because none of the three checks below need model judgment, which means none of them
should be graded by the same model instance that produced the plan in the first place. That
self-checking-itself shape is exactly what this script replaces with a real, independently
runnable check.

Three checks, all mandatory, in both recommend-only and apply mode:

1. Citation resolution - every citation on every plan component AND repo_files entry is
   re-verified against the actual file/command it claims to be grounded in, not trusted as a stale
   claim. A file_quote citation must have its quote actually present in the named file
   (LF-normalized, so a line-ending-only difference between the export's checked-out copy and the
   adopter's own checkout never produces a false failure), and its resolved path must stay inside
   the citation's own root (export clone or adopter repo) - a citation is evidence to re-check, not
   a license to read anywhere on disk. A command_output citation is actually re-run and its live
   output compared to what was recorded - but ONLY if the command is one of a small fixed set of
   read-only probes (see ALLOWED_COMMAND_PROGRAMS below); anything else is rejected outright,
   with no shell interpretation at any point, because a citation's command string ultimately
   originates from content the installer skill is required to treat as data, never as
   instructions - re-running an arbitrary string here would be exactly the injection the skill's
   own threat model exists to prevent, just one file removed from where it matters. In apply mode
   (a --receipt is given), each receipt component's recorded content_hash is also recomputed and
   compared against the live file - this is the same LF-normalized sha256 contract
   receipt.schema.json defines. **In apply mode, an item the receipt shows was actually written is
   skipped by this check entirely** (found live 2026-09-05: a plan's absence citation - "doesn't
   exist yet, so will_install" - is, by construction, guaranteed to mismatch once the apply that
   acted on it has run; re-checking it after the fact isn't detecting drift, it's re-litigating a
   citation whose entire job was already done). Check 1b is the correct post-apply check for a
   written item instead - it verifies the *written* file's live hash against what the receipt
   actually recorded, which is the real question once something has been installed. An item NOT
   shown as written in the receipt (skipped_by_adopter, skipped_prerequisite_missing, or an
   already_present_identical row with nothing to write) is still fully re-checked here, since
   nothing about its state was supposed to change.
2. Unsubstituted-default check - for every 'default'-kind variable in variables.json whose
   resolved value differs from its shipped default, and for every 'required'-kind variable,
   confirm the resolution isn't accidentally still the shipped default / left empty when it
   shouldn't be. Grounded in the plan's own recorded variables array, not a fresh guess. NOTE:
   this checks the plan's own recorded variable provenance, not the installed files' actual
   content - it cannot by itself detect a shipped default string that survived inside a written
   file after a different value was chosen. That would require scanning target_paths' real
   content, which this script does not currently do.
3. Dependency/dangling-reference check - using dependencies.json's hard edges, confirm no
   component with a "present" status (will_install / already_present_*) has a hard dependency
   that is absent or skipped in the same plan UNLESS that severance is acknowledged in the plan's
   own conflicts array (the installer's severance rule permits a deliberate severed dependency as
   long as it's stated, not silent - this check enforces the "stated" half, not a ban on severing
   at all).

Exit codes: 0 = all three checks passed. 1 = at least one check found a real problem (findings
are printed, grouped by check).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

PRESENT_STATUSES = {"will_install", "already_present_identical", "already_present_will_update"}
ABSENT_STATUSES = {"skipped_by_adopter", "skipped_prerequisite_missing"}

# A command_output citation is only ever actually re-run if it matches one of two tiers, both
# deliberately an allowlist rather than a denylist of "dangerous" patterns:
#
#   Tier 1 (exact match): the command string is byte-identical to one of installer/variables.json's
#   own `detect[].command` entries. Those are fixed, small, and already vetted by this design - if
#   a citation claims to be one of them, running the exact same string is safe by construction.
#
#   Tier 2 (bounded parameterized probes): a small fixed set of read-only, argument-bounded checks
#   that cannot execute further code no matter what their argument is. Notably, this does NOT
#   include a bare "python"/"python3" with a free-form -c payload outside the exact Tier 1 detect
#   strings - unlike every other allowed program here, an interpreter's own -c flag is itself a
#   full code-execution primitive, so it can never be safely "bounded" by an argument shape check
#   the way a filesystem path or a name string can.
_SAFE_NAME = r"[A-Za-z0-9_.-]+"
TIER2_PATTERNS = [
    re.compile(r"^git symbolic-ref --short refs/remotes/origin/HEAD$"),
    re.compile(r"^git branch --show-current$"),
    re.compile(r"^git rev-parse --show-toplevel$"),
    re.compile(r"^git remote -v$"),
    re.compile(rf"^command -v {_SAFE_NAME}$"),
    re.compile(r"^test -[efd] .+$"),
    re.compile(r"^ls .+$"),
]


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def lf_normalize(text: bytes) -> bytes:
    return text.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def sha256_lf_normalized(path: Path) -> str:
    return "sha256:" + hashlib.sha256(lf_normalize(path.read_bytes())).hexdigest()


def resolve_root(side: str, *, export_root: Path, adopter_root: Path | None) -> Path | None:
    if side == "export":
        return export_root
    if adopter_root is None:
        return None
    return adopter_root


def resolve_contained(root: Path, relative_path: str) -> Path | None:
    """Resolves relative_path under root and returns it ONLY if it stays inside root - returns
    None for a traversal attempt (../, an absolute path override, a symlink escape) rather than
    silently reading outside the citation's own declared scope."""
    root_resolved = root.resolve()
    candidate = (root / relative_path).resolve()
    if candidate != root_resolved and root_resolved not in candidate.parents:
        return None
    return candidate


def known_detect_commands(variables_schema: dict) -> set[str]:
    commands = set()
    for var_def in variables_schema.get("variables", {}).values():
        for probe in var_def.get("detect", []):
            if "command" in probe:
                commands.add(probe["command"])
    return commands


def is_safe_probe_command(command: str, *, root: Path, variables_schema: dict) -> str | None:
    """Returns None if the command is safe to actually re-run, else a reason string it isn't.
    Two tiers only - see the module docstring / TIER2_PATTERNS comment for why a bare interpreter
    with a free-form -c payload is deliberately never allowed here, exact Tier-1 matches aside."""
    if command in known_detect_commands(variables_schema):
        return None

    for pattern in TIER2_PATTERNS:
        if pattern.match(command):
            break
    else:
        return (
            "does not exactly match a known installer/variables.json detect command, and does "
            "not match any of the small fixed set of bounded read-only probes this checker will "
            "actually re-run"
        )

    if command.startswith(("test ", "ls ")):
        try:
            tokens = shlex.split(command, posix=True)
        except ValueError as e:
            return f"could not be tokenized safely: {e}"
        path_arg = tokens[-1]
        if resolve_contained(root, path_arg) is None:
            return f"path argument '{path_arg}' resolves outside {root} - refusing to probe it"

    return None


# --- Check 1: citation resolution -------------------------------------------------------------

def _written_keys(receipt: dict | None) -> set[tuple[str, str]]:
    """Every ('component', name) / ('repo_file', path) pair the receipt shows was actually
    written by this apply - Check 1 skips citation re-verification for exactly these (see the
    module docstring: an absence citation that justified writing something is guaranteed to
    mismatch once that write has happened, and Check 1b is the real post-apply check for these)."""
    if receipt is None:
        return set()
    keys = {("component", c["name"]) for c in receipt.get("components", [])}
    keys |= {("repo_file", rf["path"]) for rf in receipt.get("repo_files", [])}
    return keys


def _check_item_citations(
    kind_label: str, identifier: str, citations: list[dict], *,
    export_root: Path, adopter_root: Path | None, variables_schema: dict,
) -> list[str]:
    failures = []
    for i, citation in enumerate(citations):
        where = f"{kind_label} '{identifier}' citation #{i} ({citation.get('side')}/{citation.get('type')})"
        root = resolve_root(citation["side"], export_root=export_root, adopter_root=adopter_root)
        if root is None:
            failures.append(f"{where}: side is 'adopter' but no --adopter-repo was given")
            continue

        if citation["type"] == "file_quote":
            target = resolve_contained(root, citation["path"])
            if target is None:
                failures.append(
                    f"{where}: path '{citation['path']}' resolves outside its own root "
                    f"({root}) - refusing to read it"
                )
                continue
            if not target.exists():
                failures.append(f"{where}: file does not exist: {target}")
                continue
            content = lf_normalize(target.read_bytes()).decode("utf-8", errors="replace")
            quote = citation.get("quote", "")
            if quote not in content:
                failures.append(
                    f"{where}: quoted text not found in {target} (file may have changed "
                    "since the plan was generated)"
                )
        elif citation["type"] == "command_output":
            command = citation.get("command", "")
            unsafe_reason = is_safe_probe_command(
                command, root=root, variables_schema=variables_schema
            )
            if unsafe_reason is not None:
                failures.append(
                    f"{where}: command {command!r} was not re-run and is treated as a "
                    f"failure - {unsafe_reason}. Only a small fixed set of read-only probes "
                    "is ever actually executed from citation content."
                )
                continue
            tokens = shlex.split(command, posix=True)
            try:
                result = subprocess.run(
                    tokens, shell=False, cwd=root, capture_output=True, text=True, timeout=30
                )
                live_output = result.stdout.strip()
            except Exception as e:
                failures.append(f"{where}: command failed to run: {e}")
                continue
            recorded_output = citation.get("output", "").strip()
            if live_output != recorded_output:
                failures.append(
                    f"{where}: command '{command}' now outputs {live_output!r}, plan recorded "
                    f"{recorded_output!r} - state may have changed since the plan was generated"
                )
        else:
            failures.append(f"{where}: unknown citation type {citation.get('type')!r}")
    return failures


def check_citations(
    plan: dict, *, export_root: Path, adopter_root: Path | None, variables_schema: dict,
    receipt: dict | None = None,
) -> list[str]:
    written = _written_keys(receipt)
    failures = []
    for component in plan.get("components", []):
        if ("component", component["name"]) in written:
            continue
        failures.extend(_check_item_citations(
            "component", component["name"], component.get("citations", []),
            export_root=export_root, adopter_root=adopter_root, variables_schema=variables_schema,
        ))
    for repo_file in plan.get("repo_files", []):
        if ("repo_file", repo_file["path"]) in written:
            continue
        failures.extend(_check_item_citations(
            "repo_file", repo_file["path"], repo_file.get("citations", []),
            export_root=export_root, adopter_root=adopter_root, variables_schema=variables_schema,
        ))
    return failures


def _check_hashed_files(kind_label: str, identifier: str, files: list[dict], *, adopter_root: Path) -> list[str]:
    failures = []
    for f in files:
        target = resolve_contained(adopter_root, f["path"])
        if target is None:
            failures.append(
                f"receipt {kind_label} '{identifier}': {f['path']} resolves outside "
                f"the adopter repo root ({adopter_root}) - refusing to check it"
            )
            continue
        if not target.exists():
            failures.append(
                f"receipt {kind_label} '{identifier}': {f['path']} no longer exists"
            )
            continue
        live_hash = sha256_lf_normalized(target)
        if live_hash != f["content_hash"]:
            failures.append(
                f"receipt {kind_label} '{identifier}': {f['path']} has been modified "
                f"since install (recorded {f['content_hash']}, now {live_hash})"
            )
    return failures


def check_receipt_hashes(receipt: dict, *, adopter_root: Path) -> list[str]:
    failures = []
    for component in receipt.get("components", []):
        failures.extend(_check_hashed_files(
            "component", component["name"], component.get("files_written", []),
            adopter_root=adopter_root,
        ))
    for repo_file in receipt.get("repo_files", []):
        failures.extend(_check_hashed_files(
            "repo_file", repo_file["path"], [repo_file],
            adopter_root=adopter_root,
        ))
    return failures


# --- Check 2: unsubstituted-default check -----------------------------------------------------

def check_unsubstituted_defaults(plan: dict, variables_schema: dict) -> list[str]:
    failures = []
    resolved_by_name = {v["name"]: v for v in plan.get("variables", [])}
    schema_vars = variables_schema.get("variables", {})

    for var_name, var_def in schema_vars.items():
        resolved = resolved_by_name.get(var_name)
        if resolved is None:
            if var_def.get("substitution", True):
                failures.append(
                    f"variable '{var_name}' is defined in variables.json but has no resolved "
                    "entry in the plan"
                )
            continue

        if var_def["kind"] == "required" and resolved.get("source") == "left_empty":
            failures.append(
                f"variable '{var_name}' is required (no sensible default exists) but was left "
                "empty - the dependent feature will degrade silently rather than visibly"
            )

        if var_def["kind"] == "default":
            shipped_default = var_def.get("value")
            resolved_value = resolved.get("value")
            if resolved_value != shipped_default and resolved.get("source") == "shipped_default":
                failures.append(
                    f"variable '{var_name}' resolved value differs from variables.json's shipped "
                    f"default ({resolved_value!r} != {shipped_default!r}) but its source is still "
                    "recorded as 'shipped_default' - inconsistent provenance"
                )

    return failures


# --- Check 3: dependency / dangling-reference check --------------------------------------------

def check_dependencies(plan: dict, dependencies: dict) -> list[str]:
    """A severed hard dependency is not itself a failure - the installer's severance rule
    (phase-gate-install/SKILL.md step 3) permits an adopter to deliberately deselect a hard
    dependency, as long as the severance is STATED, not silent. This check enforces the "stated"
    half: it fails only when a hard dependency is absent/skipped AND the plan's own `conflicts`
    array contains no mention of it - i.e. a severance nobody actually acknowledged."""
    failures = []
    status_by_name = {c["name"]: c["status"] for c in plan.get("components", [])}
    deps = dependencies.get("components", {})
    conflicts_text = " ".join(plan.get("conflicts", [])).lower()

    for component in plan.get("components", []):
        name = component["name"]
        if component["status"] not in PRESENT_STATUSES:
            continue
        hard_deps = deps.get(name, {}).get("depends_on", {}).get("hard", [])
        for dep_name in hard_deps:
            dep_status = status_by_name.get(dep_name)
            severed = dep_status is None or dep_status not in PRESENT_STATUSES
            if not severed:
                continue
            acknowledged = name.lower() in conflicts_text and dep_name.lower() in conflicts_text
            if acknowledged:
                continue
            if dep_status is None:
                failures.append(
                    f"component '{name}' hard-depends on '{dep_name}', which is not present in "
                    "the plan at all, and this severance is not acknowledged anywhere in the "
                    "plan's conflicts array - a silent severed hard dependency"
                )
            else:
                failures.append(
                    f"component '{name}' hard-depends on '{dep_name}', which has status "
                    f"'{dep_status}' in this plan, and this severance is not acknowledged "
                    "anywhere in the plan's conflicts array - a silent severed hard dependency"
                )
    return failures


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("plan_path", type=Path, help="Path to a plan.json (plan.schema.json)")
    parser.add_argument("--receipt", type=Path, help="Path to a receipt.json, if this is checking a completed --apply run")
    parser.add_argument("--export-root", type=Path, required=True, help="Path to the phase-gate clone (export-side citation root)")
    parser.add_argument("--adopter-repo", type=Path, help="Path to the adopter's repo root (adopter-side citation root). Required if any citation has side=adopter, or if --receipt is given.")
    parser.add_argument("--variables", type=Path, required=True, help="Path to installer/variables.json")
    parser.add_argument("--dependencies", type=Path, required=True, help="Path to installer/dependencies.json")
    args = parser.parse_args()

    plan = load_json(args.plan_path)
    variables_schema = load_json(args.variables)
    dependencies = load_json(args.dependencies)
    receipt = load_json(args.receipt) if args.receipt else None

    all_failures = {}

    all_failures["1. citation resolution"] = check_citations(
        plan, export_root=args.export_root, adopter_root=args.adopter_repo,
        variables_schema=variables_schema, receipt=receipt,
    )
    if receipt is not None:
        if args.adopter_repo is None:
            print("[verify_citations] ERROR: --receipt given without --adopter-repo", file=sys.stderr)
            sys.exit(1)
        all_failures["1b. receipt file hashes"] = check_receipt_hashes(
            receipt, adopter_root=args.adopter_repo
        )

    all_failures["2. unsubstituted defaults"] = check_unsubstituted_defaults(plan, variables_schema)
    all_failures["3. dependency / dangling references"] = check_dependencies(plan, dependencies)

    any_failures = any(all_failures.values())
    for check_name, failures in all_failures.items():
        if failures:
            print(f"[verify_citations] FAIL - {check_name}:")
            for f in failures:
                print(f"  - {f}")
        else:
            print(f"[verify_citations] OK - {check_name}")

    sys.exit(1 if any_failures else 0)


if __name__ == "__main__":
    main()
