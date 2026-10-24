---
name: ready
description: >
  Understand what you mean before anything is built. Takes anything — a one-line idea, notes, a
  spec, or a mix — reads the project and existing solutions, asks only what is yours to decide,
  and writes your intent down for you to approve. Use when the user invokes the `ready` skill.
  Requires git.
---

# ready — entrypoint

**Force-load the complete `references/workflow.md` now.** It contains the preserved ready
procedure, core principles, stage ordering and gates; this entrypoint is not a substitute or a
summary. All `references/...` paths mentioned inside that file resolve from this **skill root**,
not from its `references/` directory. Load stage-specific references at their original stages.

Preserve LANDSCAPE's optional research delegation and tool preflight, the two independent
intent/document audits, and original intent grounding. Approval does not replace those audits.

## Caller interface

Use the ordinary question, approval and result interface throughout the cycle. Ask for the
information the task needs, wait for answers and explicit approvals, and report evidence through
the same session. Apply the same workflow and independent checks regardless of who supplies an
answer. Caller routing and authorization records belong to the host; do not inspect private
runtime state to identify the caller or create approval records yourself.

A stop/yield is not approval. Host permissions and the original verification/review gates still
apply. Do not claim a native slash-command invocation when you only loaded authorized procedure
files. Missing independent execution is a blocker, not permission to omit a required check.
