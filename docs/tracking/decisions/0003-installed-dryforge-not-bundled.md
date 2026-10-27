# 0003 — Invoke the installed Dryforge; remove the bundled copies

## Context
The repository forked from Dryforge and still ships `ready`, `go` and `migration` under
`src/skills/`, now diverging from upstream (different `SKILL.md`, an extra `agent-lifecycle.md`).
Since v1.4.x L1 invokes the *installed* `dryforge:*` skills through the host's native mechanism and
refuses to paste procedure text. The bundled copies survive only for "run one cycle yourself".

## Decision
Ouroboros does not ship Dryforge skills. L1 requires Dryforge to be installed on the L2 host and
invokes it natively (`/dryforge:<kind>` on Claude Code, `$dryforge:<kind>` + skill input on Codex). A
missing or ambiguous installed skill is a reported capability gap, never a fallback to a bundled copy.
The bundled `ready`/`go`/`migration` directories are legacy and will be removed.

## Alternatives
- **Keep bundled copies synchronized with upstream.** Rejected: duplicate maintenance, and users
  would hold two different `ready` skills (`ouroboros:ready`, `dryforge:ready`) on one host.
- **Vendor Dryforge as a pinned dependency inside the package.** Rejected: hosts load skills by
  plugin, so the user would still see two plugins; version drift problems remain.

## Consequences
- Dryforge is a hard runtime dependency; installing it on the L2 host is a user prerequisite.
- Build mappings for the three skills (Claude `allowed-tools`, Codex `openai.yaml`, shared reference
  byte-identity pairs) and the contract tests that read their text go away with them.
- Ouroboros has no say over Dryforge's internal gates (3-document review, independent review); L1
  satisfies them as an ordinary caller.
