# local-delegate

An optional gate that lets `/build` try a free local-model draft — via a locally-running model
runtime compatible with [Ollama](https://ollama.com)'s HTTP API — before spending a turn of your
main model on a task, when that task has a written contract and a real, already-written test file
to gate the draft against.

**Off by default, and safe to leave off.** With no `local_delegate` value in your recorded
configuration, `/build` behaves exactly as if this component didn't exist — every task runs on
your main model, same as before. This is a pure cost optimization for a narrow, well-specified
task shape, never a quality tradeoff you're forced to accept: any draft that doesn't pass its own
gate is discarded, and the task falls back to being implemented on your main model exactly as if
the flag had never been set.

## What it actually does

For a task marked `(local-delegate: implement)` in a design's own task breakdown (see `spec` and
`execution-gate`'s own sections on this), `/build` calls this script instead of drafting the code
itself:

1. **Configuration check, fail closed.** No model recorded for this mode → not attempted, no cost.
2. **Target-existence check, fail closed.** This script only ever generates a *whole new module* —
   if the target file already exists, a passing draft would silently overwrite real content, so it
   refuses before even calling the model.
3. **GPU pre-check, fail closed.** If your GPU looks busy (or `nvidia-smi` isn't available at all —
   permanently true on non-NVIDIA hardware), it doesn't attempt a draft that would just queue behind
   real work or run painfully slowly on CPU.
4. **Draft**, via a single call to the configured model, into an isolated scratch directory under
   `.claude/state/local-delegate/<run-id>/`. Your real repo tree is only ever *read*, never written,
   by this script.
5. **Gate**: runs your visible test file (and a held-out file, if you provide one) against the
   draft. If the test file also covers other tasks' functions, `--target-tests`/`--held-out-tests`
   scope which tests actually run, and `--target-functions` rejects a draft that also defines
   someone else's function alongside its own.
6. **Reports a structured JSON result.** The calling skill decides what to do with it — copy a
   passing draft into the real tree, or fall back to implementing the task itself on any failure.
   This script never writes anywhere outside its own scratch directory.

A gate failure, a timeout, or a "wiring error" (a mistyped test selector, a missing precondition)
all mean the same thing to the calling skill: implement the task yourself, exactly as if the flag
had never been set. The task still gets its normal review — this only ever substitutes for the
*drafting* turn, never for review.

## Configure it

Add a `local_delegate` value to your resolved `.claude/phase-gate-install/variables.json`:

```json
{
  "local_delegate": {
    "implement": "your-model-name"
  }
}
```

Any model your local runtime can serve at `http://localhost:11434/api/chat` (Ollama's default) will
work; there's no hardcoded model name. A model reasonably capable at code generation, with fast
enough inference to actually be worth the wait over your main model, is the right kind of choice —
this component doesn't validate model quality for you.

Ships with `local_delegate` empty (`{}`) — the installer never prompts for it. Most adopters will
never configure this, and that's the expected, fully-supported default.

## Prerequisites

- **A local model runtime** serving Ollama's HTTP chat API, with your configured model already
  pulled. Missing → the flag simply never fires; no error, no prompt, plain Bucket A behavior.
- **The Python `requests` package.** Missing → the runner fails at import and reports "not
  attempted," never a crash.
- **`nvidia-smi`** on `PATH`, for the GPU busy-check. Missing, erroring, or reporting high
  utilization → treated as busy, no attempt. On non-NVIDIA hardware this makes the feature
  permanently inert — a deliberate, accepted tradeoff for a silent, safe-by-default feature, not a
  bug to work around.

## Limitations

- **Only generates whole new modules.** Adding a function inside an existing file is not a
  supported or tested shape — the target-existence check above refuses it outright rather than
  risking a passing draft silently destroying real content.
- **Validated only on small, genuinely isolable functions** with no surrounding codebase
  dependencies. A function that needs to fit existing conventions or share state with other code in
  the same file is outside what this has been tested against.
- **Scratch directories under `.claude/state/local-delegate/<run-id>/` are never cleaned up.**
  Gitignored, so they don't pollute your repo, but they do grow unboundedly over time. Not a
  correctness problem — a housekeeping one, left for you to handle (a periodic manual clear, or a
  cron job) if it ever matters in practice.
- **This is a mechanical cost gate, not a code-review substitute.** A passing gate means the draft's
  tests pass — it says nothing about code quality, style, or whether the tests themselves were
  adequate. Keep whatever review step you'd otherwise run on hand-written code.
- **The wall-clock case depends entirely on your model and hardware.** A slow local model that
  usually fails the gate can easily cost *more* wall-clock time than just implementing the task
  directly, since a failure means a wasted draft attempt followed by the same implementation work
  anyway. Watch your own real outcomes before assuming this saves time as well as spend.

## CLI

```
python local_delegate_runner.py implement \
  --contract-file <path>       # the task's own written contract, verbatim
  --test-file <path>           # a real, already-written visible test file
  --target-file <path>         # intended real destination (read for its name only, never written)
  [--held-out-file <path>]     # optional held-out test file, for a stricter gate
  [--target-tests <selectors>] # comma-separated pytest -k selectors, when the visible test file
                                # also covers other tasks' functions
  [--held-out-tests <selectors>]
  [--target-functions <names>] # comma-separated function names this task actually owns
  [--repo-root <path>]         # defaults to discovering .git upward from cwd
```

Prints a single JSON object to stdout. Key fields: `attempted` (bool), `gate_passed` (bool, only
meaningful if `attempted`), `stage` (where it stopped, if it didn't reach `"complete"`),
`wiring_error` (bool — a setup mistake, distinct from a genuine draft/gate failure), and
`draft_path` (the scratch-directory path to copy from, on a real pass).
