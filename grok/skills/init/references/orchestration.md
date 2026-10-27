# L1 execution

You own the user's goal across cycles. You act as the ordinary caller of the installed Dryforge
skills: plan the work as a graph of chunks, create and keep one worker session (**L2**), answer its
questions, review its documents and results, and at the end test the result yourself the way the
user would. L2 is a headless Claude Code session in the target project; it runs Dryforge Ready and
Go in the same session and manages its own task agents (**L3**). You never manage L3 directly. The
approved documents live in `<workspace>/.dryforge/ouroboros/`: `scenario.md`, `validation.md`,
`spec.md` (the product's shape; distinct from Dryforge's own `.dryforge/spec.md`) and
`delegation.md`. All record and session commands are in `runtime.md`; every command takes
`--workspace <git root>` and `--owner <pid>` where the pid is this host process (`$CLAUDE_PID` on
Claude Code).

## Preconditions (once per run)

Run `doctor --host claude`. If `claude` is missing or the `dryforge` plugin is not installed and
enabled, report the missing capability to the user and stop; the run stays `ACTIVE`, nothing is
started. Never paste Dryforge procedure text or substitute another procedure.

## The work graph (once, before the first cycle)

After approval (and after Migration when the project needs it), write
`<workspace>/.dryforge/ouroboros/workgraph.yaml` from the Workflow in `scenario.md` and the items
in `validation.md`:

```yaml
nodes:
  - id: N1
    title: <one chunk of the work>
    depends: []
    steps: [<workflow labels this node realizes>]
    items: [V1, V3]
    status: pending      # pending | active | done | replanned
```

One node = one cycle (Ready → Go). Every workflow label and every validation item belongs to at
least one node; tell the user about any that do not (information, not a question). If the node
count exceeds `max cycles` in `delegation.md`, say so before starting; the limits still apply as
written. Show the graph to the user once it is written and again whenever its nodes or statuses
change, then start the loop. This file is the only document you
edit on your own after approval; a change to the four documents is a revision the user approves
(`interview.md`). Keep `status` current: `active` at `cycle-start`, `done` or `replanned` at
`evaluate`; a REPLAN or a failed beta test adds or rewrites nodes.

## The loop

1. **Choose work.** Take the next node whose dependencies are `done`. Record it with
   `cycle-start --kind development --goal <file> --checkpoint <commit>` (`--kind migration` for a
   Migration cycle) and mark the node `active`. If a previous cycle is still open (for example after
   an abort that was later resumed), close it first with `evaluate`. `max cycles` counts development
   cycles: when it is reached, a development `cycle-start` is refused; if nodes remain, report it
   and `stop --reason limit:cycles` (the user can raise the limit by revising `delegation.md`).
2. **Session.** Use the recorded session by default; design context carries across cycles. Start
   a fresh session (`--fresh --reason <why>`) only when there is none, after a `REPLAN`, when the
   recorded session cannot be resumed, when the last results show the context near its limit, or
   for Migration (which always gets a fresh session, and the Ready after it another fresh one).
3. **Ready.** `session-start --skill ready --message <file>` sends `/dryforge:ready` followed by
   your message, so the host loads the installed skill. The message is ordinary caller text and
   carries the whole picture you hold, not only this chunk: the node's goal; the Workflow and the
   scenarios this node serves, quoted from `scenario.md`; the validation items it must satisfy,
   quoted from `validation.md` with their evidence expectations, and the request that the worker
   verify them as part of its work and leave the evidence in the project; the outline blocks it
   touches, from `.dryforge/ouroboros/spec.md`; what earlier nodes delivered and the checkpoint. Never quote
   `delegation.md`, the record, or anything about Ouroboros, L1 or approvals. The models and the
   effort level in `delegation.md` are applied by the runtime on every turn (`--model` for L2, the
   subagent model for L3, `--effort` for the session).
4. **Wait.** Every turn runs detached. Run `session-wait` as a background shell command, end your
   turn with a one-line progress note for the user, and continue when the host tells you the wait
   finished. The wait ends either when the turn finishes or when the worker asks a question. Read
   the result (`state`, `text`, `questions`, `permission_denials`, `cost_usd`).
   - `QUESTION` → the worker asked with its question tool; the result carries the questions, each
     with its options. Choose from the proposal and your own judgment, write a JSON object mapping
     each question text to a label (a list of labels for a multi-select question, or
     `{"other": "<your text>"}`), run `session-answer --answers <file> --basis <file>` with your
     reasons, then `session-wait` again. The question and your answer are recorded automatically.
     A turn may ask several times; answer each round the same way;
   - a question in plain text (`COMPLETE` with a question in `text`) → answer it with
     `session-send` and record the basis with `event --actor L1 --kind answer`;
   - `COMPLETE` but the stage is not finished (turn limit, no question) → send a short continue
     message;
   - `INTERRUPTED` → inspect the workspace and `.dryforge/` of the target, then resume the same
     session with `session-send` and record `event --actor L1 --kind resume` with what you found;
     replacing the session is a recorded decision: `session-start --skill <stage> --fresh
     --reason <why>`, which re-sends `/dryforge:<stage>` to a new session;
   - a permission denial is part of the result: decide the next message yourself, never ask the
     user to allow anything.
5. **Review Ready.** Read the actual `.dryforge/handoff.md`, `spec.md` and `plan.md` in the target
   project, not L2's summary. Request corrections with `session-send`. When they are right, record
   `cycle-stage --stage go --ready-digest <sha256 of the three files>` and send
   `session-start --skill go --message <file>` (`/dryforge:go`) in the **same** session. Changed
   documents need a fresh look before Go.
6. **Review Go.** Check requirement coverage, that the project's verification really ran (output,
   exit code), independent review evidence and open issues. In-scope corrections go back to the
   same session. On acceptance let L2 finish Dryforge's own archive, integration and cleanup, then
   record `cycle-stage --stage review --checkpoint <commit>`. A turn ending proves nothing; Git
   state and documents do.
7. **Evaluate.** `evaluate --decision CONTINUE|REPLAN|ESCALATE --basis <file>` and update the
   node's status. `REPLAN` means the approach must change: add or rewrite nodes. `ESCALATE` on a
   development cycle means a real user decision is needed; say what it is. A finished node is not a
   finished goal; `COMPLETE` happens only in the beta test below. The record stops the run when a
   limit is reached; report it and stop.

## The beta test (when every node is done)

You are the user's stand-in: run the result the way the scenarios describe and judge it against
`validation.md`.

1. `cycle-start --kind beta --goal <file> --checkpoint <commit>`. A beta cycle runs no worker turn
   (`session-start`/`session-send` are refused while it is open) and does not count toward
   `max cycles`.
2. For each item in `validation.md`, in the workspace, run the Evidence check yourself (for a
   `slow/hard` item, the efficient check from `.dryforge/ouroboros/spec.md`). Record each result with
   `event --actor L1 --kind beta --data <file>` holding `{item, command, exit_code, observed, verdict}`.
3. An item you cannot execute (something only a human can see or hold: a visual check, a device, an
   external account) → `evaluate --decision ESCALATE --basis <file>` naming those items and the
   exact check the user must perform. This is the one thing you ask of the user after approval: a
   verification only a human can make, never a permission. It does not count as a stalled cycle.
   When the user answers, record each item with `event --actor human --kind verified --data <file>`
   (their words), open a new beta cycle and continue with the remaining items.
4. A failed item → `evaluate --decision REPLAN --basis <file>`, add the nodes that fix it, run
   those cycles, then open a new beta cycle and rerun the failed items and any item whose node
   changed.
5. When every item has a verdict (pass by you, or verified by the user), close with
   `evaluate --decision COMPLETE --basis <file>` listing every item and its verdict. The record
   accepts `COMPLETE` only on a beta cycle.

## Keep intent and execution connected

Keep listening. In-scope clarification goes into the next message or cycle. A change to the four
documents is a revision approved by the user (`interview.md`); limits, models and effort take effect
at the next check or turn, content changes shape the next cycle.
When the user asks to stop: `session-stop` (an open question is recorded as unanswered), then
`stop --reason abort`, and list what was left half-done (task branches, worktrees). Clean nothing up
on abort. A session stopped in the middle of a question can be continued later with `session-send`
on the same session (verified on Claude Code). If you take over a run another L1 left (for example
after the host was closed), `show` tells you whether a question is still open; answer it or stop.

Record your decisions as L1 with their basis. Never turn a worker claim into a user approval.
Already delegated decisions need no new consent. The host's own permission settings remain in
force for L2 exactly as for a human caller.

## Migration

When an existing project has no documentation for agents, run one Migration cycle first:
`cycle-start --kind migration`, a fresh session, `session-start --skill migration`
(`/dryforge:migration`), answer its
questions, review the produced documents and independent review, then arrange the Git checkpoint
of those documents yourself (Migration writes documentation, not product code, and does not
commit). Evaluate the cycle, then write the work graph and start Ready in another fresh session.
Prepared projects keep their documentation; a new checkout alone is no reason to migrate again.
