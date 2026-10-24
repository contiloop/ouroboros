---
name: approve
description: >
  Approve the reviewed Ouroboros intent and execution scope, then hand Ready/Go cycle management
  to L1. Use when the user explicitly invokes ouroboros:approve or the approve skill for Ouroboros.
  This is the outer handoff; it does not bypass Ready document review or implementation checks.
---

# ouroboros:approve — hand the reviewed intent to L1

This is the user's explicit handoff after `ouroboros:init`. Resolve the current draft in the
selected workspace and the exact proposal last shown to the user. Read
`../init/references/intent-contract.md` and, if execution delegation was proposed,
`../init/references/runtime-permissions.md`.

## Activate exactly what the user reviewed

If a draft is missing, materially incomplete or changed since it was shown, prepare/show the
missing or changed proposal first. The invocation cannot approve undisclosed contents. Explain
that specific gap and request approval of the concrete proposal; never fabricate a prior grant.
When the current invocation covers the reviewed draft, proceed without another confirmation.

Record one `activate` event using `../init/scripts/mission_state.py apply`: actor `human`, the
actual invocation as `approval_ref`, the review/transcript as `basis`, current revision and
`expected_proposal_digest` from `show`. It atomically approves the exact intent plus the proposed
runtime policy, if any. L1 records later decisions as `L1`, not human. A draft's proposed policy
has no effect until this activation. Existing approved runs retain their current scope: repeated
approve is not a reset, a budget refill or permission expansion. Reconcile/resume a paused run
only under its existing authority; never silently replace its L2 session.

## Take responsibility for execution

Force-load the complete `../init/references/orchestration.md` and follow it now. Its paths resolve
from the init skill root. L1 selects a cycle, invokes ordinary Ready on L2, answers its questions,
reviews the actual documents, approves them when warranted and invokes Go in the same L2 session.
L1 checks actual outcomes, requests corrections and chooses the next cycle until the approved
outcome is met or a real boundary needs the human. Preserve all independent review/test gates.

Do not stop at acknowledging approval or merely writing an ACTIVE state. Perform the host
preflight and begin the authorized loop; state records alone do not run agents. Do not ask the
human to reapprove each Ready/Go cycle or eligible tool request already delegated. This handoff
is distinct from the inner Ready approval, which L1 performs against exact documents.

The human can keep talking to L1 throughout. Incorporate in-scope clarifications and surface the
impact of changes requiring new authority. Lower tiers receive ordinary user requests and
answers; do not expose L1 identity, interview machinery or private approval records to them.
