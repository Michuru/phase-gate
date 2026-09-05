#!/usr/bin/env python
"""Reports which files in your source repo have changed since this export's manifest.json was
generated - drift detection so re-generalization is a hash comparison, not a checklist reminder
someone has to remember to run.

This is a maintainer-side tool, run from wherever the repo this export was generalized from
actually lives - never from an adopter's repo. It answers "does phase-gate need to be
regenerated from its source?", a completely different question from installer/verify_citations.py
(which answers "did an adopter's install go as planned?") or receipt.json's content_hash (which
answers "did an adopter modify their own copy?"). Three separate drift questions, three separate
mechanisms, on purpose.

For each file in manifest.json with a non-null source_blob:
- source_hash_type "git-blob": compare against `git -C <source-repo> rev-parse HEAD:<source_path>`.
  A missing/renamed path is reported, not a crash.
- source_hash_type "sha256": compare against a fresh LF-normalized sha256 of the live file at
  <source-repo>/<source_path> - LF-normalized for the same reason receipt.json's hashes are: a
  maintainer's own checkout settings can flip line endings without the content having
  meaningfully changed.

Exit codes: 0 = nothing has drifted. 1 = at least one source file has changed (or gone missing)
since manifest.json was generated - phase-gate needs re-generalization for that component.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path


def lf_normalize(data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def git_blob_hash(source_repo: Path, source_path: str) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(source_repo), "rev-parse", f"HEAD:{source_path}"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def sha256_hash(source_repo: Path, source_path: str) -> str | None:
    target = source_repo / source_path
    if not target.exists():
        return None
    return hashlib.sha256(lf_normalize(target.read_bytes())).hexdigest()


def check_drift(manifest: dict, source_repo: Path) -> dict[str, list[str]]:
    """Returns {component_name: [drift descriptions]} for components with at least one drifted
    or missing file. Components with no drift are omitted entirely."""
    drifted = {}
    for component in manifest.get("components", []):
        findings = []
        for f in component.get("files", []):
            if f.get("source_blob") is None:
                continue  # no source-repo file to drift against (e.g. a generated README)

            source_path = f["source_path"]
            recorded = f["source_blob"]

            if f["source_hash_type"] == "git-blob":
                live = git_blob_hash(source_repo, source_path)
                if live is None:
                    findings.append(f"{source_path}: no longer resolves at source-repo HEAD (renamed or deleted?)")
                elif live != recorded:
                    findings.append(f"{source_path}: source blob changed ({recorded} -> {live})")
            elif f["source_hash_type"] == "sha256":
                live = sha256_hash(source_repo, source_path)
                if live is None:
                    findings.append(f"{source_path}: file no longer exists at {source_repo / source_path}")
                elif live != recorded:
                    findings.append(f"{source_path}: content changed (sha256 {recorded[:12]}... -> {live[:12]}...)")
            else:
                findings.append(f"{source_path}: unknown source_hash_type {f['source_hash_type']!r}")

        if findings:
            drifted[component["name"]] = findings
    return drifted


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("manifest_path", type=Path, help="Path to installer/manifest.json")
    parser.add_argument("--source-repo", type=Path, required=True, help="Path to the repo this export was generalized from")
    args = parser.parse_args()

    manifest = json.loads(args.manifest_path.read_text(encoding="utf-8"))
    drifted = check_drift(manifest, args.source_repo)

    if not drifted:
        print("[drift_check] Clean - no source-repo file has changed since manifest.json was generated.")
        sys.exit(0)

    print(f"[drift_check] {len(drifted)} component(s) have drifted from their source - re-generalization may be due:")
    for name, findings in drifted.items():
        print(f"  {name}:")
        for f in findings:
            print(f"    - {f}")
    sys.exit(1)


if __name__ == "__main__":
    main()
