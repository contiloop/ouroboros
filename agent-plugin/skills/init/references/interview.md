# The interview and the proposal set

`init` ends with four documents the user approves as one set. You fill them by interviewing the
user with the discipline of a good design partner: the user owns the domain (what the result is
for, how it is used, what must hold), you own the technical shape (propose options with a
recommendation), and the project itself answers what can be read from it. Never ask what the
project or the user already settled; never leave a load-bearing decision to a guess.

## The four files (`<workspace>/.dryforge/ouroboros/`)

### `scenario.md` — usage scenarios and the workflow they imply
```
## Scenarios
### <scenario title>
1. <what the user does or what happens> — step: <generalized label>
2. … — step: <label>
### <another scenario>
…
## Workflow
- <label>: <one line on what this step does>
- <label>: …
```
Every step ends with ` — step: <label>`; the same label is reused wherever the same general step
recurs. `## Workflow` lists each distinct label once, in order. At least one scenario; every label in
the Workflow.

### `validation.md` — what must be verified
```
## Items
### V1 <title>
Behavior: <what must hold, observable>
Environment: <where and how it runs: OS, runtime, services, data>
Evidence: <what proves it: command and expected output, file, screenshot, log>
Cost: fast | slow/hard (<why, when slow/hard>)
covers: <label>, <label>
```
At least one item; all four fields non-empty; ids `V1`, `V2`, … unique.

### `spec.md` — the product's shape
```
## Users
<who it is for>
## UI references
<styles or products to resemble, or: none>
## Outline
- <block>: <its function>
- …
## Efficient checks
V3: <a cheaper way to check the slow/hard item V3>
(or: none, when no item is slow/hard)
```
Users and Outline non-empty; UI references may be `none`; an Efficient checks entry is required for
every item whose Cost is slow/hard.

### `delegation.md` — what L1 holds and within what bounds
```
## Delegated judgment
<what L1 decides without asking; default: everything after approval>
## Models
L2: <model name or default>
L3: <model name or default>
## Limits
max cycles: <N>
max stalled cycles: <N>
budget usd: <number> | no cap
## Workspace
<absolute git root>
```
`default` means the host's default model. This file is never shown to the worker.

## How to interview

1. **Orient on the project.** Read git state, existing documentation for agents, the code map.
   Fill what the project settles (workspace, whether Migration is needed, conventions, existing
   verify commands) and show it; do not ask about it.
2. **Scenarios first.** Ask for the situations in which the result is used, as concrete
   walkthroughs: who does what, what happens, what they see. Label each step with the general step
   it represents. Before closing, ask whether other scenarios exist. Derive the Workflow and show it.
3. **Enumerate the decisions the scenarios imply.** For every entity, actor and external system the
   scenarios name, walk four lenses: structure (how many, identity, relations), behavior (lifecycle,
   concurrency, policy, edges), technical (persistence, interface, consistency), contract (status
   sets, keys, uniqueness). Resolve each slot in order: settled by the user or the project → write
   it; a tuning value inside a settled mechanism → default it and say so; otherwise it is a question.
4. **Validation from the scenarios.** For each workflow step and each load-bearing decision, draw
   out what must be verified, where it runs and what counts as evidence. Mark items that are slow
   or hard and get an efficient check for each.
5. **Present the product's shape.** Propose users, UI references and the outline from the project
   and the scenarios; where the user would plausibly have a preference, present options with a
   recommendation and let them choose.
6. **Delegation and limits.** Present the defaults (everything delegated; models `default`; limits
   you recommend from the size of the work, with the reason) and let the user adjust. Explain that
   the limits are the only thing bounding L1 after approval.
7. **Rhythm.** At most four questions per prompt, each with a recommended answer; batch related
   ones. After each round write the four files with `draft` and mark them with `shown`, and show
   the user what changed. Stop asking when no load-bearing slot is left to a guess; a small goal
   makes the documents short, never incomplete.

## Showing and recording

Every showing = `draft --scenario <f> --validation <f> --spec <f> --delegation <f>` (a revision may
pass only the files that changed) followed by `shown`. Approval binds to the shown set: if any file
changes afterwards, `approve` shows the difference per file instead of approving.

## While the run is active or stopped

Clarification inside the agreed scope goes into the next worker message or the next cycle with no
new approval. A change to scenarios, validation items, the product's shape, delegation, models or
limits is a revision: write it with `draft` (which revises the current run), run `shown`, and the
user's next `approve` records the amendment. Limits and models take effect at the next check or
turn; content changes shape the next cycle. A stopped run resumes the same way (`approve` again,
with or without a revision). A different goal after a stop is a new run: `archive` first, then
`draft`.

## Legacy records

A record that still holds a single `proposal.md` (an older version of this plugin) is reported by
`show` as `legacy: true`. Tell the user; `draft` archives it (unless it is ACTIVE, which must be
stopped first) and starts the four-document set. Nothing is converted.
