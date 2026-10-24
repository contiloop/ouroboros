# Ouroboros init and approve: conversation, handoff, persistent cycles

`ouroboros:init` starts the conversation with L1. Refine the goal, completion criteria and delegated
scope together. `ouroboros:approve` hands that reviewed proposal to L1, which then manages ordinary
Ready/Go cycles. The conversation stays open while work runs. Interview procedures can evolve
independently of the lower tiers' ordinary caller interface.

The package includes a local state ledger and optional [runtime bridge](RUNTIME.md). It does not
install global hooks or authenticate approval records. Actual host support for persistent nested
sessions must be checked. A complete fresh init-to-outcome live-model acceptance run is not yet
certified; local state/transport tests are separate evidence.

## Architecture

```text
Human <-> L1 (init: discuss / approve: take responsibility)
             |
             | one cycle goal + delegated decisions
             v
          L2 Ouroboros main agent (persistent session)
             ready -> questions/approval -> go -> acceptance -> checkpoint
                                           |
                                           +-- L3 implementer(s)
                                           +-- L3 independent reviewer
             |
             +-- evidence -> L1 evaluates -> REUSE same L2 or SPAWN new L2
```

L1 owns the next cycle and final intent. L2 owns **one cycle at a time**, not a self-directed
sector loop. L2 must not be replaced between ready and go. A yielded turn can resume the same
session. At a completed and evaluated boundary, use the same L2 only when resume is verified and
context headroom is sufficient; otherwise use a fresh worker with an explicit checkpoint.

Go's existing execution policy stays: simple sequential tasks may run inline; risky/parallel tasks
use implementer agents; final review is independent. L3 may resume same-task fixes when contract,
workspace and capacity still match. New tasks or unknown capacity use a fresh agent. Independent
review must never reuse/fork the implementer's context. No agent replacement requires migration.

## Try it

Use this fork's generated plugin package. In Claude Code:

1. `/ouroboros:init` — open the conversation, refine intent and review the proposed delegation.
2. `/ouroboros:approve` — approve the current reviewed proposal and hand cycle management to L1.

In Codex explicitly select `$init`, then `$approve`, from this plugin once available. The old
`mission` skill is no longer shipped. Ordinary `$ready`/`$go` remain available for a manually
supervised single cycle. Internal `.dryforge/mission/` records are retained; do not reset old runs.

Example: “Build a local memo CLI; help me work out what it should do.” Discuss the requirements
with L1, inspect the proposal, then invoke approve. L1 performs Ready reviews, Go dispatch,
result checks and cycle selection within that scope without asking for each step again. Actual
human-only decisions still return to the human. Additional conversation remains possible at
all times. Formal goal changes currently commit at evaluated cycle boundaries.

Read-only project inspection can inform the discussion. Cycle workers do not start in DRAFT.
After activation, missing host capability is a concrete blocker, not silent single-agent
fallback. Grep/Context7 remain optional; see [MCP setup](RESEARCH_MCP_SETUP.md).

## What the runtime must supply

A host adapter must create actual sessions, retain IDs, route questions/answers to the correct
worker, explicitly load ready/go, enforce budgets/permissions, quiesce children, inspect evidence
and reconcile filesystem state. Native tools can provide this in a capable agent host. The optional [runtime bridge](RUNTIME.md) supplies Claude SDK and Codex App Server operations.
Use its actual CLI commands; a JSON ledger event alone neither spawns nor resumes a model. The runtime preflight and official sources are in
[host-adapter.md](../src/skills/init/references/host-adapter.md).

Hooks can supply observations. A stopped process/agent does not mean a successful cycle, and an
approval of a spec does not authorize every tool call. No auto-go-on-stop hook is installed.
Do not submit approval events from untrusted hook output or from a child task's claimed authority.

## Durable ledger (Python 3, standard library)

The script is included in every platform's `skills/init/scripts/` directory. From a repository
checkout (replace paths with your actual approved files):

```sh
python3 src/skills/init/scripts/mission_state.py draft \
  --state /project/.dryforge/mission/state.json --contract /project/draft-contract.json
python3 src/skills/init/scripts/mission_state.py digest --docs-dir /project/.dryforge
python3 src/skills/init/scripts/mission_state.py apply \
  --state /project/.dryforge/mission/state.json --event /project/next-event.json
python3 src/skills/init/scripts/mission_state.py show --state /project/.dryforge/mission/state.json
```

Do not run the example with invented approvals. The contract shape is documented in
[intent-contract.md](../src/skills/init/references/intent-contract.md).
Events carry `mission_id`, `id`, `op`, `actor`, `expected_revision`, and (during a cycle) `cycle_id`.
L2 events additionally carry the recorded `session_id`. Operation fields follow the implementation
and its behavioral fixtures in [test_mission_state.py](../ci/test_mission_state.py).

The outer handoff is `DRAFT -> revise_draft (repeat) -> activate -> ACTIVE`.
`show` reports the proposal digest; activation binds both intent and proposed execution scope to
the actual human invocation. After activation, each inner cycle follows
`start -> ready -> approve -> go -> result -> accept -> close -> evaluate`.
The inner `approve` is L1 reviewing exact Ready documents, not another user handoff.
`question/answer` does not grant go approval; `interrupt/resume` requires the same worker ID.
`abort` requires a human and stopped children. `continue` resumes an evaluated, escalated mission
only after a human decision; it cannot enlarge the cycle budget. A new budget needs an explicitly
approved replacement contract/mission, never a silent ledger reset. `observe` cannot advance gates.
Identical event retries are idempotent; changed payloads with the same ID and stale revisions fail.
The writer lock and atomic snapshot prevent conflicting local writes; they do not provide an
exactly-once guarantee for external commands. A stale lock needs manual owner/crash reconciliation.

The ledger validates supplied records, **not** the truth of tests or the origin of approval. Keep
its write interface under the trusted controller. Preserve ordinary sandbox/tool permissions.
Do not store credentials or raw confidential transcripts in the ledger; use protected references.

## Checkpoint and migration

A new worker reads the accepted branch/commit, harness, cycle archives and decisions. `.dryforge/`
is ignored and will not appear automatically in a new clone/worktree. Transfer trusted state
explicitly or resolve the existing-harness guard. A checkpoint must not silently point to main
when the prior cycle's work is still on a feature branch. Leave failed worktrees for diagnosis.

## Verification

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s ci -p 'test_*.py'
bash build/build.sh
# Commit generated files before the clean-tree reproducibility check:
python3 ci/verify.py
```

Tests cover ledger transitions, rejected approvals, session replacement, stale artifacts, reuse,
fresh review, pause/recovery, budget/stall stops, persistence and five-platform mirroring. Synthetic
two/three-cycle tests are **not live Claude/Codex runs**. Before unattended use, demonstrate same-ID
ready/go, actual L3 spawning and review, a relayed question, human-only escalation, L2 reuse and
replacement, interruption recovery, and mission-level success evidence on the target host.

## Delegated tool decisions

L1 can be the decision provider for local tool permissions as well as cycle specs, within an
explicit human-approved [runtime policy](../src/skills/init/references/runtime-permissions.md).
This uses a `runtime_policy` event and state schema 3. It does not change the active Intent or
Ready approval. Schema-1/2 ledgers remain readable and human-only until explicitly opted in.
