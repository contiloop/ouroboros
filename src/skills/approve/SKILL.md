---
name: approve
description: >
  Hand the reviewed Ouroboros proposal to L1 when the user invokes ouroboros:approve.
  Start autonomous cycle management within that scope, retaining worker review gates.
---

# Hand execution to L1

Resolve the current draft and the exact proposal last shown to the user. If missing, incomplete
or materially changed, show the concrete gap before seeking approval. Otherwise this invocation
is the approval; do not request it again.

Use `../init/references/runtime-bridge.md#records` to record `activate` against the
current revision and `expected_proposal_digest`. Record the actual human invocation as the
approval source; later delegated decisions belong to L1. Repeated approve preserves an existing
run's authority, session and consumed limits.

Load the complete `../init/references/orchestration.md` and begin the authorized loop now.
Recording ACTIVE or acknowledging the handoff is not execution. Continue talking with the user
throughout; changes follow the scope and recovery rules in that procedure.
