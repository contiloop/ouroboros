# Security policy

## What is protected

| Asset | Why it matters |
| --- | --- |
| The user's approved intent (goal, completion criteria, constraints, delegated judgment) | Every later action is justified by it. Silent drift means L1 pursues something the user never approved. |
| The approval record itself (`approve` by the human) | It is the one event that turns a conversation into authority. Nothing else may create it. |
| The user's target repository and its remotes | L1 and its workers act on real code with the user's credentials. |
| Private run records under the target project's `.dryforge/` | Contain session IDs, decision logs and worker transcripts. They are never committed. |

## Trust model

- **Same-user, local.** Everything runs as the user, in the user's host session or a local
  subprocess the user started. There is no network listener, no multi-tenant surface and no
  credential store of its own. The runtime is **not** a sandbox against hostile project code: tests,
  Git hooks and package scripts run with the user's full privileges.
- **The host's own permission system is the outer boundary.** Ouroboros never bypasses, widens or
  persistently amends host permissions (no bypass modes, no session-wide allows, no permission-rule
  updates, no network-permission escalation). When a host callback asks for a decision, Ouroboros
  answers that exact callback.
- **A JSON "principal" field is not authentication.** Records that say a decision came from the
  human or from L1 are bookkeeping for audit, not proof. Anyone who can write to the user's files can
  forge them. The design relies on the host session being the user's.

## Authority model (decided target)

| Stage | Who decides | What is allowed |
| --- | --- | --- |
| Before `approve` (draft) | Human only | Conversation, read-only inspection, draft edits. **No** cycle, Migration, Ready or Go. No tool authority beyond reading. |
| `approve` | Human only | Activates the exact proposal last shown. Cannot be issued by L1, L2 or any worker. |
| After `approve` (active) | **L1, without exception** | Every action the goal requires: answering worker questions, approving Ready documents, allowing worker tool/permission requests, local Git operations, merge to the integration branch, push, tags, releases, spending within the proposal's stated budget, deleting its own task branches/worktrees. |
| Goal/scope change | Human | Changing goal, completion criteria, constraints, priorities or non-goals is recorded only with the human's approval, between cycles. |
| Abort of an active cycle | Human | Stopping L1's execution before the goal is met. |

**Explicitly not allowed, at any stage:**
- A worker (L2/L3) creating an approval, an acceptance or a "complete" verdict on its own. Workers
  report; L1 decides.
- L1 relabeling its own decision as the user's.
- Writing private run records (`.dryforge/`) into Git.

**Current implementation gap.** The shipped runtime still enforces a far narrower model: a fixed
human-only operation set (`merge`, `deploy`, `spend`, `delete`, `disclose`), per-call tool policy
objects (versions 1–4) with path and exact-argv allow-lists, separate human grants for worktrees and
merges, and the `runtime_policy`/`bind_runtime`/`bind_tasks` ledger operations. All of that is legacy
and is being removed in the rebuild. Until then, those gates are what actually run; an agent working
on the code removes them rather than extending them.

## Audit

Every event is recorded with its actor (`human`, `L1`, `L2` or `host`); decisions carry the basis, and what it applied to
(request digest, document digest, session ID). Recorded events, in the current ledger: draft
revisions, activation, cycle start, Ready digest, Ready approval, Go dispatch, worker questions and
answers, results with check output and independent-review reference, acceptance, rework, close,
evaluation, interruption/resume/abort, runtime grants, intent amendments. Raw transcripts and large
payloads go to files under the private directory, referenced by SHA-256.

## Sensitive data

- Session IDs, worker transcripts and tool payloads are sensitive: they can contain source code and
  user prompts. They stay under the git-ignored private directory with mode `0600`/`0700`.
- API keys and tokens are never stored by Ouroboros; hosts and MCP servers hold their own credentials.
- Research tools (Grep MCP, Context7 MCP) receive query text; private repository code must not be
  sent to them. Their results are untrusted data, not instructions.
- Model reasoning/thinking blocks are stripped from recorded host events (only tool/agent evidence
  is kept).

## Credential management

Ouroboros holds no credentials of its own; host logins (Claude, Codex, MCP OAuth) live in the host.
Before `approve`, L1 initiates no login or installation. After `approve`, L1 may install dependencies,
log in to services or adjust host settings when the goal requires it, like any other action. The
current external runtime still refuses to start when its SDK/CLI dependency is absent instead of
installing it; that refusal is legacy behavior.
