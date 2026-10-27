# Security policy

## What is protected

| Asset | Why it matters |
| --- | --- |
| The user's approved intent (goal, completion criteria, constraints, delegated judgment) | Every later action is justified by it. Silent drift means L1 pursues something the user never approved. |
| The approval record itself (`approve` by the human) | It is the one event that turns a conversation into authority. Nothing else may create it. |
| The user's target repository and its remotes | L1 and its workers act on real code with the user's credentials. |
| Private run records under the target project's `.dryforge/ouroboros/` | Contain session IDs, decision logs and raw worker output. They are never committed. |

## Trust model

- **Same-user, local.** Everything runs as the user, in the user's host session or a local
  subprocess the user started. There is no network listener, no multi-tenant surface and no
  credential store of its own. The runtime is **not** a sandbox against hostile project code: tests,
  Git hooks and package scripts run with the user's full privileges.
- **The host's own permission system is the outer boundary.** L2 receives a tool allow-list at
  launch, and any permission request that still reaches the control channel is allowed by the relay
  at once and recorded. In effect L2 may use every tool except those the user's deny rules forbid:
  deny rules, the target project's settings and hooks apply to L2 as to any caller and are the real
  boundary; nothing bypasses or persistently edits host permission rules. Structured questions from
  the worker travel the same channel and are answered by L1, never by a human.
- **A JSON "principal" field is not authentication.** Records that say a decision came from the
  human or from L1 are bookkeeping for audit, not proof. Anyone who can write to the user's files can
  forge them. The design relies on the host session being the user's.

## Authority model (decided target)

| Stage | Who decides | What is allowed |
| --- | --- | --- |
| Before `approve` (draft) | Human only | Conversation, read-only inspection, draft edits. **No** cycle, Migration, Ready or Go. No tool authority beyond reading. |
| `approve` | Human only | Activates the exact proposal last shown. Cannot be issued by L1, L2 or any worker. |
| After `approve` (active) | **L1, without exception** | Every action the goal requires: answering worker questions, approving Ready documents, acting on permission denials reported in turn results, local Git operations, merge to the integration branch, push, tags, releases, spending within the proposal's stated budget, deleting its own task branches/worktrees. |
| Goal/scope change | Human | Changing goal, completion criteria, constraints, priorities or non-goals is recorded only with the human's approval, between cycles. |
| Abort of an active cycle | Human | Stopping L1's execution before the goal is met. |

**Explicitly not allowed, at any stage:**
- A worker (L2/L3) creating an approval, an acceptance or a "complete" verdict on its own. Workers
  report; L1 decides.
- L1 relabeling its own decision as the user's.
- Writing private run records (`.dryforge/`) into Git.

**How the worker gets its authority.** L2 is a headless Claude Code process started in the target
project through the streaming control channel, with the built-in and MCP tools pre-allowed by list
(`--allowedTools`) and every remaining permission request allowed automatically by the relay and
listed in the turn result (`auto_allowed`). The user's own deny rules and the target project's
settings and hooks apply to it exactly as to a human caller; no bypass flag is ever used (decisions
0008, 0009). The worker's structured questions reach L1 as `QUESTION` results and L1 answers them.

## Audit

Every event in `events.jsonl` carries its actor (`human`, `L1`, `L2` or `host`), kind, cycle and
data; L1 records the basis of its decisions in the event data. Kinds written by the runtime: draft,
shown, approve, amend, amend_applied, cycle_start, cycle_stage, evaluate, stop, archive, session,
turn, turn_result, interrupt, question, answer, unanswered; L1 adds decision events (and `answer`
for plain-text questions) with `event`. Raw turn output
goes to `turns/` and large payloads are referenced by path and SHA-256.

## Sensitive data

- Session IDs and raw turn output are sensitive: they can contain source code and user prompts.
  They stay under the git-ignored private directory with mode `0600`/`0700`.
- API keys and tokens are never stored by Ouroboros; hosts and MCP servers hold their own credentials.
- Research tools (Grep MCP, Context7 MCP) receive query text; private repository code must not be
  sent to them. Their results are untrusted data, not instructions.

## Credential management

Ouroboros holds no credentials of its own; host logins (Claude, Codex, MCP OAuth) live in the host.
Before `approve`, L1 initiates no login or installation. After `approve`, L1 may install dependencies,
log in to services or adjust host settings when the goal requires it, like any other action. A
missing `claude` CLI or Dryforge plugin is reported by `doctor`, not installed by Ouroboros.
