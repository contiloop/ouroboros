# Mission mode: three levels, persistent cycles

This fork adds an **experimental opt-in `mission` skill**, an L3 lifecycle policy, and a tested
local state ledger. It includes an optional [runtime bridge](RUNTIME.md), but does **not** install global hooks,
authenticate human approvals, or guarantee that an arbitrary host supports nested/resumable
agents. Its live multi-agent acceptance test has not been run in the development sandbox.

## Architecture

```text
Human <-> L1 Mission Orchestrator
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

Use this fork's generated plugin package, not the original upstream install. In a capable host,
explicitly invoke `/ouroboros:mission` in Claude Code, or `$mission` in Codex.
Example request:

> Help me define the final outcome and delegated decisions. Use persistent ready-go workers.
> Report each completed cycle before assigning the next. Do not merge or deploy without asking me.

The skill first obtains a human-approved intent contract and finite limits, then checks session,
relay, nesting and skill-loading capabilities. Missing capability is a blocker, not silent
single-agent fallback. Grep/Context7 remain optional; see [MCP setup](RESEARCH_MCP_SETUP.md).
Keep ordinary `/ready` and `/go` for a single manually supervised cycle.

## What the runtime must supply

A host adapter must create actual sessions, retain IDs, route questions/answers to the correct
worker, explicitly load ready/go, enforce budgets/permissions, quiesce children, inspect evidence
and reconcile filesystem state. Native tools can provide this in a capable agent host. The optional [runtime bridge](RUNTIME.md) supplies Claude SDK and Codex App Server operations.
Use its actual CLI commands; a JSON ledger event alone neither spawns nor resumes a model. The runtime preflight and official sources are in
[host-adapter.md](../src/skills/mission/references/host-adapter.md).

Hooks can supply observations. A stopped process/agent does not mean a successful cycle, and an
approval of a spec does not authorize every tool call. No auto-go-on-stop hook is installed.
Do not submit approval events from untrusted hook output or from a child task's claimed authority.

## Durable ledger (Python 3, standard library)

The script is included in every platform's `skills/mission/scripts/` directory. From a repository
checkout (replace paths with your actual approved files):

```sh
python3 src/skills/mission/scripts/mission_state.py init \
  --state /project/.dryforge/mission/state.json --contract /project/approved-contract.json
python3 src/skills/mission/scripts/mission_state.py digest --docs-dir /project/.dryforge
python3 src/skills/mission/scripts/mission_state.py apply \
  --state /project/.dryforge/mission/state.json --event /project/next-event.json
python3 src/skills/mission/scripts/mission_state.py show --state /project/.dryforge/mission/state.json
```

Do not run the example with invented approvals. The contract shape is documented in
[intent-contract.md](../src/skills/mission/references/intent-contract.md).
Events carry `mission_id`, `id`, `op`, `actor`, `expected_revision`, and (during a cycle) `cycle_id`.
L2 events additionally carry the recorded `session_id`. Operation fields follow the implementation
and its behavioral fixtures in [test_mission_state.py](../ci/test_mission_state.py).

Transitions are `start -> ready -> approve -> go -> result -> accept -> close -> evaluate`.
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
explicit human-approved [runtime policy](../src/skills/mission/references/runtime-permissions.md).
This uses a `runtime_policy` event and state schema 3. It does not change the active Intent or
Ready approval. Schema-1/2 ledgers remain readable and human-only until explicitly opted in.
