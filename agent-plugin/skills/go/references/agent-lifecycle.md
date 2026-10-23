# Task-agent lifecycle — SPAWN, RESUME, FRESH_REVIEW

Force-load before the first dispatch and before resuming any child. This policy applies to go
both standalone and as a mission's L2. It does **not** alter the Execution Graph or dispatch
criteria: direct low-risk sequential work, risky-task isolation, parallel worktrees, the external-
state path and all verification gates stay intact. Independent review remains independent.

## Identity and ownership

Record each child's actual host session ID, role, task ID, parent cycle/session, approved task
contract digest, pinned worktree/branch and last verified commit. Track active/paused/done/closed
and known context capacity. A worktree pool is **not** a session pool. Recycling a worktree does
not transfer its previous agent's conversation or let that agent resume in a different task.
Never start two writers for the same task/worktree. Wait for acknowledgement that the old writer
has stopped before resuming or handing off. A returned summary is not necessarily a terminated
session; keep its ID only when useful and supported.

## RESUME

Prefer the same implementer for clarification, a bounded retry, or review-requested fixes to
**the same task**, provided the host confirms resume support and adequate context, the task
contract is unchanged, and the worktree/branch/current HEAD match the checkpoint. Re-pin the
absolute path, accepted spec slice and shared-write constraints on every resume. Return only the
new delta plus updated evidence; rerun affected checks. Resuming does not waive merge-gates,
review or the completion gate. Keep the existing bounded retry ladder; do not restart its count
by switching models or session IDs. A negative feasibility result is not a retryable failure.

## SPAWN with explicit handoff

For an independent new task, unavailable resume, insufficient/unknown headroom, contract change,
or changed/recycled workspace, start a fresh agent **after** quiescing the old one. Pass relevant
spec text, constraints, current code/commit, verification evidence, decisions and remaining work.
The new agent must inspect those artifacts. It does not inherit hidden reasoning or the entire
old conversation automatically. Do not call this resumption. Large logs stay in files with
pointers and a digest. Check for partial side effects before retrying an external operation.

## FRESH_REVIEW

A new independent review starts in a fresh context that did **not author** the reviewed changes.
Never turn an implementer's resumed/forked conversation into its own spec/final reviewer. Provide
the approved contract, diff/commit and evidence, not an instruction to endorse the implementer's
story. A reviewer may re-check its own prior findings in the same read-only session if it never
became an implementer; otherwise use fresh review. Ready's intent-completeness/3-doc audits retain
their original raw-dialogue versus artifact-only separation.

## Report and cleanup

Keep existing implementer statuses: DONE, DONE_WITH_CONCERNS, NEEDS_CONTEXT, BLOCKED. Add session
identity, task/contract digest, workspace checkpoint and pending-side-effect information when
lifecycle management is active. Report missing runtime capability honestly. Do not create a fake
session ID, claim a resume or independent review that did not happen, or bypass a permission gate.

Before a cycle handoff/cleanup, collect all children, resolve or preserve failed work, stop writers
and record checkpoint references. Remove/recycle a worktree only under the original go ancestry
and safety rules. Do not keep leaf agents alive merely because L2 will be reused for a new cycle.
No migration is needed for agent replacement; the handoff reads existing code and project harness.
