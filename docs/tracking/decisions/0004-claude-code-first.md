# 0004 — Claude Code first; Codex second; other packages format-only

## Context
The build emits five packages. Only Claude Code and Codex have transports in the runtime and only
Codex has had any live check. Verifying unattended multi-cycle behavior on every host is expensive,
and Grok, Agent Plugins and Antigravity have shown no demand.

## Decision
The project is "done" when a full unattended run (`init → approve → cycles → complete`) succeeds on
**Claude Code**. Codex is the second supported host and follows. Grok, Agent Plugins and Antigravity
packages are kept buildable and schema-valid but carry no execution support claim.

## Alternatives
- **Codex first** (it already had a live invocation check). Rejected by the user: Claude Code is the
  primary daily host.
- **All five equal.** Rejected: no transport or test exists for three of them.

## Consequences
- Live evidence is required on Claude Code before any completion claim; Codex evidence is a
  separate later item.
- Packaging validation for all five stays in CI (cheap), but README and docs must not imply the
  three extra hosts run L1.
