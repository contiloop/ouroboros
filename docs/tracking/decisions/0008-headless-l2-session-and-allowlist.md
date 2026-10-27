# 0008 — L2 is a headless Claude Code session with a tool allow-list

## Context
Installed Dryforge skills on Claude Code are marked user-invocable only. A probe on 2026-10-27
showed a Claude Code subagent neither sees `dryforge:*` nor has a question tool, so the "native
subagent" path cannot host L2. A headless `claude -p` process, given `/dryforge:ready` as its user
message, loads the real skill, answers questions as plain text, and continues with `--resume`.
Without a tool allow-list a headless turn silently denies Write and Bash.

## Decision
L2 is one headless `claude -p … --output-format json` session per run, resumed by session id for
every later turn and kept across cycles by default (fresh only on REPLAN, loss, context pressure or
Migration). Every turn runs detached; L1 waits with a blocking `session-wait` run as a background
shell command. Tool permission is an allow-list (`--allowedTools` with the built-in tools plus
`mcp__*`), never a bypass flag; the user's deny rules and the target project's settings still apply.
Since decision 0009 the allow-list is not a ceiling: remaining permission requests are allowed
automatically by the relay, so the deny rules are the effective boundary.

## Alternatives
- **Claude Code subagent as L2.** Rejected: cannot invoke the installed skill, no question relay.
- **`claude-agent-sdk` with a `can_use_tool` relay (the old runtime).** Rejected: rebuilds the
  per-call permission machinery decision 0001 abolished and adds a third-party dependency.
- **`--dangerously-skip-permissions` / `bypassPermissions`.** Rejected by the user: it would also
  ignore deny rules they set; the host must stay the outer boundary.
- **Fresh session every cycle.** Rejected by the user: design context should carry across cycles.

## Consequences
- The runtime is a thin port/adapter around the `claude` CLI; a Codex adapter implements the same
  `HostSession` protocol later.
- A permission denial is part of a turn's result for L1 to act on, never a question for the user.
- `--owner` must carry the L1 host pid: every CLI call is a short-lived process, so recording its own pid would make every owner stale and the second-L1 refusal would never fire.
