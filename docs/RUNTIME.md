# Persistent worker connection

The optional runtime bridge connects L1 to an actual persistent L2 host session. It reuses the
Claude Agent SDK or Codex App Server, records messages in a local SQLite mailbox, and relays input
requests. L2 still runs one ready-go cycle and its own L3 tasks; L1 still owns intent and evaluation.
Native host tools remain usable when already verified. This bridge is not a new agent framework.

**Verification boundary:** protocol and subprocess tests use deterministic fixtures. They exercise
real Python controller processes and SQLite, not authenticated Claude/Codex models. Installing the
bridge does not prove model compliance, L3 availability, skill behavior or full mission success.

## Requirements and setup

Python 3.11+ on macOS/Linux/WSL; a Git project with `.dryforge/` ignored. Authentication belongs to
your installed host. Nothing auto-installs dependencies, logs in, changes global hooks or broadens
host permissions. Use a disposable project for the first live test.

Claude needs the optional SDK. Install it explicitly in a Python environment you choose:

```sh
python3 -m venv ~/.venvs/ouroboros-runtime
~/.venvs/ouroboros-runtime/bin/python -m pip install \
  -r ~/ouroboros/claude/skills/init/scripts/runtime-requirements.txt
```

Codex uses the Python standard library and an already installed/configured `codex` command.
The SDK pin is the inspected release, not a promise every host configuration has been tested.

```sh
PY="$HOME/.venvs/ouroboros-runtime/bin/python"  # python3 is enough for Codex
BRIDGE="$HOME/ouroboros/claude/skills/init/scripts/worker_runtime.py"
PROJECT="/absolute/path/to/your/test-project"

"$PY" "$BRIDGE" doctor --backend claude
"$PY" "$BRIDGE" start --workspace "$PROJECT" --worker l2-01 --backend claude \
  --turn-seconds 600 --lifetime-seconds 3600 --max-messages 20
"$PY" "$BRIDGE" status --workspace "$PROJECT" --worker l2-01
```

Change to `--backend codex` for Codex. Paths/limits are examples, not budget authorization. Claude
startup makes a no-tool bootstrap model call to obtain/confirm its session ID and may incur cost.
A successful process launch is not a connected session: wait for a real session_id and IDLE.
`doctor` checks dependencies, not login or live execution.

Claude settings/MCP configuration are opt-in (`--load-settings user`, `--load-settings project`,
`--load-settings local`); choose only trusted sources. The runtime does not strip nested-session
protections from environment variables. When a host prevents launching inside another session,
start the controller in a normal terminal or report the restriction; do not bypass safeguards.
Keep the Python environment and plugin checkout available while the controller runs.

## L1 integration

The init/approve workflow loads [runtime-bridge.md](../src/skills/init/references/runtime-bridge.md) only
when this execution path is selected. Give L1 the Python executable, bridge path and workspace.
L1 uses its ordinary shell tool for start/status/send/wait/answer, under existing host permissions.
No listener or extra model supervisor is required.

For existing-project cycles, policy v4 separates the final integration branch from the cycle
feature branch and L3 task branches/worktrees. The human grants operation/path/branch scope once;
L1 narrows it to exact cycle targets with `bind_runtime` after Ready review. Result corrections
return the same L2 to GO through `rework`; accepted cleanup/integration preserves the approved
document identity in the pinned archive. See the [v4 policy and event contract](../src/skills/init/references/runtime-permissions.md#cycle-workflow-policy-v4).
Older grants do not acquire these rights automatically. Protected metadata and unsupported
commands still use ordinary host controls; a v4 grant is not proof of unattended E2E execution.

A small read-only capability probe can test the connection before cycle assignment:

```sh
"$PY" "$BRIDGE" send --workspace "$PROJECT" --worker l2-01 \
  --id probe-1 --kind probe --text-file /absolute/path/probe.txt
"$PY" "$BRIDGE" wait --workspace "$PROJECT" --worker l2-01 --id probe-1 --timeout 30
```

A reply proves a responding session, not nested-agent support. Inspect real host tool events before
recording capabilities in the mission ledger. Probe is not an alternate route to unapproved work.
A missing L3 capability is a blocker, not permission to simulate roles in a single agent.

### Ready and Go in the same session

First establish the normal human-approved Intent Contract. After capability checks, L1 records the
existing ledger `start` with the actual L2 session_id, cycle ID and checkpoint. Then:

```sh
LEDGER="$PROJECT/.dryforge/mission/state.json"
"$PY" "$BRIDGE" send --workspace "$PROJECT" --worker l2-01 --id c1-ready \
  --kind ready --ledger "$LEDGER" --cycle c1 --text-file /absolute/path/cycle-goal.txt
"$PY" "$BRIDGE" wait --workspace "$PROJECT" --worker l2-01 --id c1-ready --timeout 30

# L1 checks the actual documents and records ready/approve with legitimate authority.
# The controller requires that approval before this explicit go command:
"$PY" "$BRIDGE" send --workspace "$PROJECT" --worker l2-01 --id c1-go \
  --kind go --ledger "$LEDGER" --cycle c1 --text-file /absolute/path/go-instruction.txt
```

The bridge validates the active cycle, same session, unchanged intent, unresolved questions and
exact approved three-document digest at enqueue and dispatch. Immediately before dispatching the
explicitly approved Go command, it records the ledger's `go` execution-start event transactionally.
Do not pre-record `go` yourself. It never records approval, acceptance or completion from transport
notifications. A failure after that write leaves an in-flight GO to reconcile, not something to
replay blindly. Mailbox/ledger/filesystem effects are not one distributed atomic transaction.

Full preserved procedures are passed with reference paths. Claude uses explicitly authorized
procedure loading (not a claimed slash invocation); Codex additionally receives `$ready`/`$go` and
the official skill input item. Normal manual-only settings are unchanged. A yielded prose question
ends a turn, not the session; `send --kind message` continues that phase after a legitimate answer.
A message is not authority to skip the ready approval gate or start another cycle.

### Pending questions and tool permissions

`status.pending` contains id, body, session_id and fingerprint. A trusted controller/operator writes
a private response file and calls `answer --request-id ... --response-file ...`. Example shape:

```json
{
  "principal": "human",
  "basis": "reference to the actual human decision",
  "session_id": "copy the actual pending session ID",
  "request_digest": "copy its fingerprint",
  "action": "allow"
}
```

This example is not approval. Claude questions use `action: answer` plus `answers` keyed by original
question text. L1 may answer only with explicit delegation and must preserve the decision in the
mission ledger. Tool permission allow is exact-call only. It defaults to human review; with a
separately human-approved runtime policy, L1 may approve matching local operations. See
[delegated runtime approvals](../src/skills/init/references/runtime-permissions.md) for the
policy shape, grant/revoke events, eligibility hints and audit fields. Codex requestUserInput uses
`action: answer` and an `answers` map keyed by actual question IDs. The same contract-bound L1
question authority applies as for Claude; human-only or out-of-intent decisions still go to the human. Permission expansion/MCP elicitation are declined, not silently supported.

The same-user mailbox is not an adversarial security boundary. `principal: human` is a trusted
record, not authentication. Never expose these commands as an untrusted remote service or accept
child-supplied JSON as consent. Host permissions remain authoritative; approved host settings may
resolve tools before a callback, and the bridge does not widen them.

## Inspect, recover, stop

```sh
"$PY" "$BRIDGE" events --workspace "$PROJECT" --worker l2-01 --after 0 --limit 50
"$PY" "$BRIDGE" result --workspace "$PROJECT" --worker l2-01 --id c1-go
"$PY" "$BRIDGE" stop --workspace "$PROJECT" --worker l2-01
"$PY" "$BRIDGE" status --workspace "$PROJECT" --worker l2-01

# Only after inspecting the host transcript, files, side effects and active children:
"$PY" "$BRIDGE" resume --workspace "$PROJECT" --worker l2-01 \
  --reconciled --basis "reference to reconciliation evidence"
```

| Receipt | Meaning, not a mission verdict |
| --- | --- |
| QUEUED | Input stored, not dispatched. |
| DISPATCHED | Controller claimed it; host execution may be in flight. |
| TURN_COMPLETE | Host ended a turn successfully; cycle verification still required. |
| TURN_FAILED | Host reported a failure/interruption. |
| REJECTED | Input failed the current ledger/procedure gate before sending. |
| UNCERTAIN | Connection/process/timeout prevented a trustworthy outcome. |
| CANCELLED | Unsent input cancelled for explicit reissue after shutdown/recovery. |

Exact message-ID retries return the existing receipt; changed content is rejected. Uncertain work
is never auto-replayed. Resume pins the recorded ID, expires old callbacks and cancels unsent
inputs; it does not create a new conversation on failure. Stored deadlines/counters do not reset.
The OS lock permits one bridge controller per workspace and is released by the kernel after crash.
Replacing a worker requires a handoff reference; process exit alone does not prove L3 quiescence.
Context headroom remains unknown until separately observed. No token counts are fabricated.

Default bounds: 600 seconds per turn, 3600 seconds lifetime, 20 dispatched inputs. Set appropriate
limits with the human. Claude `--budget-usd` and `--max-model-turns` are SDK query limits, not a
whole-mission cost guarantee. Codex rejects USD limits it cannot enforce. Unsupported required
limits are a blocker; absent telemetry does not authorize unlimited spending.

Runtime data is private and ignored beneath `.dryforge/mission/runtime/`. It may contain code and
user input. Result/wait omit input echoes and bound reply text; `--full` gives the original record.
Events show kinds/cursors by default; use `--full` for protected payloads. Large events point to
private artifacts. Raw thinking/signature blocks are omitted. Never evaluate solely from clipped
summaries or publish logs without checking them. No global hook installation is performed.

## Verification and sources

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s ci -p 'test_runtime*.py' -v
```

Tests cover real SQLite/CLI processes, a fake App Server subprocess and SDK-shaped doubles:
session continuity, permission/question correlation, stale approvals, idempotency, missing notices,
resume, disconnection and timeout. They are **not live authenticated model runs** or independent
LLM review. Verify same-ID ready/go, actual L3 calls, a genuine permission denial, real evidence
and safe handoff in the intended host before claiming end-to-end support.

This is original code using official interfaces, not vendored third-party bridge code:

- [Claude SDK sessions](https://platform.claude.com/docs/en/agent-sdk/sessions)
- [Claude input callbacks](https://platform.claude.com/docs/en/agent-sdk/user-input)
- [Claude Python SDK](https://github.com/anthropics/claude-agent-sdk-python)
- [Codex App Server](https://developers.openai.com/codex/app-server)
- [claude-bridge](https://github.com/michalekz/claude-bridge): stable addressing and durable messages
- [codex-bridge](https://github.com/shadohead/codex-bridge): state-driven waits and explicit thread reuse
- [Agent Bridge](https://github.com/creatornader/agent-bridge): delivery acknowledgment is not task completion

## Updating an existing test session

Installing the updated plugin does not grant execution authority to an old mission. Ask the human
once for the actual scope, then record a `runtime_policy` event; do not rewrite the mission goal or
fabricate approval. A live controller continues using the code it imported at startup. Stop it,
reconcile the host/files/children, and explicitly resume the SAME host session on the updated
code. Old callbacks expire; never replay an uncertain command without checking its effects.
An unchanged local checkout path must not be deleted while the controller is active. Installing
in a new plugin-cache version requires using the corresponding new script, not the old cached CLI.

### Delegating verified Go worktree operations (v1.3.10)

When Go's task implementer is checked out in `.dryforge/worktrees/T1`, Codex reports that
worktree as the command's `cwd`, while Git stores its index in the parent repository's
`.git/worktrees/<name>/index` rather than `.git/index`. Delegated `git add`, `git commit -m`,
file edits and exact approved test commands now recognize this case **only** for registered task
worktrees tied to the mission repository. The exact workspace, operation and worktree ID are
recorded at both authorization and consumption; a changed commit index is rejected.

The earlier v1 policy was deliberately base-only. It does not silently gain worktree authority
when v1.3.10 is installed. A human must explicitly authorize a **version 2** policy with
`"go_worktrees": true` and the same bounded operations and paths, using a new `runtime_policy`
event. See [scoped policy example](../src/skills/init/references/runtime-permissions.md).
L1 may then approve exact Go worktree operations independently within that grant. An existing
denied request is NOT automatically retried: reconcile the worktree first and have Codex issue a
new request in the same L2 session. In-flight callbacks expire across controller replacement.

A v2 grant does NOT authorize `git merge`. Version 3 can separately grant exact, pinned
`git merge --no-ff <40-hex-SHA> -m <message>` operations from the clean approved base,
after validating the registered task worktree, branch identity and complete allowed diff.
This is a new HUMAN `runtime_policy` grant, never inferred from prior v1/v2 approval.
Under the `integration_branch` policy shape, worktree add/remove and other integration
commands remain human-reviewed. The separate `go_workflow` shape is described below. See [integration scope](../src/skills/init/references/runtime-permissions.md).
Likewise, worktree support is not an end-to-end live Mission acceptance claim.


### Ordinary caller interface and live children (v1.3.11)

Ready/Go receive ordinary user goals, questions, approvals and results. Provider identity, private
Mission state and cycle correlations stay in the outer controller. Audit records still identify
L1 decisions accurately. No Mission-specific worker mode or impersonated human record is needed.
Codex parent model-turn completion now leaves its message dispatched while observed children or
callbacks are active. Child approvals retain their original binding; the transport waits within
existing limits rather than requesting extra model turns. This behavior needs live host validation
in addition to deterministic protocol tests; Claude child lifecycle is not certified here.

Policy v3 can explicitly delegate local Go worktree creation, scoped task integration and safe
cleanup. See the [exact commands and state guards](../src/skills/init/references/runtime-permissions.md).
Existing v1/v2 grants remain unchanged. Cleanup refuses ignored evidence as well as ordinary
untracked files; force removal is never delegated. Python `-B -m unittest` is recognized only when
that exact argv appears in the human-approved policy.

## L1-managed Migration (v1.4.1)

The runtime accepts `send --kind migration` for an explicitly assigned Migration preparation
cycle. It loads the existing skill, relays questions and requires evidence-backed result review.
The ledger verifies the actual documentation digest at result recording, acceptance and closure.
Read [Migration orchestration](../src/skills/init/references/migration-orchestration.md) for
setup, events, policy boundaries, checkpointing and the mandatory fresh Ready session.
Existing contracts do not gain preparation authority on upgrade; active Migration grants use
schema 4. Local Git/SQLite/CLI regressions verify these boundaries; a complete authenticated
Migration → Ready → Go model run has not been certified.
