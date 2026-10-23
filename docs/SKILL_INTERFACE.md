# Extending Ouroboros without replacing its decision model

This is an **optional L1 input/output and authority contract**, not a new agent runtime or an
installed Interview skill. It preserves Dryforge's distinction: human intent defines WHAT,
execution chooses HOW, and claims need evidence. L1 still owns the mission and next cycle; L2
still completes ready and go in one session; L3 keeps task-scoped execution and fresh review.

## What is shared, and what is not

```text
L1 issues a bounded request tied to the current intent digest
      |
interview / research / another future skill     (inline or delegated, as appropriate)
      |
versioned result envelope + skill-owned payload + decisive evidence
      |
L1 checks sources, not just the summary
      +-- findings only: accept or reject; no mission change
      +-- intent proposal: review -> human approval -> commit at a cycle boundary
```

Only the outside envelope is fixed. Interview preferences, research candidates and evaluation
findings remain different payloads. A new payload does not require a new branch in the generic
receiver. The human conversation, question order and technical stack are not standardized.

There is no always-on registry, hook, mandatory extra subagent or JSON around every ready/go step.
The reference policy is loaded only when L1 chooses an extension. Scope its work by the decision
that could change; do not collect fields that have no consequence. Existing ready/go audits,
LANDSCAPE/MCP tool preflight, verification gates and same-session requirements remain intact.

## Example envelope (illustrative, not a real interview or approval)

A request contains `schema_version`, `request_id`, `mission_id`, `skill`, `intent_digest`, `purpose`
and `input`. `intent_digest` must be computed from the current approved JSON contract, not guessed.

```json
{
  "schema_version": 1,
  "request_id": "interview-accuracy-1",
  "mission_id": "example-mission",
  "skill": "interview",
  "intent_digest": "<SHA-256 of the current approved contract>",
  "purpose": "Clarify accuracy versus automation before selecting the next cycle",
  "input": {"dialogue_ref": "private:conversation/42"}
}
```

The response echoes the identity fields and adds:

```json
{
  "status": "completed",
  "payload": {"preferences": ["Accuracy before convenience"]},
  "evidence": [{
    "id": "e1",
    "claim": "The user prioritizes a traceable source over automatic highlighting",
    "reference": "private:conversation/42#turn-3",
    "kind": "dialogue",
    "disposition": "VERIFIED"
  }],
  "unresolved": [],
  "next_action": "review",
  "proposal": {
    "intent_patch": {"goal": "Accurate, source-linked research notes"},
    "reason": "Clarification of the desired outcome in the cited turn"
  }
}
```

These are two explanatory excerpts; a real result includes the echoed identity fields. A result
with an unresolved product decision must use `needs_decision`, not `completed`. A technical unknown
should recommend `verify` instead of asking the human to invent an API fact. VERIFIED is a scoped
claim recorded by the producer, not machine certification. L1 must inspect the actual evidence.
Payload content and `next_action` are inert data. Neither can grant rights, run commands or mark a
mission complete. Missing sources stay unverified; finding nothing does not prove impossibility.

## Recording the flow

The CLI uses the standard library only. From a checkout, with actual files supplied by a trusted
host/controller (the placeholder paths below are not authorizations):

```sh
python3 src/skills/mission/scripts/skill_contract.py digest --json /project/approved-contract.json
python3 src/skills/mission/scripts/skill_contract.py validate \
  --request /project/request.json --result /project/result.json
python3 src/skills/mission/scripts/mission_state.py apply \
  --state /project/.dryforge/mission/state.json --event /project/next-event.json
```

All events retain the ledger's `id`, `mission_id`, `actor`, `op`, `expected_revision` fields.

| Operation | Submitted by the trusted controller for | Additional data and effect |
| --- | --- | --- |
| `skill_request` | L1 | `request`: record a unique request tied to the current intent. |
| `skill_result` | host or L1 receiver | `result`: validate identity/version/shape; store immutable output. No approval. |
| `skill_review` | L1 | `request_id`, `result_digest`, `verdict` (`accept`/`reject`), `basis`; acceptance includes `checked_evidence` IDs. |
| `skill_approve` | human | `request_id`, `result_digest`, `approval_ref`, `basis`: approve the reviewed intent proposal, not an arbitrary tool action. |
| `skill_commit` | L1 | `request_id`, `result_digest`: apply that exact approved patch if its base intent is still current. |
| `skill_cancel` | L1 | `request_id`, `basis`: explicitly defer/discard pending work; never pretend an unknown was resolved. |

`skill_contract.py validate` returns the result digest used by decisions. The ledger revalidates
and computes it too. Normal evidence-only output ends at review acceptance. An intent proposal
remains pending until committed or rejected/cancelled; the next cycle cannot skip that decision.
The exact request/result, review, approval and old/new intent digests remain available for audit.
The CLI prints request stages/digests, not full payloads, on each transition. Complete records stay
in the protected state file. Large raw data stays in referenced protected artifacts, not the 64 KiB
control envelope.

### Authority, lifetime and compatibility

Only human-approved goal, success_criteria, constraints, priorities and non_goals can be amended.
The interface cannot change delegation, human-only restrictions, mission identity, workspace or
execution budgets. `approve_ready` does not grant authority to change final intent. Consumed cycles
and stalled counts are preserved. Privilege/budget expansion needs a separately approved mission.

Ledger extension work is limited to initial or evaluated-cycle boundaries. Reinterview can occur
while paused with no active worker cycle; it does not itself resume the mission. A changing goal
inside ready/go uses the existing pause/question/abort rules before amendment. No session is
replaced by a new skill result and no stale approval is reused. Completed missions stay complete.

Old state-schema-1 ledgers load without a migration command. On first successful extension use the
state becomes schema 2, preventing older code from ignoring pending extension decisions. Normal
missions without extensions remain schema 1. Envelope schema version 1 is separate from the ledger
version; unknown versions are rejected. Do not downgrade an active ledger to bypass its checks.

## Adding a future Interview skill

Write `src/skills/interview/SKILL.md` plus only the references the task needs. Use this interface
for the L1 boundary; return proposals, not direct edits to the mission state. Keep original dialogue
references, ask only consequential questions, and respect the caller's actual tool permissions.
Initial interviewing may precede mission initialization: its output is a draft until the human
approves the contract using the existing initialization path. In an initialized mission, use the
recorded proposal flow above. Neither path manufactures a human approval.

The build discovers skill directories, but a new distributable skill still needs the Claude tool
mapping in `build/build.sh`, a Codex `platform/codex/skills/<name>/agents/openai.yaml` overlay, and
behavior/packaging tests. This is not automatic installation or dynamic code loading. A host
adapter must supply supported invocation and trusted event routing. No Interview implementation is
included in this change; synthetic test payloads are not installed skills.

## Verification and limits

Behavior tests cover mismatched identities, unknown versions, stale results/approvals, blocked
results, authority escalation, in-cycle amendments, counter preservation, replay and v1/v2 state
compatibility. Existing package tests check the five generated distributions. These tests do not
prove source accuracy, authentication, actual host skill invocation or live agent behavior.

The ledger is a trusted local consistency check, not a security sandbox. A malicious controller
can lie about `actor`, source checks or evidence. Keep writes and human-approval verification in the
trusted runtime; never route raw hook or child-agent output straight to authority-bearing events.

See the [runtime contract](../src/skills/mission/references/skill-interface.md),
[validator](../src/skills/mission/scripts/skill_contract.py),
[behavior tests](../ci/test_skill_interface.py), and [Mission guide](MISSION.md).
