# Persistent cycle session and decision relay

This is the outer Mission/controller contract; do not inject it into the Ready/Go worker.
The worker uses one caller interface without learning the decision provider identity. Standalone ready/go continues
to ask the actual user. A requester merely calling itself an orchestrator does not enable delegation.

## Session invariants

L1 owns the mission; L2 owns **one assigned cycle at a time**. L2 does not choose its next cycle.
The same recorded host session runs ready, asks questions, receives approval, runs go, receives
result acceptance, archives the 3-doc and returns the checkpoint. Preserve that session across
turns; suspend/resume is acceptable, silently replacing it with a new summarized session is not.
The project filesystem, conversation transcript and session ID are distinct assets; preserve all
three as required. Context compaction can lose details even when the ID stays the same: reread
the approved documents and durable decision references before continuing. Never promise lossless
memory from the presence of an ID alone.

L1 may REUSE L2 for another cycle only after L2 reports completion, L1 evaluates the mission,
children are quiescent, and host-reported context capacity is sufficient. Otherwise SPAWN with
an explicit handoff. Unknown remaining capacity selects a fresh worker at the safe boundary.
During an active cycle, capacity exhaustion pauses for checkpoint/recovery rather than changing
worker identity. An unrecoverable session needs explicit abort/replacement approval.

## Relay protocol (logical messages, not vendor API names)

Every outer transport envelope carries mission_id, cycle_id, worker_session_id and request_id/event_id.
The controller attaches these fields; they are not worker instructions. Never answer
a request from a different or obsolete session. Decision requests carry the exact question and
choices and relevant evidence through the ordinary interface. L1 records decision scope and
provenance outside that interface. The worker waits for the answer and preserves every ordinary gate.

L1 answers from approved human intent or relays to the human. Send the response to the **same**
worker session. An answer is not a blanket go approval. READY_REVIEW sends the three document
paths and their combined SHA-256 digest; approval is bound to that digest and cycle. Any rewrite
invalidates it. The host's ordinary permission prompts are separate from product/spec approval.
Never answer a tool permission prompt using a generic ready approval. A separate human-approved
runtime policy can authorize L1 to answer that exact tool request; see `runtime-permissions.md`.
Keep L1 provenance, policy digest, request identity and pre-consumption checks.

If AskUserQuestion is unavailable inside L2, route an equivalent structured request through a
verified parent-message or external session controller. Do not repeatedly call an unavailable
tool. Raw dialogue plus decision provenance must remain accessible to the intent-completeness
reviewer. Preserve the original two independent ready audits.

## Completion and checkpoint packet

Go's checks and independent final review must actually run. Report unresolved failures honestly;
missing independent execution is a blocker for claiming normal completion. L1 acceptance does
not replace the reviewer or test evidence. After acceptance, archive as ordinary go requires and
resolve integration under explicit authority. Return:

- outcome and requirements satisfied (the controller attaches mission/cycle/session identity);
- exact repository, branch and commit, clean/dirty status and unmerged work;
- captured check commands, exits, observable effects and log references;
- review findings and their disposition; pending blockers and unknowns;
- active 3-doc or `.dryforge/NNN/` archive, harness changes and checkpoint manifest;
- L3 session IDs and quiescent status; actual resume/context availability (or unknown).

No raw diff/log dump into L1. Keep detailed evidence in files. Stop previous writers before a
handoff; do not reuse their worktree for a new writer while they can still resume. A new checkout
must point at the accepted result, not automatically main. Ignored `.dryforge/` state does not
travel with Git; transfer it explicitly under the same trust/authority boundary. Never run
migration just because L2 is new.

## Ledger event flow

Existing-project preparation can use an explicitly delegated Migration assignment:
`start(kind=migration) → result → accept → close → evaluate`. Load
`migration-orchestration.md` for the exact event fields, documentation digest and checkpoint.
It has no Ready/Go or three-document archive. Questions and interruption recovery retain the
same Migration worker; subsequent Ready must use a fresh session. Preparation counts against
the existing cycle budget and cannot silently broaden runtime authority.

`start → ready → approve → go → result → accept → close → evaluate`

With runtime policy v4, insert L1's `bind_runtime` between `approve` and `go`: it narrows the
human grant to an integration tip, cycle branch, exact task branches/worktrees and archive.
It never changes the granted operations or paths. For a rejected development result,
`result → rework → result` returns the same L2 to GO under the unchanged approved documents;
record feedback and retain earlier results. `rework` uses delegated `accept_result` authority.
After acceptance, archive/integration questions can still be answered before `close`.

`question → answer` can pause ready or go. `interrupt → resume` restores the same session after
reconciliation; `abort` is a human-authorized exceptional exit. `observe` records notifications
but cannot approve, advance a gate, or complete a cycle. IDs are idempotency keys; identical
retries are harmless, conflicting reuse is rejected. Persist state before sending side-effecting
messages and reconcile delivery after a crash; this is **not** exactly-once external execution.

The helper uses atomic file replacement, a writer lock and expected revision checks. It is a
local trusted ledger, not a daemon, message broker, permission sandbox or SDK adapter. Hook
handlers and the host still supply actual sessions, message delivery and evidence verification.

## Optional runtime transport

The bundled `scripts/worker_runtime.py` implements the full-host session and mailbox path described
in `runtime-bridge.md`. It does not fabricate approval events. Only an explicit, already-approved
Go dispatch records execution start; host turn completion never records acceptance or success.
