# Ouroboros operation

`ouroboros:init` starts a conversation about the outcome, completion criteria and delegation.
`ouroboros:approve` hands that reviewed proposal to L1. L1 chooses development cycles, answers
questions, reviews Ready documents and results, and continues until the goal is met. The user
can keep talking throughout; routine progress updates do not require a reply.

## Responsibility

```text
User ↔ L1: intent, delegated judgment, cycle selection and result acceptance
        ↕
       L2: ordinary Dryforge Ready → Go → result approval → cleanup
        ↕
       L3: implementation/review agents managed by Dryforge
```

L2 may implement directly or delegate. Dryforge owns task scheduling, L3 lifecycle and worktrees.
Ouroboros preserves the same L2 through a cycle and relays caller decisions. It does not install
another set of L3 scheduling rules. Reuse or replace L2 only after an evaluated checkpoint;
interrupted cycles reconcile and resume their recorded session.

## Use

| Host | Start the conversation | Hand over the reviewed proposal |
| --- | --- | --- |
| Codex | `$ouroboros:init` | `$ouroboros:approve` |
| Claude Code | `/ouroboros:init` | `/ouroboros:approve` |

Install Dryforge for the selected worker host. L1 explicitly invokes its Ready/Go/Migration skills;
the host loads their instructions. The old public Mission skill and optional extension protocol
are no longer shipped. Existing private records remain under ignored `.dryforge/mission/`.

The [L1 procedure](../src/skills/init/references/orchestration.md) defines the loop and when to use
Migration. The [runtime guide](../src/skills/init/references/runtime-bridge.md) is the single
operating reference for connection commands, progress records, recovery and delegated tool approvals.
[Runtime policy](RUNTIME_POLICY.md) retains detailed implementation/version compatibility.
[Grep/Context7 setup](RESEARCH_MCP_SETUP.md) is optional.

A reviewed goal change uses `amend` at a cycle boundary. It preserves authority, history and
consumed limits. Pending legacy extension records require explicit disposition; cancelling a
record does not answer an unresolved product question. A new checkout needs both the accepted
Git checkpoint and explicit transfer of trusted ignored state.

## Implementation and verification

The ledger records decisions; it does not run agents. Native host sessions can supply the
connection, or the optional Python controller uses Codex App Server/Claude SDK and a SQLite
mailbox. There is no extra model supervisor or network listener. Host permissions stay in force.
The same-user controller is not an adversarial security boundary and does not authenticate a
JSON approval principal. A timeout or UNCERTAIN receipt needs reconciliation, not automatic replay.

Protocol tests include SDK-shaped doubles, real local Git/SQLite and subprocesses; these are
not live authenticated model runs. Passing them is not a promise of model behavior, L3 support
or an uninterrupted multi-cycle run. Live verification must exercise same-session Ready/Go,
questions, delegated approvals, independent review, cleanup and interruption recovery.

Run `python3 -B -m unittest discover -s ci -p 'test_*.py'` and `bash build/build.sh` for regression
and package checks. `python3 ci/verify.py` also verifies reproducible generation from a clean tree.
