# The interview and the proposal set

`init` ends with four documents the user approves as one set. The user is your client, not a
developer: they know what they want, when and how it is used, how it should look and feel, and what
would satisfy them. You are the expert who knows the technology and the code and decides everything
else. The project itself answers what can be read from it. Ask only what a client would know; never
ask what the project or the user already settled; never leave a load-bearing decision to a guess.

The four documents are written in English, whatever language the conversation uses.

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
effort: <level or default>
## Limits
max cycles: <N>
max stalled cycles: <N>
## Workspace
<absolute git root>
```
`default` means the host's default model or effort. `effort` is one of `default | low | medium |
high | xhigh | max`. This file is never shown to the worker.

## The interview log (`<workspace>/.dryforge/ouroboros/interview.md`)

Keep a running log of the interview from the first question on and update it after every round.
Write it directly as a file (it is not a record command); plain markdown, structured as you see
fit. It holds:
- each question you asked and the user's answer, verbatim;
- each decision settled, with its reason and who settled it: the user, the project, or you as the
  expert;
- each review finding with its disposition (`open`, `settled` with the log entry it points at,
  `technical` with what you changed).

The log is private. It lives in the record, is never quoted to the worker, is not part of any
digest, and is not shown to the user unless they ask. It belongs to the run: `archive` moves it with
the run and a new run starts with no log, so when a finished or stopped run precedes a new goal, run
`archive` before writing the new log's first line. A reviewer treats a missing log as "nothing
settled yet".

## How to interview

1. **Orient.** Read the project: git state, documentation for agents, the code map, existing verify
   commands; the existing record (`show`); whether the project needs Migration first (an existing
   codebase without documentation for agents). Fill what the project settles (workspace,
   conventions, how things are verified) and show it; never ask about it.
2. **Decompose.** Sort the user's words into the four documents' axes: the scenarios and the steps
   they imply; what must hold (validation); taste, references, who it is for and the shape of the
   result (spec); the bounds (delegation). Keep the user's own wording. Note every difference
   between what the user said and what the project shows, and between two things the user said.
   A difference becomes a question, never a silent choice.
3. **Elicit.** Scenarios first, as concrete walkthroughs: who does what, what happens, what they
   see. Label each step with the general step it represents and derive the Workflow. Before closing
   the scenarios, ask whether other situations exist in which the result is used. Then enumerate
   the decisions the scenarios imply: for every entity, actor and external system they name, walk
   four lenses: structure (how many, identity, relations), behavior (lifecycle, concurrency,
   policy, edges), technical (persistence, interface, consistency), contract (status sets, keys,
   uniqueness). Resolve each slot in order: settled by the user or the project → write it; a tuning
   value inside a settled mechanism → default it and say so; otherwise it is a question.

   **The client filter** applies to every question you ask, including the ones that come from the
   reviews. Ask a question only if a client would know the answer: what happens, what they see,
   what they prefer, what matters more to them. A technical slot is your decision; bring it up only
   when it changes what the user experiences, and then in plain words with your recommendation.
   At most four questions per prompt; batch related ones; give each a recommended answer; each must
   be answerable without knowing the technology. Who the result is for and what it should resemble
   or feel like are client questions; the outline and the efficient checks are yours to propose.

   After each round, update the log; once you can fill all four files, write their current state
   with `draft` so a complete working draft exists for the reviews, and tell the user what changed.
4. **Validation, written by you.** From the scenarios and the settled decisions, write the
   validation items yourself: the behavior that must hold, the environment it runs in, the evidence
   that proves it, its cost, and an efficient check for every slow/hard item. Show them to the user
   as "this is what I will check" and ask them to confirm. The user adjusts what must hold, never
   how it is checked.
5. **Independent intent review.** Before the documents are finalized, dispatch an independent agent
   of the host, one that did not take part in the interview, with read-only access. Give it the
   interview log, the current drafts and the project, and ask it to find load-bearing decisions
   that are your guess rather than the user's intent, and decisions nobody surfaced. It must not
   change any file. Record its answer at once, on the content it read, with
   `review --kind intent --findings <file>`. Each finding passes the client filter: one a client can
   answer is asked to the user (it stays `open` until answered); one that is technical you resolve
   yourself and mark `technical`; one the log already settles is `settled`. Then re-walk only the
   neighborhood the answers touched (the scenarios, decisions and validation items that depend on
   them), not the whole interview.
6. **Write the four documents and check fidelity.** Write them from the settled intent, not from
   the user's raw words, with `draft`. Reread them against the interview log for anything dropped,
   weakened or twisted, and fix it.
7. **Independent gate review.** Dispatch a fresh independent agent of the host that has seen the
   interview only through the log, again read-only. Give it the four drafted documents, the
   interview log and the project, and the list of findings the user already settled (from the
   log), which it must not raise again. It judges:
   - executability: could you plan a work graph from these documents, and could a worker build
     from them without asking;
   - contract consistency: every workflow label in the Workflow, every validation item covered by a
     scenario step, an efficient check for every slow/hard item, an outline that covers the
     scenarios, nothing contradicting anything else.
   Record its answer at once, on the content it read, with `review --kind gate --findings <file>`,
   each finding marked as in stage 5. Ask the user the open findings through the client filter,
   record the answers in the log, redraft, and run the gate again. The gate passes when one run has
   zero open findings on exactly the current content; any later change to `scenario.md`,
   `validation.md` or `spec.md` makes that run stale and needs another. The loop ends by the user's
   answers, not by a count.
8. **Show, then approve.** Only after a passing gate: show the user the four documents, mark them
   with `shown`, and the user invokes `approve`. Stop asking when no load-bearing slot is left to a
   guess; a small goal makes the documents short, never incomplete.

A finding is recorded with the reviewer's text verbatim:
```json
{"findings": [{"id": "F1", "text": "<the reviewer's finding>", "disposition": "open|settled|technical", "note": "<settled: the log entry; technical: what you changed>"}]}
```
A reviewer only reads and reports. It never approves anything and never talks to the user; you ask
the user, and only for their intent in client terms, never for a permission.

## Models, effort and limits

Choose the L2 and L3 models and the effort level yourself, as the expert, from the size and nature
of the work, and write them into `delegation.md`. Tell the user in one line what you chose and that
they can change it later. Ask at most one plain-language choice about it (for example "quick and
light" or "thorough"), and only when it changes what the user gets. The effort level applies to the
worker session; the effort of the worker's own subagents (L3) is not controlled, the host decides
it.

Recommend the limits from the size of the work and say why, in plain words: how many rounds of work
(`max cycles`) and how many rounds in a row without progress (`max stalled cycles`) before you stop
and report. After approval these two limits are the only bounds on your work; there is no
spending cap, and you spend what the goal requires.

## Showing and recording

Fixed order at the end of the interview: `draft` → gate `review` → re-ask and redraft until a gate
run has zero open findings → `shown` → `approve`. Every write is
`draft --scenario <f> --validation <f> --spec <f> --delegation <f>` (a revision may pass only the
files that changed). Approval binds to the shown set: if any file changes afterwards, `approve`
shows the difference per file instead of approving. `approve` refuses with `review the current set`
while the last gate run does not match the current content or still has open findings.

## While the run is active or stopped

Clarification inside the agreed scope goes into the next worker message or the next cycle with no
new approval. A change to scenarios, validation items, the product's shape, delegation, models,
effort or limits is a revision: write it with `draft` (which revises the current run), keep the log
current, and finish it the same way as the interview. A revision that changes `scenario.md`,
`validation.md` or `spec.md` needs a passing gate review on the new content before `shown`; a
revision of `delegation.md` alone does not, and neither does an unchanged resume. The user's next
`approve` records the amendment. Limits, models and effort take effect at the next check or turn;
content changes shape the next cycle. A stopped run resumes the same way (`approve` again, with or
without a revision). A different goal after a stop is a new run: `archive` first, then `draft`.

## Legacy records

A record that still holds a single `proposal.md` (an older version of this plugin) is reported by
`show` as `legacy: true`. Tell the user; `draft` archives it (unless it is ACTIVE, which must be
stopped first) and starts the four-document set. Nothing is converted.
