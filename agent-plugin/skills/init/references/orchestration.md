# L1 execution

You own the user's goal across cycles. You act as the ordinary caller of the installed Dryforge
skills: choose work, create and keep one worker session (**L2**), answer its questions, review its
documents and results, and continue until every completion criterion has evidence. L2 is a
headless Claude Code session in the target project; it runs Dryforge Ready and Go in the same
session and manages its own task agents (**L3**). You never manage L3 directly. All record and
session commands are in `runtime.md`; every command takes `--workspace <git root>` and
`--owner <pid>` where the pid is this host process (`$CLAUDE_PID` on Claude Code).

## Preconditions (once per run)

Run `doctor --host claude`. If `claude` is missing or the `dryforge` plugin is not installed and
enabled, report the missing capability to the user and stop; the run stays `ACTIVE`, nothing is
started. Never paste Dryforge procedure text or substitute another procedure.

## The loop

1. **Choose work.** From the approved proposal, prior checkpoints and the remaining criteria,
   select one bounded outcome in the one workspace that advances at least one criterion. Record it
   with `cycle-start --kind development --goal <file> --checkpoint <commit>` (`--kind migration`
   for a Migration cycle). If a previous cycle is still open (for example after an abort that was
   later resumed), close it first with `evaluate`.
2. **Session.** Use the recorded session by default; design context carries across cycles. Start
   a fresh session (`--fresh --reason <why>`) only when there is none, after a `REPLAN`, when the
   recorded session cannot be resumed, when the last results show the context near its limit, or
   for Migration (which always gets a fresh session, and the Ready after it another fresh one).
3. **Ready.** `session-start --skill ready --message <file>` sends `/dryforge:ready` followed by
   your message, so the host loads the installed skill. The message is ordinary caller text:
   the cycle goal, the relevant requirements and decisions from the proposal, the project path and
   checkpoint. Nothing about Ouroboros, L1, the record or approvals goes into it.
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
     user to allow anything;
   - `run_status: STOPPED` → the turn's cost took the run over its budget; report it and stop.
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
7. **Evaluate.** `evaluate --decision CONTINUE|REPLAN|ESCALATE|COMPLETE --basis <file>`. `COMPLETE`
   needs evidence for every completion criterion in the basis. `ESCALATE` means a real user
   decision is needed; say what it is. A finished cycle is not a finished goal. The record stops the
   run when a limit is reached; report it and stop.

## Keep intent and execution connected

Keep listening. In-scope clarification goes into the next message or cycle. A changed goal is a
proposal revision approved by the user (`interview.md`); it applies at the next cycle boundary.
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
commit). Evaluate the cycle, then start Ready in another fresh session. Prepared projects keep
their documentation; a new checkout alone is no reason to migrate again.
