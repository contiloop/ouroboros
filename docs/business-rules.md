# Business rules

Ouroboros is a coding-agent plugin that puts one agent, **L1**, in charge of a user's development
goal: L1 talks with the user until the goal is clear, takes a single approval, and then runs
development cycles through an installed **Dryforge** worker until the goal is met. The shipped
runtime implements exactly the behavior below.

## Vocabulary

| Term | Meaning in this project |
| --- | --- |
| **User** | The human who owns the goal. Talks only to L1. Never talks to L2/L3 directly. |
| **L1** | The Ouroboros agent. The user's continuing counterpart and the owner of execution after approval. Runs in the user's host session (Claude Code or Codex). |
| **L2** | A headless Claude Code session that L1 creates in the target project and keeps across cycles. Runs Dryforge Ready, then Dryforge Go, in the *same* session. May implement directly or spawn L3. |
| **L3** | Task agents (implementers, researchers, independent reviewers) that L2 creates under Dryforge's own rules. L1 never manages L3 directly. |
| **Dryforge** | A separately installed plugin providing the `ready`, `go` and `migration` skills. Ouroboros invokes the *installed* copy through the host's native skill mechanism. Ouroboros does not ship, patch or substitute its own copy. |
| **Proposal set** | The four documents L1 fills with the user during `init` (`scenario.md`, `validation.md`, `spec.md`, `delegation.md`) and the user approves as one. |
| **Work graph** | `workgraph.yaml`: the chunks (nodes) L1 plans after approval, one per cycle, each owning workflow steps and validation items. |
| **Beta test** | The cycle in which L1 runs the scenarios end to end itself and judges every validation item; the only place a run becomes COMPLETE. |
| **Cycle** | One Ready → Go run by one L2 session against one bounded outcome. |
| **Checkpoint** | The accepted Git state (branch/commit) a cycle leaves behind; the next cycle starts from it. |

## Lifecycle

```
init  ──(conversation, revisable)──▶  Proposal  ──approve──▶  ACTIVE  ──cycles──▶  COMPLETE
                                                                  │
                                                                  └─ user may keep talking; L1 folds in-scope clarification into work
```

### `init` — the interview and the proposal set
- Starts L1. L1 reads the selected project and any existing Ouroboros records, then interviews the
  user to fill four documents under `.dryforge/ouroboros/`: **`scenario.md`** (usage scenarios whose
  steps carry a generalized `step:` label, and the Workflow derived from them), **`validation.md`**
  (items with Behavior, Environment, Evidence and Cost), **`spec.md`** (Users, UI references, Outline
  of blocks and their function, Efficient checks for slow/hard items), **`delegation.md`** (delegated
  judgment, L2/L3 models, limits, workspace). The interview follows elicitation discipline: scenarios
  first, then the decisions they imply, validation, the product's shape, delegation; the project
  answers what it can, the user answers only what only they hold, technical choices are presented
  with a recommendation (`src/skills/init/references/interview.md`).
- The set is **revisable** for as long as the user wants and is shown to the user after every round.
- **No cycle may run while the set is unapproved.** Read-only inspection and draft edits are the
  only permitted actions. Running Migration, Ready or Go during this stage is a defect.
- Invoking `init` again on a project with an active run does **not** reset the run, refill budgets
  or discard history; it continues the conversation about changes.

### `approve` — the single handoff
- `approve` is the user's approval of the four documents **exactly as last shown**. The record
  checks completeness (every required item of every file; a refusal names the file and the item)
  and the shown digest; if the set is missing, incomplete or has changed since it was shown, L1
  shows the concrete gap (a diff per changed file) instead of treating the invocation as approval.
- Approval is a **handoff, not the end of the conversation**. After it L1 owns execution; the user
  keeps talking; L1 incorporates clarification within the agreed scope and discusses the impact of
  changes that need a new decision before dependent work proceeds.
- Repeating `approve` on an active run changes nothing: same authority, same session, same consumed
  limits.

### Delegation after approval — **full, with no exceptions**
- Once the user has approved, **L1 holds complete authority to finish the goal.** It answers every
  worker question (structured or plain text), approves Ready documents, acts on anything a turn
  reports (automatically allowed permission requests included),
  merges, pushes, tags, and performs any other action the goal requires. The user is not asked to
  confirm individual cycles, tool calls, merges or releases.
- The user's role during execution is to receive progress and results and to add clarification.
  Routine progress updates need no reply.
- **Counter-case:** there is no category of action L1 must route back to the user merely because it
  is "risky" (merge, deploy, spend, delete, disclose). The only things L1 brings back are (a) a
  genuine change to the approved goal/scope that the user did not delegate judgment on, and (b)
  a blocker L1 cannot resolve with any available means. Everything else is L1's decision.
- L1 records its decisions as L1. It never presents its own decision as the user's.

### The work graph
After approval (after Migration when needed) L1 writes `workgraph.yaml` in the record: nodes with
`id`, `title`, `depends`, the workflow `steps` and validation `items` they realize, and a `status`
(pending / active / done / replanned). One node = one cycle. Every workflow step and every validation
item belongs to a node; unowned ones are reported to the user as information. If the node count
exceeds `max cycles`, L1 says so before starting. The graph is the only document L1 edits on its own
after approval; the four documents change only through a revision the user approves. The graph is
shown to the user as progress, never as a question.

### Running a cycle
1. **Choose work.** L1 takes the next node whose dependencies are done and opens a development
   cycle for it. One cycle targets one repository.
2. **Prepare L2.** L1 continues the run's recorded L2 session by default; it starts a fresh one
   only when none exists, after REPLAN, when the session cannot be resumed, when its context is near
   its limit, or for Migration. L1 records the real session identity; a process ID or a one-shot
   summary is not a session.
3. **Ready.** L1 explicitly invokes the installed Dryforge `ready` skill in L2 with the node's goal
   and the whole picture it holds: the Workflow and the scenarios the node serves, the validation
   items it must satisfy (with the request to verify them and leave evidence), the outline blocks it
   touches, what earlier nodes delivered, the checkpoint. `delegation.md` and the record are never
   quoted. L2 asks questions; L1 answers them from the user's intent.
4. **Approve Ready.** L1 reads the actual specification, plan and handoff documents (not a summary)
   plus the independent review evidence, requests corrections if needed, then approves the exact
   documents and invokes installed Dryforge `go` **in the same L2 session**. Changed documents need
   renewed review before Go.
5. **Review results.** L1 checks requirement coverage, that tests actually ran, independent review
   evidence and unresolved issues. In-scope corrections go back to the same L2 as rework. Acceptance
   lets L2 finish archive, integration and cleanup; L1 receives the final commit/branch.
6. **Evaluate.** L1 records one of CONTINUE (more work, goal advancing), REPLAN (approach must
   change; nodes are added or rewritten), ESCALATE (a real user decision is needed). **A finished
   node is not a finished goal**; COMPLETE is reserved for the beta test.

### The beta test
When every node is done, L1 opens a **beta cycle** (no worker turns; not counted toward `max
cycles`) and runs the scenarios end to end itself, as the user would: for each validation item the
Evidence check, or the efficient check from `spec.md` for slow/hard items, recording each result as a
`beta` event. An item only a human can check (visual, device, external account) is raised as
ESCALATE naming the exact check; the user's answer is recorded as a `verified` event and the beta
test continues in a new beta cycle (this ESCALATE is not a stalled cycle). A failed item leads to
REPLAN, new nodes and cycles, then a new beta cycle for the affected items. **COMPLETE is the
evaluation of a beta cycle in which every item has a verdict**; the record refuses COMPLETE anywhere
else. Models: the L2 model from `delegation.md` is the session's model, the L3 model is applied to
the worker process so Dryforge's task agents use it; `default` means the host's default.

### Migration (existing projects only)
- When an existing codebase has no project documentation for agents, L1 may first assign the
  installed Dryforge `migration` skill to a fresh worker, answer its questions, review the produced
  docs and independent review, and then arrange the Git checkpoint of those docs. Migration writes
  documentation only; it never implements product code or commits by itself.
- After Migration, Ready–Go starts in a **fresh** worker session. New projects and projects that
  already carry documentation skip Migration. A new session or a new checkout is **not** by itself a
  reason to run Migration again.

### Interruption and recovery
- On interruption (timeout, disconnection, host failure) L1 reconciles actual effects and live
  child agents first, then resumes the **recorded** L2 session. Replacing L2 with a summary-fed new
  session is a handoff that needs an explicit decision; it is not a resume.
- Uncertain writes are never replayed automatically. A host "turn complete" receipt is never proof
  that a cycle completed.

## Invariants

- **One approval, one handoff.** Nothing executes before `approve`; after it, nothing needs a second
  user approval. Both halves are rules; a design that asks for per-action consent after approval
  violates the second half.
- **Same-session Ready and Go.** The L2 that produced the approved Ready documents is the L2 that
  runs Go. Design context from Ready must inform implementation.
- **L1 is the only caller L2 sees.** L2 and L3 use Dryforge's ordinary caller interface; nothing in
  the worker prompt reveals Ouroboros identity, private records or approval bookkeeping. Dryforge
  never needs to know whether its caller is a human or L1.
- **Installed Dryforge, not a bundled copy.** If the installed skill is missing or ambiguous, that is
  a capability gap to report, not a reason to paste procedure text into a prompt.
- **Evidence over claims.** Acceptance, completion and recovery decisions rest on actual documents,
  actual test output, actual Git state and independent review, never on a worker's self-report.
- **Intent changes commit at cycle boundaries.** An approved change to goal, completion criteria,
  constraints, priorities or non-goals is recorded once, between cycles, with the user's actual
  approval. In-scope clarification during a cycle needs no such record.

## Edge cases

| Situation | Disposition |
| --- | --- |
| User invokes `approve` with no draft | Show that nothing was proposed; start `init` conversation. No approval recorded. |
| Proposal edited after it was shown, then `approve` | Show the diff; approval applies only to what the user has seen. |
| Installed Dryforge skill not found in L2's host | Report the missing capability to the user; do not start Go; keep the existing session. |
| L2 asks a structured question (its question tool) | The turn pauses, L1 receives the questions with their options, answers from the proposal and its judgment (`session-answer`), and the turn continues. Several rounds per turn are possible. Question and answer are recorded. |
| L2 asks a question outside the approved scope | L1 decides under full delegation if the goal still determines the answer; brings it to the user only if the goal itself is ambiguous. |
| User stops while a question is open | The question is recorded as unanswered; the same session can be continued later. |
| A cycle ends with failing tests | Not acceptable; L1 requests rework in the same L2 or replans. |
| Cycle limit, stall limit or budget reached | The stall and budget limits stop the run at once. The cycle limit counts development cycles: at the limit a development cycle cannot open and asking for more development (REPLAN, or ESCALATE on a development cycle) stops the run; a beta cycle may still open. L1 reports; a revised `delegation.md` approved again resumes it. |
| A validation item only a human can check | L1 raises ESCALATE from the beta cycle naming the exact check; the user's answer is recorded as `verified`; the beta test continues. This is a verification, not a consent. |
| An older single-file proposal record (`proposal.md`) is found | Reported as legacy; archived by `draft` (an ACTIVE one must be stopped first); never converted. |
| Worker session lost mid-cycle | Reconcile effects, resume the same session; otherwise explicit, recorded replacement with the checkpoint and decisions. |
| User asks to stop | The running turn is killed at once, the run is STOPPED with its last stage and checkpoint, half-done branches and worktrees are listed, nothing is cleaned up. `approve` again (same or revised proposal) resumes it; `archive` then `init` starts a different goal. |
| Project without `.dryforge/` in `.gitignore` at `init` | L1 appends that one line (uncommitted) and says so; the only pre-approval write outside `.dryforge/`. |
