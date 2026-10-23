---
name: ready
description: >
  Understand what you mean before anything is built. Takes anything — a one-line idea, notes, a
  spec, or a mix — reads the project and existing solutions, asks only what is yours to decide,
  and writes your intent down for you to approve. Use when the user invokes the `ready` skill.
  Requires git.
disable-model-invocation: true
allowed-tools: Read, Edit, Write, Bash, Grep, Glob, Agent, AskUserQuestion, WebSearch, WebFetch, SendMessage
---

# ready — entrypoint

**Force-load the complete `references/workflow.md` now.** It contains the preserved ready
procedure, core principles, stage ordering and gates; this entrypoint is not a substitute or a
summary. All `references/...` paths mentioned inside that file resolve from this **skill root**,
not from its `references/` directory. Load stage-specific references at their original stages.

Preserve LANDSCAPE's optional research delegation and tool preflight, the two independent
intent/document audits, and original intent grounding. L1 approval does not replace those audits.

## Mission mode (explicit opt-in only)

When a trusted mission dispatch supplies a human-approved intent/delegation contract, force-load
`../mission/references/cycle-contract.md`. You are L2, the existing Dryforge main agent, not a
leaf task worker. Keep the **same host session** through ready, approval, go and result handoff.
Use the verified decision relay for questions and approvals; the provider may be human or L1,
but its provenance and authority must be recorded. Do not infer delegation from an agent's name.
Without this contract, preserve the normal human-facing workflow. A stop/yield is not approval.
Do not choose another cycle yourself; report to L1 after completing this one. Session handoff is
not migration. Host permissions and all original verification/review gates still apply.

These explicit session/relay additions govern mission transport; the preserved workflow governs
what must be asked, built, verified and reviewed. Do not claim a native slash-command invocation
when you only loaded its authorized procedure files. A capability missing from the host is a
blocker, not a reason to silently flatten levels or skip an independent check.
