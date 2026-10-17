# spec: local-model fit and delegation markers

Read from `SKILL.md` when the local-model-fit answer might be yes, or before writing a `(local-delegate: implement)` task's contract.

## Contents
- The checkpoint
- Marking a task `(local-delegate: implement)`

## The checkpoint

Briefly note whether a local small model could plausibly power any part of the tool, and if so whether the fit is **retrieval** (cheap, citable, no confabulation risk) or **generation** (needs a propose, deterministic gate, act structure before anything it produces is trusted). Favor a stronger deterministic rule over a probabilistic guess wherever one exists or can be found instead. If it is genuinely not applicable, say so in one sentence and move on. This is a checkpoint to consider every time, not a bias toward using one.

If a local generative runtime is available to you, weigh it the same way: it is a plausible fit for the generation half of a propose, deterministic gate, act pipeline, but not for open-ended judgment or QA work with no deterministic gate (code review, correctness verification). Keep that kind of work on a full model regardless of how tempting "it's free and local" is.

## Marking a task `(local-delegate: implement)`

The marker is a *request* for a free local-model draft before `execution-gate` and `build` spend a turn on the task, via the optional `local-delegate` component (see its own README for the full mechanism and when it is worth setting up). A task may carry it only if **all** of these hold:

1. Its own text states the function's contract.
2. It either names an existing visible test file or an earlier task in the same breakdown creates one. **If the marked task's test file is not written by an earlier task, write a minimal visible test file for it as part of drafting this design** (a handful of assertions covering the contract).
3. The task's own target file does **not** already exist in the tree. Implement mode is a whole-module generator; marking a task against an existing file risks a passing draft silently overwriting real content.

Vague contracts do not get the marker: an underspecified prompt risks a plausible-looking but wrong implementation, the same failure any code-generation task risks when the contract is fuzzy.

If the marked task's visible test file is a **shared file also covering other tasks' functions**, the task's own text must name its scope: either write a module-scoped visible file just for this task, or add explicit `Target functions: <names>` and `Test classes or selectors: <names>` lines to the task text, which `execution-gate` and `build` pass through to the runner as `--target-functions` and `--target-tests`. Keep that scoping out of the marker itself, which stays the single token `(local-delegate: implement)`.

Whether anything runs on a marker depends entirely on whether your own recorded configuration names a local-delegate model for that mode (`execution-gate` checks this, not `spec`); an unconfigured repo (the default, unless you have set one up) pays nothing for a marker that never fires.
