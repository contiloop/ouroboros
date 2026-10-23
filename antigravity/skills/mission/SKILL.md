---
name: mission
description: >
  Hold an approved user intent across multiple ready-go cycles. Delegate each cycle to one
  persistent worker, review its evidence, then reuse or replace it at a cycle boundary.
  Use only when the user explicitly invokes mission. Requires a host with resumable workers,
  decision relay, and nested agents; never simulate unavailable capabilities.
---

# mission — intent owner, not an implementation worker

Reply in the user's language. This is an opt-in experimental extension; ordinary ready/go usage
is unchanged. Force-load `references/intent-contract.md`, `references/cycle-contract.md`, and
`references/host-adapter.md` before delegation. The executable ledger is
`scripts/mission_state.py`; it validates transitions, not model behavior or tool permissions.

## Three levels, different lifetimes

- **L1 / Mission Orchestrator (you):** understand the human's intent, preserve its constraints,
  answer within delegated authority, evaluate outcomes, and select the next cycle. Do not absorb
  raw task logs or implement the cycle yourself to hide a missing worker capability.
- **L2 / Cycle Worker:** the existing Ouroboros main agent. One assignment is **one ready-go cycle**.
  The same L2 session must span questions, ready approval, go, result approval, and handoff.
  It may receive another cycle only after reporting back and L1's evaluation. It is **not** an
  autonomous sector owner allowed to invent its own successive cycles.
- **L3 / Task agents:** L2's researchers, implementers, and independent reviewers. L2 controls
  their lifecycle using `../go/references/agent-lifecycle.md`. L1 does not micromanage them.

**Mission success is not cycle success. Session reuse is not authority reuse.** Evidence from
one commit, approval, or task cannot silently authorize a different one.

## 1. Align and bound the mission

Read the human's original statements. Establish a user-approved intent contract: desired outcome,
observable success criteria, priorities, non-goals, forbidden actions, delegated decisions, and
finite execution limits. Preserve exact decision excerpts or transcript references, not just a
paraphrase claiming to understand the user. Never infer permission to merge, deploy, spend money,
expose private data, or destroy state from a general request to finish the project.

The human approves the contract before any cycle. Store it and the decision ledger under
`.dryforge/mission/`, outside tracked project documentation. Ensure `.dryforge/` is ignored.
Use `scripts/mission_state.py init` to initialize a ledger when Python 3 is available; otherwise
pause for an explicit compatible runtime, not an untracked autonomous loop.

## Optional skill boundary — evidence in, authority stays here

When a human or a genuine decision gap calls for an extension, force-load
`references/skill-interface.md` **at that point**, not for every ordinary cycle. Use a versioned
request/result envelope; keep the skill-specific payload free of artificial universal checklists.
No extension is mandatory, no skill name is privileged, and a skill does not imply a new agent.
L1 retains the raw intent context; existing ready/go and independent-review contracts stay intact.

Accepting a skill's findings is not accepting a changed mission. Inspect decisive sources before
using the result. If it proposes new intent, use **PROPOSE → REVIEW → APPROVE → COMMIT**: review
exact content, obtain the human's explicit approval, then commit at an evaluated cycle boundary.
A payload, `completed` flag, hook, or `next_action` cannot approve anything. Use the local ledger's
`skill_*` operations for these records; it checks consistency, not truth or human identity.
Return technical unknowns to research/testing, not to the human as invented preference questions.

## 2. Verify the host, then choose a cycle

Run the capability preflight in `references/host-adapter.md`. Require actual worker identity,
resume/message support, L2-to-L3 spawning, explicit procedure loading, and a question relay.
A tool appearing in L1's list is not proof it works in L2. No spawning capability → report a
blocker; do not silently flatten the three levels. Do not change host permissions automatically.

Select one bounded outcome that advances a mission success criterion. Read the current accepted
Git checkpoint and harness. Resolve branch integration before assigning dependent work: a feature
commit not merged to main is **not** available in a checkout of main. Use the exact accepted
branch/commit as the next workspace. Preserve normal go clean-tree and base-branch preconditions;
when these cannot be reconciled without integration, request the required approval and pause.

## 3. Assign or reuse L2

Start one cycle at a time per working repository. Select **REUSE** only at a completed, evaluated
cycle boundary: the host confirms the same session is resumable, context headroom is sufficient
for the next cycle plus recovery, and no old child is still writing. Otherwise **SPAWN** a fresh
L2 with the checkpoint packet. Unknown headroom is not evidence of sufficient capacity. Never
invent token counts. Do not replace L2 between ready and go merely to clear its context.

Give L2 the cycle goal, intent/delegation contract, decision-provider identity, project path,
expected Git checkpoint, harness/previous-cycle pointers, complete ready/go procedure paths, and
`references/cycle-contract.md`. Record the real session ID returned by the host. Keep its session
available while waiting for questions or approval; a yielded turn is not a closed session.

## 4. Relay decisions and approve exact artifacts

L2 uses its normal question-and-approval interface. You are its decision provider, not a new
source of product intent. Answer only when the contract or human evidence entails the decision;
otherwise ask the human and relay the actual answer. Record principal, scope, basis and request ID.
Do not impersonate a human approval in the audit log.

At READY_REVIEW, read the three actual documents and compare them with the cycle and mission.
Approve the exact combined content digest, not merely their paths or a summary. Send go to the
**same session**. If the documents change, the approval is stale and ready review must happen
again. If the host cannot invoke manual-only skills programmatically, use its supported explicit
user-invocation/authorized-procedure-loading path or stop; never claim an invocation that failed.

## 5. Evaluate, then loop

L2 runs go with its original dispatch, tests, integration and independent-review gates. It may
implement low-risk sequential work itself; risky/parallel work still earns L3 agents. L2 resolves
local implementation exceptions within the approved spec. Only decisions outside that authority
are relayed upward. A negative feasibility experiment stops dependent work, as in ordinary go.

Inspect the result and captured evidence, not just DONE. Accept within delegated authority, then
let the same L2 finish archiving, checkpointing and quiescing children. Receive a compact packet:
cycle outcome, requirement coverage, commit/branch, check commands/results, archive/harness paths,
accepted concerns, unresolved facts, and safe session-reuse status. Keep raw logs on disk.

Choose **CONTINUE**, **REPLAN**, **ESCALATE**, or **COMPLETE**, with evidence and a reason. CONTINUE
and REPLAN return to step 2; only L1 chooses the next cycle. Enforce cycle/stall/time/cost limits
before dispatch; unavailable budget telemetry must be disclosed, never treated as infinite credit.
COMPLETE requires evidence for every mission success criterion, not just green unit tests.

## Failure and recovery

An interrupted session pauses the cycle. Reconcile files, live children and external effects, then
resume the recorded L2 ID. A new worker with a summary is a **handoff**, not a resumed session.
If the original session is unrecoverable, preserve the checkpoint and ask for an explicit abort/
replacement decision. Never replay a side-effecting operation just because its last message was
lost. Hooks are observations, never approvals or proof of completion.

Spawning a new worker does **not** invoke migration. Migration initializes an existing project's
harness; a session handoff reads the existing harness. A fresh clone/worktree may lack the ignored
`.dryforge/status.json` and archives: explicitly transfer trusted state or resolve ready's existing-
harness guard, rather than treating the project as new or regenerating its documentation.
