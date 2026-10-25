# L1 execution

You own the user's goal across cycles. Act as the caller of ordinary Dryforge skills: choose work,
answer questions, review outcomes and continue until the goal is met. L2 is the Dryforge main
agent assigned **one ready-go cycle**; it may implement or delegate to L3. L2 controls L3.
Paths below resolve from the init skill root. Read conditional references only when needed.

## Run the loop

1. **Choose work.** Read the approved intent, original decisions, accepted checkpoint and remaining
   limits. Select a bounded outcome advancing a success criterion, one cycle per working repository.
   Use the accepted branch/commit; an unmerged feature is unavailable in a checkout of main.
   An existing project needing initial harness preparation uses Migration below within delegated scope. New or already prepared projects go directly to Ready.
2. **Prepare L2.** Verify persistent session identity, question/approval relay, installed skills,
   L3 tools, workspace access and enforceable limits. Use native sessions when supported; otherwise
   consult `references/runtime-bridge.md` for `scripts/worker_runtime.py`. If neither works, report
   the missing capability; never auto-install clients or weaken permissions. Record the real ID.
   REUSE only after a completed, evaluated cycle with children quiescent and verified context
   headroom; otherwise SPAWN with the accepted checkpoint. Keep the same L2 session throughout
   Ready, Go, corrections, result acceptance and cleanup.
3. **Request Ready.** Send the cycle goal, relevant original requirements/decisions, project path
   and checkpoint/harness pointers. Explicitly invoke the installed skill as below. Give L2 ordinary
   caller messages; keep L1 identity, private state and approval bookkeeping outside its prompt.
4. **Decide and approve.** Answer within delegated judgment using user intent and evidence. Research
   technical unknowns; ask the human only for a consequential decision outside that scope. Read
   the actual spec, plan and handoff plus independent review evidence. Request corrections or
   approve their exact combined digest. Changed documents require renewed review. Invoke Go in
   the same L2 session. For runtime policy v4, bind cycle targets before Go using
   `references/runtime-bridge.md#execution-scope`; distinguish integration, cycle and task branches.
5. **Review results.** Check requirement coverage, actual tests, independent review and unresolved
   issues. Request in-scope corrections through `rework` and an ordinary message to the same L2.
   Acceptance preserves Dryforge's gates. After acceptance, let that L2 finish authorized archive,
   integration and cleanup; receive the final commit/branch, archive, checks and child status.
   Keep raw logs in files. A turn ending or Transport receipts never prove cycle completion.
6. **Continue.** Record and evaluate the checkpoint: CONTINUE or REPLAN when more work is needed,
   ESCALATE for a real human boundary, COMPLETE only with evidence for all success criteria.
   Routine progress updates need no human reply. Enforce the approved cycle/stall/time/cost limits;
   report unknown telemetry. L1 chooses the next cycle.

## Invoke installed Dryforge skills

| Host | Ready / Go / Migration |
| --- | --- |
| Codex | Resolve `dryforge:<kind>` with workspace `skills/list`; send `$dryforge:<kind>` plus the native `skill` input with its returned name/path and the caller's prompt. |
| Claude Code | Invoke `/dryforge:<kind> <caller prompt>`; verify the command is available in that session. |

The host loads the skill. Missing skills are a capability gap; do not paste procedure files or
substitute bundled Ouroboros copies. Session creation does not create a Git worktree. Dryforge
owns task worktree execution; L1 selects permitted targets when the runtime policy requires it.

## Keep intent and execution connected

Continue listening to the user. Apply in-scope clarification without another handoff; review the
impact of changed goals/authority before dependent work proceeds. Stop affected work when needed
and preserve unrelated progress. At an evaluated cycle boundary, record a reviewed goal change directly with `amend` and
the actual human approval. No separate skill request or result protocol is needed.

Use the relevant section of `references/runtime-bridge.md` for state records and tool decisions. Record L1 decisions as L1;
never turn a worker claim into human approval. Already delegated requests need no new consent.
Host controls and explicit human-only boundaries still apply.

On interruption, reconcile effects and live children, then resume the recorded L2. Replacing it
with a summary is a handoff, requiring an explicit abort/replacement decision during an active
cycle. Do not replay uncertain writes. Context compaction may require rereading approved artifacts;
a session ID alone does not guarantee memory. A fresh checkout needs accepted Git content and
explicit transfer of trusted ignored `.dryforge/` state; a new session does not justify Migration.

## Migration

When an existing project needs initial harness documentation and preparation is delegated, assign
installed `dryforge:migration` to a fresh worker. Answer its questions and review the actual docs,
checks and independent review. Accept the reviewed result, then arrange its authorized Git
checkpoint separately: Migration itself writes docs, not product code or commits. Reconcile that
worker and start Ready in a fresh session with the accepted checkpoint. Prepared projects retain
their harness; a missing ignored marker in another checkout alone does not justify Migration.
