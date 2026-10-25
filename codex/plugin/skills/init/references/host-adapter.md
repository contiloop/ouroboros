# Host preflight and runtime boundary

The skill describes behavior; the host supplies persistent execution. Do not declare a host
supported merely because a manifest or a tool name exists. Before the first mission, verify:

1. A real L2 session ID can be created, messaged, yielded and resumed without substitution.
2. Questions/approval requests can reach L1 and replies return to that exact ID.
3. L2 can spawn L3 with appropriate tools and independent reviewer contexts.
4. The explicit user-authorized ready/go procedures can be loaded in L2, including references.
5. Repository and ignored state are accessible at the pinned checkpoint; previous writers stop.
6. The controller can enforce finite budgets, record unknown capacity and preserve recovery state.

Use **native nested sessions** when all checks work. The bundled optional **external persistent session controller**
(`runtime-bridge.md`, `scripts/worker_runtime.py`) is also valid: L2 is a full host session with its own L3 agents. If neither is available, stop with
a capability report. Do not use one-shot shell commands with only a summary as a fake persistent
worker. Do not auto-install clients, change permissions or enable experimental flags.

## Claude Code

Official subagent documentation describes nested spawning and resuming an agent by ID, but actual
limits and tools depend on the installed version. It also documents that ordinary subagents do
not receive AskUserQuestion, and manual-only skills cannot be preloaded using the agent `skills`
field. Verify a supported parent-message relay and native explicit command invocation;
do not rely on frontmatter to grant a tool the host removes. A full SDK worker accepts
`/dryforge:ready <goal>`, then `/dryforge:go <approval/instruction>` in the same session. Check
`slash_commands` in its init event and load the installed plugin through selected settings or
`--dryforge-plugin`. Do not paste skill files as a substitute for an unavailable command.

Use the installed host's actual Agent/message/resume interfaces. Do not hardcode a guessed Agent
`resume` parameter or silently replace a lost ID. An SDK controller can manage separate worker
sessions and callbacks, and the optional runtime implements this path; see `runtime-bridge.md`. Configured MCP tools are still subject to L2/L3
availability checks. Keep the optional Grep/Context7 fallback from LANDSCAPE.

## Codex

Verify the installed client's nested-agent, input/approval and resume interfaces. A controller
using App Server can maintain a worker thread and deliver subsequent turns; a thread completion
notification is not a completed ready-go cycle. Do not assume a configuration key or default
nesting depth across client versions. Check actual schemas and capabilities before invocation.
If a top-level worker session is used instead of native nesting, keep the same worker thread
through ready/go and give it its own independent task agents. Resolve `dryforge:ready` and
`dryforge:go` using `skills/list` for the workspace. Send `$dryforge:ready` / `$dryforge:go` with the
caller's prompt and the corresponding native `skill` input (name and returned absolute path).
The host loads the skill; the controller does not concatenate SKILL.md or workflow references.
Migration uses the same host-specific invocation rules for `dryforge:migration`.

## Optional executable transport

The bundled worker_runtime.py uses a persistent ClaudeSDKClient or Codex stdio App Server thread.
L2 is a full host session, so L1 need not consume an extra native subagent nesting level. L2 still
needs actual L3 tools; this capability is not certified by starting the controller. The bridge
checks exact-cycle Go approval, records only explicit execution start, and never infers approval,
acceptance or mission completion from receipts. Real model behavior is not certified. Python
3.11+ and POSIX locks are required; use macOS/Linux/WSL. See `runtime-bridge.md`.

## Hooks: observe, do not authorize

Lifecycle hooks/notifications may report session start/end, tool failures, child start/stop,
compaction or interruption. Adapt real host events to `observe` (or a controller-validated
`interrupt`). A SubagentStop, Stop, process exit 0 or end-of-turn is **not** `result`, `accept`,
`close` or `complete`. A PermissionRequest is not ready approval. No auto-go-on-stop hook.
Do not stream raw transcripts or all tool output into L1; send bounded identities, artifact
references and actionable blockers. L1/host authenticates the source before authority events.
This extension does not install global hooks or turn off permission prompts.

## Official references checked 2026-10-23

- Claude Code subagents: https://code.claude.com/docs/en/sub-agents
- Claude session persistence: https://code.claude.com/docs/en/agent-sdk/sessions
- Claude hooks: https://code.claude.com/docs/en/hooks
- Codex subagents: https://developers.openai.com/codex/multi-agent
- Codex App Server: https://developers.openai.com/codex/app-server

These establish integration surfaces, not a successful test on the user's installation. A live
acceptance test must show two cycles, at least one L3 implementer and independent reviewer,
same-ID ready/go, a delegated question, a human-only escalation, reuse then fresh-worker handoff,
and interruption recovery. Static/unit tests do not prove model compliance or live SDK behavior.

Runtime tool approvals can be scoped to L1 through a human-approved execution-policy attachment.
See `runtime-permissions.md`. This uses the host's ordinary exact-call allow response, not an
allow-for-session, exec-policy amendment, network grant or permission bypass. An updated plugin
cannot replace an already-running controller: reconcile and resume it explicitly on the new code.
