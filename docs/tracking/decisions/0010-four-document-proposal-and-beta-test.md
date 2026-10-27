# 0010 — Four-document proposal, work graph, beta test, model enforcement

## Context
The single `proposal.md` of cycle 001 was a placeholder with eight headed sections and no interview
discipline. The user wanted `init` to reach the quality of Dryforge's own documents: usage scenarios
as the ore, a workflow extracted from them, validation items with environment and evidence, a product
outline without code detail, and an explicit statement of what L1 holds.

## Decision
`init` fills four documents the user approves as one set: `scenario.md`, `validation.md`, `spec.md`,
`delegation.md` (the user's design; the fourth file, the field minimums, file names and the YAML
shape are the producer's choices). The interview follows Dryforge-style elicitation. `approve`
checks completeness and the shown digest of the set. After approval L1 writes a work graph of nodes
(one node = one cycle, every workflow step and validation item owned by a node), sends the worker the
whole context each cycle and asks it to verify its items, applies the L2 model as the session flag
and the L3 model through `CLAUDE_CODE_SUBAGENT_MODEL` on the worker process (verified), and when every
node is done opens a beta cycle in which it runs the scenarios itself; COMPLETE is accepted only on a
beta cycle. A validation item only a human can check is raised as ESCALATE and recorded as
`verified`; that is evidence, not consent (the one post-approval question). Beta cycles are exempt
from `max cycles`; the cycles limit is enforced at development `cycle-start` and when more development
is asked for, not on CONTINUE. Legacy single-file records are archived, never converted.

## Alternatives
- **Keep one proposal file with more sections.** Rejected by the user: scenarios and validation need
  their own structure to drive the work graph and the beta test.
- **L2 verifies, L1 only reads the report.** Rejected by the user: "L1 is me" — the beta test is L1
  exercising the product; L2's own verification stays as a complement.
- **Accept L2's evidence or an efficient check for human-only items.** Rejected by the user in favor
  of ESCALATE: a human check is asked for, as a verification.
- **Request the L3 model in the message.** Rejected: the environment variable enforces it.

## Consequences
- `core.check_set` and `core.set_digest` are the single authorities for completeness and identity.
- `delegation.md` is never quoted to L2; scenario, validation and spec content is.
- L1 edits only `workgraph.yaml` on its own after approval.
- The live unattended run (tracking item 1) exercises this design next.
