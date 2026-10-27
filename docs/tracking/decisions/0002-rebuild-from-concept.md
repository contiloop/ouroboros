# 0002 — Rebuild from the concept; existing code is a blank slate

## Context
The repository grew from a Dryforge fork into ~2.5k lines of Python runtime plus skill text, with
five ledger schema versions, four policy versions and three Git-check modules, most of it devoted to
the per-call permission model that decision 0001 abolishes. Two days of commits show the shape still
changing with every release.

## Decision
Keep only the concept: a user talks to L1 (`init`), hands over once (`approve`), L1 runs installed
Dryforge Ready–Go cycles in a persistent L2 session and evaluates the goal. Everything else is
rewritten; no existing module is required to survive.

## Alternatives
- **Keep the ledger and mailbox, strip the policy layer.** Rejected: the ledger's stage machine,
  digests and schema history are shaped around the policy model and Dryforge's three-document gate;
  carrying them forces the new design to inherit those constraints.
- **Incremental refactor toward a harness-replaceable core** (the Korean design draft). Rejected:
  it adds abstraction for hypothetical second harnesses before the first host even works end to end.

## Consequences
- Backward compatibility with existing `.dryforge/mission/state.json` ledgers, schema versions and
  policy objects is **not** required. Earlier guarantees ("old grants never widen") become moot once
  the grant concept disappears.
- Until the rebuild lands, the old code is what runs; agents fixing it should not extend the policy
  layer.
- Product docs `docs/MISSION.md` and `docs/RUNTIME_POLICY.md` describe the old model and must be
  rewritten with the rebuild.
