# spec: the phase-record convention

Read from `SKILL.md` whenever a phase section is added to or updated in a design doc. Other skills (`build`, `verify`, `ship`, `initiate`, `execution-gate`) write into and read these sections.

## Contents
- Heading grammar
- Status vocabulary
- Write on entry
- The section table
- Avoid load-bearing words

## Heading grammar

Always `## <Phase> — <status>, <detail>`, for example `## Design review — pending, Opus` or `## Build — done, tasks 1-12`. One shape, no variants.

## Status vocabulary

Fixed: `pending`, `running`, `done`, `blocked-on-user: <what>`, `blocked-on: <who or what>`. `blocked-on-user` names a decision only the user can make (cheap to unblock: a review owed, a question not yet asked); `blocked-on` names an external party or event the user cannot unblock by deciding anything (a person, a release, an external event). The split lets a session-start ranker skill (`/initiate`, if you have it installed) sort "waiting on you" from "waiting on someone else" mechanically. A plain `blocked: <detail>` is still read as `blocked-on-user`, but write the explicit form and do not introduce new plain `blocked:` lines.

## Write on entry

A phase writes its own section, with a real status and never blank, the moment it is **entered**, and updates that same section in place when it closes. Without this, a section that does not exist yet and a phase that has not started look identical (the reason `## Execution strategy` is written `pending` at draft time rather than left absent).

## The section table

| Section | Written by | Notes |
|---|---|---|
| `## Intent` | `/spec`, opens the doc | Not `/backlog`: a `BACKLOG.md` entry is a bullet, not a `##`-headed doc |
| `## Summary` | `/spec`, right after `## Intent` | Plain language, 2 to 4 sentences, drafted last. Not a substitute for Problem and Approach, which stay the technical record |
| `## Problem` + `## Approach` | `/spec` | Pick this pair only: don't invent a `## Context` or `## Scope` variant |
| `## Design review` | the review gate | Declared `pending, <model>` at draft time, filled in when the review runs |
| `## Execution strategy` | `execution-gate`, run automatically by `/build` | Written `pending` if a backlogged design's breakdown looks substantial (3 or more tasks with a real delegation question, or several sub-parts), so the gate is visibly owed |
| `## Build` | `/build` | |
| `## Verification` | `/spec`, at draft time | The plan, not the record: a later phase must not overwrite it |
| `## QA gate` | `/verify` | The record, a different thing from the plan above |
| `## Shipped` | `/ship` | |
| `## Blocked` | any phase | |

## Avoid load-bearing words

Do not name a section with a word that means something else in AI tooling. `## Context` collides with the context window, context files and retrieved context; `## Problem` and `## Intent` collide with nothing. Apply this test to any future section name.
