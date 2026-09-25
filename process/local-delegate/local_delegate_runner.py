#!/usr/bin/env python3
"""Local-model delegation runner for /build's implement-mode gate (optional,
off by default unless your own configuration names a model for it -- see
this component's own README).

Deliberately self-contained -- no imports outside the standard library plus
`requests` -- so it ships as a single script.

Behavior, in order:
  1. Configuration check, fail closed -- no recorded local-delegate model, no attempt.
  2. Target-existence check, fail closed -- the target file must not already exist in the tree,
     since this script only ever generates a whole module; no attempt if it does.
  3. GPU pre-check, fail closed -- nvidia-smi missing/erroring or busy, no attempt.
  4. Draft via Ollama, into an isolated scratch copy under .claude/state/local-delegate/.
     The real repo tree is only ever read, never written, by this script.
  5. Gate: run the visible test file (and held-out file, if given) against the draft, scoped to
     --target-tests/--held-out-tests (pytest -k selectors) when the test file also covers other
     tasks' functions. A mistyped selector surfaces as a distinct wiring error via pytest's own
     "no tests collected" exit code, never a false gate failure.
  6. If the gate passes and --target-functions was given, check the draft's own top-level names
     against every function the full test file references -- a name outside the target list
     fails the gate too (out-of-scope-definition check), so a draft implementing someone else's
     function alongside its own can't slip through.
  7. Report a structured result; the CALLING skill decides whether to copy the draft
     into the real tree, escalate, or (test-gen mode) anything else -- this script
     never writes outside its own scratch root.

--mode is present now so a future test-gen mode doesn't need a restructure; only
"implement" runs today.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

try:
    import requests
except ImportError:
    requests = None  # handled at call time -- a missing dependency is a "not attempted", not a crash

OLLAMA_URL = "http://localhost:11434/api/chat"
NUM_CTX = 16384
# Generous enough to cover a real whole-module draft without truncating it; a
# tighter cap risks cutting a legitimate response off mid-generation.
REQUEST_TIMEOUT_S = 300.0

_FENCE_RE = re.compile(r"```(?:python)?\s*\n(.*?)```", re.DOTALL)

EXCLUDED_DIR_NAMES = {".git", "node_modules", "__pycache__", ".venv", "venv"}


# --- repo/config resolution -------------------------------------------------------

def find_repo_root(start: Path) -> Path:
    """Walk upward from `start` to the nearest ancestor containing a .git directory."""
    current = start.resolve()
    if current.is_file():
        current = current.parent
    for candidate in [current, *current.parents]:
        if (candidate / ".git").exists():
            return candidate
    return current


def parent_config_root_of(repo_root: Path) -> Path | None:
    """If you keep several repos nested under one parent that carries the shared
    .claude/ configuration (this export's own multi-repo convention -- see
    `spec/SKILL.md`'s own upward-resolution note for `fable_available`), a
    session in the nested repo should still find the parent's recorded config."""
    return repo_root.parent if (repo_root.parent / ".claude").exists() else None


def load_config(repo_root: Path) -> dict:
    """Reads the resolved, live .claude/phase-gate-install/variables.json -- never
    installer/variables.json, which is this export's shipped-defaults copy."""
    candidates = [repo_root / ".claude" / "phase-gate-install" / "variables.json"]
    parent_root = parent_config_root_of(repo_root)
    if parent_root:
        candidates.append(parent_root / ".claude" / "phase-gate-install" / "variables.json")
    for path in candidates:
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
    return {}


def configured_model(config: dict, mode: str) -> str | None:
    return (config.get("local_delegate") or {}).get(mode)


def python_cmd(config: dict) -> str:
    """The resolved python_cmd variable from your own configuration -- never a
    literal "python". Falls back to "python" only when nothing is recorded."""
    return config.get("python_cmd") or "python"


# --- GPU pre-check -----------------------------------------------------------------

GPU_BUSY_THRESHOLD_PCT = 15.0


def gpu_busy() -> tuple[bool, str]:
    """Fails closed: nvidia-smi missing, erroring, timing out, or returning unparseable
    output all count as busy, never as free. On a non-NVIDIA machine this makes the
    feature permanently inert, which is the stated, accepted tradeoff for an opt-in,
    silent-and-safe feature.

    Uses GPU utilization, not a process-name check. An earlier version enumerated
    --query-compute-apps and treated any non-model-runtime entry as busy; live testing
    found that query lists ordinary desktop/background processes (a browser, an editor)
    unconditionally on some drivers, not just genuine heavy compute users -- as designed
    it would almost never report "free". Utilization is the direct answer to the
    question this check actually needs to answer."""
    try:
        proc = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as e:
        return True, f"nvidia-smi unavailable ({e}) -- treated as busy"
    if proc.returncode != 0:
        return True, f"nvidia-smi exited {proc.returncode} -- treated as busy"
    try:
        utilization_pct = float(proc.stdout.strip().splitlines()[0])
    except (ValueError, IndexError):
        return True, f"unparseable nvidia-smi output ({proc.stdout!r}) -- treated as busy"
    if utilization_pct > GPU_BUSY_THRESHOLD_PCT:
        return True, f"GPU utilization {utilization_pct:.0f}% > {GPU_BUSY_THRESHOLD_PCT:.0f}% threshold"
    return False, f"GPU free ({utilization_pct:.0f}% utilization)"


# --- Ollama call ---------------------------------------------------------------------

def call_ollama(model: str, prompt: str, num_ctx: int = NUM_CTX) -> dict:
    if requests is None:
        return {"response_text": "", "wall_clock_s": 0.0, "timed_out": True,
                 "error": "the 'requests' package is not installed"}
    start = time.monotonic()
    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "options": {"num_ctx": num_ctx},
            },
            timeout=REQUEST_TIMEOUT_S,
        )
        wall_clock_s = time.monotonic() - start
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException as e:
        return {"response_text": "", "wall_clock_s": time.monotonic() - start,
                 "timed_out": True, "error": str(e)}
    return {
        "response_text": data.get("message", {}).get("content", ""),
        "wall_clock_s": wall_clock_s,
        "eval_count": data.get("eval_count"),
        "load_duration_s": (data.get("load_duration") or 0) / 1e9,
        "timed_out": False,
    }


def extract_code(response_text: str) -> tuple[str | None, str]:
    m = _FENCE_RE.search(response_text)
    if m:
        return m.group(1).strip("\n"), "fenced_block"
    stripped = response_text.strip()
    if stripped:
        return stripped, "raw_fallback_no_fence"
    return None, "empty_response"


def syntax_valid(code: str) -> tuple[bool, str]:
    try:
        ast.parse(code)
        return True, ""
    except SyntaxError as e:
        return False, str(e)


# --- Gate ----------------------------------------------------------------------------

# A pathological draft (infinite loop, blocking I/O) must not hang the gate -- and
# therefore the whole /build step -- indefinitely. The draft call already has an
# equivalent cap via REQUEST_TIMEOUT_S above; this mirrors it on the gate side.
PYTEST_TIMEOUT_S = 60.0


PYTEST_NO_TESTS_COLLECTED = 5  # pytest's own exit code for "-k matched nothing" -- a wiring
                                # mistake (a typo'd class/test name), never a genuine gate failure.


def run_pytest(scratch_dir: Path, test_filename: str, python_exe: str,
                select_expr: str | None = None) -> dict:
    start = time.monotonic()
    cmd = [python_exe, "-m", "pytest", "-q", test_filename]
    if select_expr:
        cmd += ["-k", select_expr]
    try:
        proc = subprocess.run(
            cmd, cwd=str(scratch_dir), capture_output=True, text=True, timeout=PYTEST_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired as e:
        return {
            "passed": False,
            "returncode": None,
            "wall_clock_s": time.monotonic() - start,
            "output_tail": f"gate timed out after {PYTEST_TIMEOUT_S:.0f}s: {e}",
        }
    return {
        "passed": proc.returncode == 0,
        "returncode": proc.returncode,
        "wall_clock_s": time.monotonic() - start,
        "output_tail": (proc.stdout + proc.stderr)[-4000:],
    }


def referenced_module_functions(test_source: str, module_stem: str) -> set[str]:
    """Every function name the FULL test file (not just the selected subset) references off
    the target module, via either `import module_stem` + `module_stem.fn(...)`, an aliased
    `import module_stem as alias` + `alias.fn(...)`, or `from module_stem import fn`. Used by
    the out-of-scope-definition check below -- scoped to names the test file itself calls
    out, never a blanket "no extra definitions" rule that would also reject a model's own
    legitimate private helpers."""
    tree = ast.parse(test_source)
    aliases = {module_stem}
    referenced: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == module_stem and alias.asname:
                    aliases.add(alias.asname)
        elif isinstance(node, ast.ImportFrom) and node.module == module_stem:
            referenced.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id in aliases:
                referenced.add(node.attr)
    return referenced


def out_of_scope_definitions(draft_code: str, referenced: set[str], target_functions: set[str]) -> list[str]:
    """Top-level names in the draft that the full test file references but that this task
    wasn't actually assigned -- catches the case where a draft implements several functions
    from a shared test file when it was only assigned one or two of them."""
    tree = ast.parse(draft_code)
    top_level = {
        node.name for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }
    return sorted((top_level & referenced) - target_functions)


def run_gate(scratch_dir: Path, target_name: str, draft_code: str, test_name: str,
             held_out_name: str | None, python_exe: str,
             visible_select: str | None = None, held_out_select: str | None = None) -> dict:
    """Runs entirely inside scratch_dir -- the real repo tree is never touched here."""
    (scratch_dir / target_name).write_text(draft_code, encoding="utf-8")

    visible = run_pytest(scratch_dir, test_name, python_exe, visible_select)
    if visible_select and visible["returncode"] == PYTEST_NO_TESTS_COLLECTED:
        return {"wiring_error": True,
                "wiring_reason": f"-k {visible_select!r} matched no tests in {test_name} -- "
                                  "check the target-tests class/function names"}
    result = {
        "visible_passed": visible["passed"],
        "visible_wall_clock_s": visible["wall_clock_s"],
        "visible_output_tail": visible["output_tail"],
    }
    if held_out_name:
        held_out = run_pytest(scratch_dir, held_out_name, python_exe, held_out_select)
        if held_out_select and held_out["returncode"] == PYTEST_NO_TESTS_COLLECTED:
            return {"wiring_error": True,
                    "wiring_reason": f"-k {held_out_select!r} matched no tests in {held_out_name} -- "
                                      "check the held-out-tests class/function names"}
        result["held_out_passed"] = held_out["passed"]
        result["held_out_wall_clock_s"] = held_out["wall_clock_s"]
        result["held_out_output_tail"] = held_out["output_tail"]
        result["gate_passed"] = visible["passed"] and held_out["passed"]
    else:
        result["gate_passed"] = visible["passed"]
    return result


# --- implement mode --------------------------------------------------------------------

PROMPT_TEMPLATE = """You are implementing a small, self-contained Python function from a written \
contract. Below is the contract and the visible test file your implementation must pass.

=== contract ===
{contract}

=== test file ({test_name}) ===
{test_visible}
{scope_note}
Write the complete contents of a module named {target_name} that implements the contract and \
passes every test in {test_name} above.

Respond with ONLY the Python code for {target_name}, inside a single fenced code block \
(```python ... ```), and nothing else -- no explanation, no prose before or after the code block.
"""

SCOPE_NOTE_TEMPLATE = """
IMPORTANT: the test file above may also exercise OTHER functions/classes that belong to separate, \
unrelated tasks. Only these will actually be run against your code: {target_test_classes}. Every \
other test class in the file -- including any class that exercises a module-level import or \
attribute you have not been told to implement -- belongs to a separate, unrelated task and will \
NOT be executed against your module. You are only responsible for implementing these specific \
function(s): {target_functions}, PLUS any module-level utilities already described to you above \
(if there is a "provided utilities" section) as available to reuse -- including those is expected \
and never a violation, whether you copy them verbatim or write your own equivalent. Do not \
implement, import, or attempt to satisfy any OTHER function, class, or module-level name \
referenced in the file that was not described to you above, even though it may be visible in the \
test file -- doing so is unnecessary for the tests that will actually run, and risks introducing \
an import that cannot resolve in your sandboxed environment (there is no wider package/repo \
available to you here, only the files shown above).
"""
# This wording went through two earlier iterations that each introduced a real regression
# (a model implementing out-of-scope functions it shouldn't have) before converging on the
# text above, validated across several real local models with zero regressions once
# stabilized. If you change this template, re-run your own eligible tasks afterward rather
# than assuming a wording tweak is safe.


def run_implement(args: argparse.Namespace) -> dict:
    repo_root = find_repo_root(Path(args.repo_root) if args.repo_root else Path.cwd())
    config = load_config(repo_root)

    model = configured_model(config, "implement")
    if not model:
        return {"attempted": False, "reason": "no local-delegate model configured for implement"}

    # Implement mode is a whole-module generator -- a gate pass means the calling skill
    # copies the draft over whatever is at target_file. If that file already has real
    # content, a passing draft would silently destroy it. Fails closed, before any model
    # call -- see this component's own README, "Limitations," for the full reasoning
    # (adding a function inside an existing file is not a supported/tested shape).
    target_path = Path(args.target_file)
    if target_path.exists():
        return {"attempted": False, "wiring_error": True,
                "reason": f"target module already exists at {target_path} -- implement mode "
                           "only produces whole new modules; see this component's README, "
                           "\"Limitations\""}

    busy, reason = gpu_busy()
    if busy:
        return {"attempted": False, "reason": f"GPU: {reason}"}

    if requests is None:
        # A missing dependency is a precondition failure, same shape as the checks above --
        # not a draft attempt that happened to fail.
        return {"attempted": False, "reason": "the 'requests' package is not installed"}

    contract_text = Path(args.contract_file).read_text(encoding="utf-8")
    test_path = Path(args.test_file)
    test_text = test_path.read_text(encoding="utf-8")
    target_name = target_path.name
    test_name = test_path.name
    held_out_path = Path(args.held_out_file) if args.held_out_file else None
    held_out_name = held_out_path.name if held_out_path else None
    held_out_text = held_out_path.read_text(encoding="utf-8") if held_out_path else None

    target_functions = {f.strip() for f in args.target_functions.split(",") if f.strip()} \
        if args.target_functions else None
    visible_select = " or ".join(s.strip() for s in args.target_tests.split(",") if s.strip()) \
        if args.target_tests else None
    held_out_select = " or ".join(s.strip() for s in args.held_out_tests.split(",") if s.strip()) \
        if args.held_out_tests else None

    run_id = uuid.uuid4().hex[:12]
    scratch_dir = repo_root / ".claude" / "state" / "local-delegate" / run_id
    scratch_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(test_path, scratch_dir / test_name)
    if held_out_path:
        shutil.copy(held_out_path, scratch_dir / held_out_name)

    scope_note = ""
    if target_functions:
        # Your own eligibility rule for the (local-delegate: implement) marker should always
        # scope a shared test file via --target-tests -- but the flag is optional at the CLI
        # level, so this falls back to a plain description rather than a KeyError if it's ever
        # omitted anyway.
        test_classes_desc = visible_select if visible_select else \
            "the tests that exercise your assigned function(s) below"
        scope_note = SCOPE_NOTE_TEMPLATE.format(
            target_functions=", ".join(sorted(target_functions)),
            target_test_classes=test_classes_desc,
        )
    prompt = PROMPT_TEMPLATE.format(
        contract=contract_text, test_name=test_name, test_visible=test_text, target_name=target_name,
        scope_note=scope_note,
    )
    draft = call_ollama(model, prompt)

    result = {
        "attempted": True,
        "mode": "implement",
        "model": model,
        "scratch_dir": str(scratch_dir),
        "draft_wall_clock_s": draft["wall_clock_s"],
    }
    if draft.get("timed_out"):
        result.update(gate_passed=False, stage="draft_failed", error=draft.get("error"))
        return result

    code, extraction_method = extract_code(draft["response_text"])
    if code is None:
        result.update(gate_passed=False, stage="empty_response", extraction_method=extraction_method)
        return result

    valid, syntax_error = syntax_valid(code)
    if not valid:
        result.update(gate_passed=False, stage="syntax_invalid", syntax_error=syntax_error,
                        draft_path=None)
        return result

    gate = run_gate(scratch_dir, target_name, code, test_name, held_out_name, python_cmd(config),
                     visible_select, held_out_select)
    if gate.get("wiring_error"):
        return {"attempted": False, "wiring_error": True, "reason": gate["wiring_reason"],
                "scratch_dir": str(scratch_dir)}
    result.update(gate)
    result["stage"] = "complete"
    result["draft_path"] = str(scratch_dir / target_name)

    # Out-of-scope-definition check: only meaningful once the gate has passed on the model's
    # own assigned scope -- a gate failure already means the draft is discarded regardless of
    # what else it defined.
    if result["gate_passed"] and target_functions:
        referenced = referenced_module_functions(test_text, target_path.stem)
        if held_out_text:
            referenced |= referenced_module_functions(held_out_text, target_path.stem)
        extra = out_of_scope_definitions(code, referenced, target_functions)
        if extra:
            result["gate_passed"] = False
            result["stage"] = "out_of_scope_definition"
            result["out_of_scope_names"] = extra
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["implement", "test-gen"])
    parser.add_argument("--contract-file", help="Task contract text (implement mode)")
    parser.add_argument("--test-file", required=True, help="Real, already-written visible test file")
    parser.add_argument("--target-file", required=True,
                         help="Intended real destination path (read for its basename only -- "
                              "never written by this script)")
    parser.add_argument("--held-out-file", help="Optional held-out test file")
    parser.add_argument("--target-tests",
                         help="Comma-separated pytest -k selectors (e.g. class or test names) "
                              "scoping the visible test file to this task's own tests, when the "
                              "file also covers other tasks' functions. Requires --target-functions.")
    parser.add_argument("--held-out-tests",
                         help="Comma-separated pytest -k selectors scoping the held-out file, if "
                              "given. Independent of --target-tests -- a held-out file holds "
                              "different tests by definition.")
    parser.add_argument("--target-functions",
                         help="Comma-separated function names this task is actually responsible "
                              "for -- required with --target-tests. Used both to tell the model "
                              "its scope explicitly and to reject a draft that also defines "
                              "another task's function (out-of-scope-definition check).")
    parser.add_argument("--repo-root", help="Defaults to discovering .git upward from cwd")
    args = parser.parse_args()

    if args.mode == "test-gen":
        print(json.dumps({"attempted": False,
                           "reason": "test-gen mode not implemented yet"}))
        return 0

    if not args.contract_file:
        parser.error("--contract-file is required for implement mode")
    if args.target_tests and not args.target_functions:
        parser.error("--target-functions is required when --target-tests is given")

    result = run_implement(args)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
