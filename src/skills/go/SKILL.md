---
name: go
description: >
  Carry out the intent approved in `ready`, as meant, and prove it with checks that actually ran.
  Comes back to you if the work would change what you approved, keeps the project docs in step,
  and never merges on its own. Use when the user invokes the `go` skill after `ready`. Requires
  git.
---

# go — entrypoint

**Force-load the complete `references/workflow.md` now.** It contains the preserved go
procedure, core principles, stage ordering and gates; this entrypoint is not a substitute or a
summary. All `references/...` paths mentioned inside that file resolve from this **skill root**,
not from its `references/` directory. Load stage-specific references at their original stages.

Also force-load `references/agent-lifecycle.md` before dispatch/resume. It extends session
lifetime, not task selection: preserve the workflow's direct MECHANICAL/NONE path, RISKY and
parallel delegation, worktree gates and fresh final review. The ordinary bounded retry count is
shared across resumes/replacements. Keep an active `.dryforge/mission/` ledger during cleanup;
only clean task worktrees and archive the active 3-doc as the workflow specifies.

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
