# Contracts

## User-facing commands (the stable contract)

| Host | Command | Input | Effect | Errors |
| --- | --- | --- | --- | --- |
| Claude Code | `/ouroboros:init` | free text about the goal, optionally over many turns | starts or continues the proposal conversation; writes/updates the draft record; never runs a cycle | none fatal; a project without git is reported |
| Codex | `$ouroboros:init` | same | same | same |
| Claude Code | `/ouroboros:approve` | none | approves the proposal exactly as last shown and starts L1's autonomous loop; conversation stays open | no draft → "nothing proposed"; proposal changed since shown → shows the gap, no approval |
| Codex | `$ouroboros:approve` | none | same | same |

All skills are manual-only on every host: they are never auto-selected from semantic similarity
(`disable-model-invocation: true` for Claude/Grok/Agent Plugins, `allow_implicit_invocation: false`
for Codex, `rules/invocation.md` for Antigravity).

The bundled `ouroboros:ready`, `ouroboros:go` and `ouroboros:migration` commands exist in the current
packages but are not part of the supported contract (slated for removal).

## Host-facing packaging contract

| Consumer | Reads | Must hold |
| --- | --- | --- |
| Claude Code | `.claude-plugin/marketplace.json` → `claude/.claude-plugin/plugin.json`, `claude/skills/*/SKILL.md` | frontmatter `name`, `description`, `allowed-tools`, `disable-model-invocation: true` |
| Codex (current) | `.agents/plugins/marketplace.json` → `codex/plugin/plugin.json` (Agent Plugins 1.0, `extensions.com.openai.interface`) | `skills/*/SKILL.md` + `skills/*/agents/openai.yaml` with `interface` and `policy.allow_implicit_invocation: false` |
| Codex (older) | `codex/plugin/.codex-plugin/plugin.json` | identical identity/interface to the root manifest; `"skills": "./skills/"` |
| Grok | `.grok-plugin/marketplace.json` → `grok/plugin.json` | SKILL.md with `disable-model-invocation: true`, no `allowed-tools` |
| GitHub Copilot / Agent Plugins | `.github/plugin/marketplace.json` → `agent-plugin/plugin.json` | `$schema` `https://agent-plugins.org/schemas/1.0.0/plugin.schema.json`; only schema-allowed fields |
| Antigravity | `antigravity/plugin.json` (`$schema`, `name`, `description` only) + `rules/invocation.md` | skills byte-identical to source |

## Internal CLI contract (current runtime; consumed by L1)

Both CLIs print JSON on stdout and exit 0; on refusal they print `{"status":"BLOCKED","error":…}` or
`BLOCKED: …` to stderr and exit 2. A refusal never changes state.

### `mission_state.py`
| Command | Input | Output |
| --- | --- | --- |
| `init --state P --contract C.json` (legacy) | contract already carrying `approved_by: "human"`, `approval_ref`, `success_criteria`, `delegated_actions`, `max_cycles`, `max_stalled_cycles` | creates an **ACTIVE** ledger directly, bypassing `draft → activate`; refuses if the state file exists |
| `draft --state P --contract C.json [--policy P.json]` | contract with `mission_id`, absolute `workspace`; no `approved_by`/`approval_ref` | state summary (`status: DRAFT`, `proposal_digest`) |
| `apply --state P --event E.json` | event with `id`, `op`, `actor` (`L1`/`L2`/`human`/`host`), `mission_id`, `expected_revision`; cycle ops add `cycle_id`, L2 ops add `session_id` | new summary; same `id` with same content is idempotent, same `id` with different content is refused |
| `show --state P` | — | `schema_version`, `status`, `revision`, `cycle`, counts, `intent_digest`, `proposal_digest`, `runtime_policy_digest` |
| `digest --docs-dir D` | directory containing `handoff.md`, `spec.md`, `plan.md` | 64-hex SHA-256 over the three files in that order |
| `migration-digest --workspace W --paths-file J` | JSON list of relative doc paths incl. `AGENTS.md`, `CLAUDE.md`, `.dryforge/status.json`, ≥1 `docs/*.md` | 64-hex digest |

Supported `op` values: `revise_draft`, `activate`, `runtime_policy`, `amend`, `skill_cancel`,
`start`, `ready`, `approve`, `go`, `bind_runtime`, `bind_tasks`, `rework`, `question`, `answer`,
`result`, `accept`, `close`, `evaluate`, `interrupt`, `resume`, `abort`, `continue`, `observe`.
Status values: `DRAFT`, `ACTIVE`, `PAUSED`, `COMPLETE`. Readable schema versions: 1–5.

### `worker_runtime.py`
| Command | Key inputs | Output |
| --- | --- | --- |
| `doctor --backend claude\|codex` | — | dependency presence; never installs |
| `start` | `--backend`, finite `--turn-seconds/--lifetime-seconds/--startup-seconds/--max-messages/--max-model-turns` (each 1–86400), optional `--budget-usd` (Claude only), `--handoff-ref` (required when replacing a previous worker) | `controller_pid`, `state: STARTING` |
| `status` | — | `session_id`, `state` (`STARTING/IDLE/RUNNING/WAITING/UNREACHABLE/STOPPED/ERROR`), `pending[]` requests each with `delegation` eligibility hint |
| `send --id M --kind probe\|ready\|go\|migration\|message --text-file F [--ledger L --cycle C]` | non-probe kinds require ledger+cycle and an ACTIVE ledger in the matching stage | `{id, state: QUEUED, session_id}`; reuse of `M` with different content is refused |
| `wait --id M --timeout 1..300` | — | message view + worker status; `wait_timed_out: true` on timeout |
| `answer --request-id R --response-file J` | JSON with `principal` (`human`/`L1`), `basis`, `session_id`, `request_digest`, `action` (`answer`/`allow`/`deny`), `answers{}` or `policy_digest` | stored receipt; consumption is re-validated later |
| `result --id M [--full]` | — | `TURN_COMPLETE/TURN_FAILED/REJECTED/CANCELLED/UNCERTAIN` with text (clipped at 8000 chars unless `--full`) |
| `events --after N --limit 1..200 [--full]` | — | event list + `next_cursor` |
| `resume --reconciled --basis TEXT` / `stop` | — | relaunch of the same host session / stop request |

Message size limit 256 KiB; mailbox limit 1000 messages per worker.
