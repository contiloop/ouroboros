# Optional L2 runtime — persistent host sessions, not another agent tier

Load only when native L2 persistence/relay is missing or the human chooses this execution path.
`scripts/worker_runtime.py` supplies actual Claude Agent SDK and Codex App Server operations.
L1 still owns intent and chooses cycles. L2 is a full host session; L3 uses that host's tools.
Do not claim L3 support until a live probe observes it. Dependency presence is not compatibility.

## Before use

Python 3.11+ on macOS/Linux/WSL; a Git project with `.dryforge/` ignored. Claude additionally
requires the optional SDK in the selected Python environment; Codex requires an installed CLI.
Never install dependencies, log in, alter permissions or open network listeners automatically.
Use absolute paths to this skill's script and the user's selected Python executable. This is a
trusted same-user controller interface, not a sandbox against hostile agents sharing that user.

`doctor --backend claude|codex` checks dependencies only. `start --workspace <repo> --worker <id>
--backend claude|codex` launches a controller with finite turn/lifetime/message limits. Set those
limits within the human-approved budget. Claude startup includes a no-tool model bootstrap call
and may incur cost. Wait for `status` to expose a real host session_id and IDLE. A PID is not proof
of readiness. User/project Claude settings and MCP configuration require explicit `--load-settings`
choices and a new availability check in L2. Host permission gates remain authoritative.

## One cycle over one session

1. `send --kind probe --id <id> --text-file <path>` tests read-only session/relay/task-agent
   capabilities. Do not fabricate the mission ledger's capability booleans from a text response.
2. After actual capability checks, L1 records the existing ledger `start` event with the observed
   L2 session_id, approved goal and checkpoint. No cycle assignment is inferred from a spawn.
3. `send --kind ready --id <id> --ledger <state.json> --cycle <cycle-id> --text-file <goal>` gives
   L2 the full preserved procedure and reference paths. Claude executes explicitly authorized
   procedure text; Codex also receives `$ready` and a native `skill` input. Never describe file
   loading as a proven slash-command invocation. Standalone manual-only settings are unchanged.
4. `wait --id <id> --timeout 30` reads durable results or pending input. A wait timeout is not a
   failed task. L1 answers within original intent or relays to the human. Keep decision provenance
   in the mission ledger as well as the mailbox. A final prose question yields a turn; answer via
   `send --kind message` to the same worker. This is not permission to start go.
5. L1 reads the actual three docs, records `ready` and legitimate `approve` in the existing ledger.
   `send --kind go` checks identity, cycle, active mission, unresolved questions and exact approved
   document digest at enqueue and dispatch. Immediately before sending this explicitly approved
   command, the controller atomically records the ledger's **go execution-start event**. L1 must
   not pre-advance that event. A host error after start is UNCERTAIN/GO, never a fabricated result.
6. All other result/accept/close/evaluate events remain under existing L1/L2 responsibilities.
   TURN_COMPLETE means only the host ended a turn. Inspect tests, independent review, artifacts and
   side effects before accepting a cycle. L1 alone selects another cycle or mission completion.

The runtime does not choose architecture, answer questions itself or replace the mission loop.
Every cycle input is bound to the current intent digest. Ordinary messages continue the existing
phase; interpreting a payload correctly remains the agent's responsibility, not a security proof.

## Answering a pending host request

`status.pending` includes request id, actual content, session_id and fingerprint. `answer
--request-id <id> --response-file <json>` takes session_id, request_digest, principal (human/L1),
basis and action. These are records from a trusted controller, not self-authenticating claims.

Claude AskUserQuestion uses `action: answer` plus `answers` keyed by original question text.
L1 may answer only when the matching active cycle delegates answer; it must still check that the
content follows the human's intent. Tool callbacks use allow/deny for that exact invocation,
never new rules or allow-for-session. Generic Ready approval is not a tool permission. An explicit
human-approved runtime policy may delegate a bounded allow to L1; force-load
`references/runtime-permissions.md` for this path. `status.pending[].delegation` reports eligibility
and policy digest, not approval. L1 must inspect the exact request, record its own basis and answer
as `principal: L1`; do not ask the human again for a matching delegated action. Unknown/out-of-scope
requests still require the human. Host rules may resolve tools earlier; no host rule is widened.

Codex structured requestUserInput can include app side-effect approvals: conservatively require a
human response (`action: allow`, `answers` keyed by actual question IDs). Yielded product questions
can use ledger-bound message turns instead. Permission expansion and MCP elicitation are declined;
unsupported RPC methods fail closed. Do not turn child-produced JSON into authority-bearing input.

## Delivery, shutdown and recovery

Messages are QUEUED, DISPATCHED, TURN_COMPLETE, TURN_FAILED, REJECTED, CANCELLED or UNCERTAIN.
Exact message-ID retries return their existing receipt; different content under that ID fails.
Only one OS-locked controller may write turns in a workspace; kernel locks release on crash.
This is a serialized local transport, not a distributed exactly-once executor.

Lost connection/timeouts never cause automatic replay. Inspect recorded host thread, partial file
or external effects and live children first. Then `resume --reconciled --basis <evidence>` resumes
the **recorded host ID**, expires stale callbacks and cancels unsent inputs for explicit reissue.
A changed host ID fails. Resume never falls back to a new session or replenishes stored limits.
New workers after prior ones require `--handoff-ref` and actual child/workspace reconciliation.
Context headroom and child quiescence remain unknown until independently observed.

`stop` requests shutdown; wait for STOPPED/ERROR and inspect children separately. `result --id`
returns a compact reply; `--full` exposes the original. `events --after <cursor> --limit 50` lists
observable events; add `--full` to inspect protected payloads. Large events use artifact pointers.
Logs may contain private code/input, must remain ignored and must not flood L1's context. Hooks
observe actual host activity but never approve or complete a cycle. No global hooks are installed.

The bridge enforces finite time/message bounds. Claude's model-turn/USD settings are SDK query
limits, not a mission-wide cost guarantee. Codex does not enforce a USD budget here. Unsupported
required limits are a blocker; unknown telemetry is not unlimited credit. Real host/model behavior
still needs live acceptance; protocol fixtures are not real agents.
