export const meta = {
  name: 'implement-queue',
  description: 'Implement approved design docs in parallel, one worktree per item, with a bounded QA fix loop and blocked-item escalation',
  phases: [
    { title: 'Implement' },
    { title: 'QA' },
    { title: 'Docs' },
  ],
}

// The reasoning behind every choice below lives inline in the comments on the stages themselves
// (GIT_BOUNDARY, BLOCK_BAR, and each stage's own comment) - there is no separate external design
// doc this file is implementing; read the comments in place rather than looking for one.

const STAGE_SCHEMA = {
  type: 'object',
  properties: {
    status: { type: 'string', enum: ['done', 'blocked'] },
    summary: { type: 'string' },
    worktreePath: { type: 'string' },
    blockingQuestion: { type: 'string' },
  },
  required: ['status', 'summary'],
}

const QA_SCHEMA = {
  type: 'object',
  properties: {
    findings: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          description: { type: 'string' },
          severity: { type: 'string' },
        },
        required: ['description', 'severity'],
      },
    },
    passed: { type: 'boolean' },
    requiresUserJudgment: { type: 'boolean' },
  },
  required: ['findings', 'passed', 'requiresUserJudgment'],
}

const GIT_BOUNDARY =
  'Read-only git is fine (status, diff, log, show). Never run git stash, git checkout/restore, ' +
  'git reset, or a bare git add - those mutate shared state this workflow depends on, even inside ' +
  "your own worktree, since a later stage in this same item's chain may still need an earlier " +
  'stage\'s uncommitted work intact. Never touch CLAUDE.md, BACKLOG.md, BACKLOG_ARCHIVE.md, or ' +
  'MISTAKES.md, and ' +
  'never run git commit - those are handled centrally, sequentially, after this workflow returns. ' +
  'You are one stage in a fixed pipeline (implement, then QA via code-reviewer, then docs) - never ' +
  'spawn your own nested review/QA pass or otherwise act outside your own stage\'s job, even if you ' +
  'think it would help; a later stage already exists for that and doing it yourself is exactly the ' +
  'kind of scope creep this workflow guards against. ' +
  'Never run git push, or any command that publishes to a remote or triggers external CI - in this ' +
  'repo or in any OTHER repo the design doc touches (e.g. a separate deploy repo). If the remaining ' +
  "work genuinely requires a push, stop before doing it and report status 'blocked' with a " +
  'blockingQuestion asking for explicit confirmation of that specific push - a remote push is a ' +
  'materially higher-stakes action than anything else this workflow does locally, and needs your own ' +
  'go-ahead every time, not standing authorization.'

const BLOCK_BAR =
  "If you hit something the design doc didn't anticipate and a reasonable person could genuinely go " +
  'either way on - an ambiguous design choice, a surprising fact contradicting an assumption the doc ' +
  'baked in, anything destructive or hard-to-reverse, or a scope question that changes what "done" ' +
  "means - stop before making that change. Report status 'blocked' with a specific, concrete " +
  'blockingQuestion instead of guessing. This design doc already went through approval, so blocking ' +
  'should be the exception (a genuine unanticipated surprise), not a routine judgment call.'

// items: [{designDocPath, backlogEntryText, toolName}, ...] - the confirmed batch. designDocPath is
// a bare filename relative to this repo's design_docs_dir (default "Design Docs/"), e.g. "some-slug.md"
// - never a path already including that directory, and never a path with its own subdirectories.
const items = args

const results = await pipeline(
  items,

  // Stage 1: implement, in its own worktree. Reports that worktree's own path - every later stage
  // for this item operates inside it instead of getting its own fresh worktree (isolation:'worktree'
  // is per-agent()-call, not per-item-chain).
  (prevResult, item, index) => agent(
    `Implement Design Docs/${item.designDocPath} task-by-task, for the tool "${item.toolName}". ` +
    'Read the design doc fully first. ' +
    `Current status of this item, from its BACKLOG.md entry (treat as ground truth for what's ` +
    `already done - some or all of this design may already be built): ` +
    `${item.backlogEntryText || 'No existing BACKLOG.md status - this is a fresh, untouched design.'} ` +
    'Work through only the task breakdown steps that status shows are NOT yet done, verifying per ' +
    "the design doc's own Verification section as you go. Never redo or regenerate something the " +
    'status says already exists (e.g. a generated keystore, a completed migration) - if verifying an ' +
    "already-done step seems necessary, verify it non-destructively rather than rebuilding it. If " +
    "that verification needs a locally-running dev server of your own and other items in this batch " +
    "might run one too, pick a port that avoids collision with them (e.g. offset a base port by this " +
    `item's index) rather than assuming a fixed port is free. ` +
    "Report your own worktree's absolute path in the 'worktreePath' field of your structured output " +
    `- get it via \`git rev-parse --show-toplevel\`. ${GIT_BOUNDARY} ${BLOCK_BAR}`,
    { label: `implement:${item.toolName}`, phase: 'Implement', schema: STAGE_SCHEMA, isolation: 'worktree' }
  ),

  // Stage 2: QA via the real code-reviewer subagent, bounded 2-iteration fix loop. Gates on a prior
  // block instead of relying on pipeline()'s throw-based skip, which would destroy blockingQuestion.
  // A finding that meets the blocking bar (destructive, ambiguous, scope-changing) escalates
  // immediately, skipping the fix loop entirely - only an ordinary fixable bug goes through it.
  async (prevResult, item, index) => {
    if (prevResult.status === 'blocked') return prevResult
    const worktreePath = prevResult.worktreePath

    const escalate = (qa) => {
      const stillOpen = qa.findings.map(f => `${f.severity}: ${f.description}`).join('; ')
      return {
        status: 'blocked',
        summary: 'A QA finding requires user judgment rather than an ordinary fix',
        worktreePath,
        blockingQuestion: `code-reviewer flagged something that isn't a routine fixable bug: ` +
          `${stillOpen}. How should this be resolved?`,
      }
    }

    let qa = await agent(
      `Delegating to code-reviewer: verify the implementation in ${worktreePath} against ` +
      `Design Docs/${item.designDocPath}. Operate entirely inside ${worktreePath} - never touch the ` +
      `main working tree. ${GIT_BOUNDARY} Independently re-check the implementation against the ` +
      "design doc's task breakdown and re-run its Verification section rather than trusting the " +
      "implementer's own claim. Report findings as a list of {description, severity}, 'passed': " +
      "true only if nothing needs fixing, and 'requiresUserJudgment': true if any finding is not an " +
      `ordinary fixable bug but something a reasonable person could go either way on. ${BLOCK_BAR}`,
      { label: `qa:${item.toolName}`, phase: 'QA', schema: QA_SCHEMA, agentType: 'code-reviewer' }
    )
    if (qa.requiresUserJudgment) return escalate(qa)

    let iterations = 0
    while (!qa.passed && iterations < 2) {
      iterations++
      const fix = await agent(
        `Fix these code-reviewer findings, working entirely inside ${worktreePath} (not the main ` +
        `tree): ${JSON.stringify(qa.findings)}. This is against Design Docs/${item.designDocPath}. ` +
        `${GIT_BOUNDARY} ${BLOCK_BAR}`,
        { label: `fix:${item.toolName}:${iterations}`, phase: 'QA', schema: STAGE_SCHEMA }
      )
      if (fix.status === 'blocked') return { ...fix, worktreePath }

      qa = await agent(
        `Delegating to code-reviewer: re-verify the implementation in ${worktreePath} against ` +
        `Design Docs/${item.designDocPath}, after a fix pass for: ${JSON.stringify(qa.findings)}. ` +
        `${GIT_BOUNDARY} Report findings + passed + requiresUserJudgment as before. ${BLOCK_BAR}`,
        { label: `qa:${item.toolName}:${iterations}`, phase: 'QA', schema: QA_SCHEMA, agentType: 'code-reviewer' }
      )
      if (qa.requiresUserJudgment) return escalate(qa)
    }

    if (!qa.passed) {
      const stillOpen = qa.findings.map(f => `${f.severity}: ${f.description}`).join('; ')
      return {
        status: 'blocked',
        summary: 'QA did not pass after 2 fix iterations',
        worktreePath,
        blockingQuestion: `code-reviewer still finds problems after 2 fix attempts: ${stillOpen}. ` +
          'How should this be resolved?',
      }
    }
    return { status: 'done', summary: `Implemented and QA-passed (${iterations} fix iteration(s))`, worktreePath }
  },

  // Stage 3: docs, via the real docs-writer subagent, restricted to this item's own tool-specific
  // NOTES.md - never CLAUDE.md/BACKLOG.md, those are centralized after the workflow returns.
  (prevResult, item, index) => {
    if (prevResult.status === 'blocked') return prevResult
    return agent(
      `Delegating to docs-writer: sync ${item.toolName}'s own NOTES.md (create one only if this ` +
      `tool's established convention already uses one; otherwise skip) to reflect the ` +
      `implementation in ${prevResult.worktreePath}, per Design Docs/${item.designDocPath}. Operate ` +
      `entirely inside ${prevResult.worktreePath}. ${GIT_BOUNDARY}`,
      { label: `docs:${item.toolName}`, phase: 'Docs', schema: STAGE_SCHEMA, agentType: 'docs-writer' }
    ).then(r => ({ ...r, worktreePath: prevResult.worktreePath }))
  }
)

return results
