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
shared across resumes/replacements. Preserve private runtime state under `.dryforge/` during cleanup;
only clean task worktrees and archive the active 3-doc as the workflow specifies.

## Caller interface

Use the ordinary question, approval and result interface throughout the cycle. Ask for the
information the task needs, wait for answers and explicit approvals, and report evidence through
the same session. Apply the same workflow and independent checks regardless of who supplies an
answer. Caller routing and authorization records belong to the host; do not inspect private
runtime state to identify the caller or create approval records yourself.

A stop/yield is not approval. Host permissions and the original verification/review gates still
apply. Do not claim a native slash-command invocation when you only loaded authorized procedure
files. Missing independent execution is a blocker, not permission to omit a required check.
