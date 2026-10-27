# Contracts

## User-facing commands (the stable contract)

| Host | Command | Input | Effect | Errors |
| --- | --- | --- | --- | --- |
| Claude Code | `/ouroboros:init` | free text about the goal, over any number of turns | starts or continues the proposal conversation; ensures `.dryforge/` is ignored; writes the draft record; never runs a cycle | project without git is reported |
| Codex | `$ouroboros:init` | same | same | same |
| Claude Code | `/ouroboros:approve` | none | approves the proposal exactly as last shown and starts L1's loop in the session; conversation stays open | no proposal → "nothing proposed"; changed since shown → the difference is shown, nothing approved |
| Codex | `$ouroboros:approve` | none | reports that no Codex worker adapter exists; records nothing | — |

Any later message to L1 is conversation: in-scope clarification, a proposal revision (approved
again with `approve`, applied between cycles) or a request to stop (immediate abort).

All skills are manual-only on every host (`disable-model-invocation: true` for Claude/Grok/Agent
Plugins, `allow_implicit_invocation: false` for Codex, `rules/invocation.md` for Antigravity).

## Host-facing packaging contract

| Consumer | Reads | Must hold |
| --- | --- | --- |
| Claude Code | `.claude-plugin/marketplace.json` → `claude/.claude-plugin/plugin.json`, `claude/skills/*/SKILL.md` | frontmatter `name`, `description`, `allowed-tools`, `disable-model-invocation: true` |
| Codex (current) | `.agents/plugins/marketplace.json` → `codex/plugin/plugin.json` (Agent Plugins 1.0, `extensions.com.openai.interface`) | `skills/*/SKILL.md` + `skills/*/agents/openai.yaml` with `interface` and `policy.allow_implicit_invocation: false` |
| Codex (older) | `codex/plugin/.codex-plugin/plugin.json` | identical identity/interface to the root manifest; `"skills": "./skills/"` |
| Grok | `.grok-plugin/marketplace.json` → `grok/plugin.json` | SKILL.md with `disable-model-invocation: true`, no `allowed-tools` |
| GitHub Copilot / Agent Plugins | `.github/plugin/marketplace.json` → `agent-plugin/plugin.json` | `$schema` `https://agent-plugins.org/schemas/1.0.0/plugin.schema.json`; only schema-allowed fields |
| Antigravity | `antigravity/plugin.json` (`$schema`, `name`, `description` only) + `rules/invocation.md` | skills byte-identical to source |

## Internal CLI contract (`ouroboros_cli.py`, consumed by L1)

`python3 -B <skill root>/scripts/ouroboros_cli.py --workspace <abs git root> --owner <pid> <command> …`.
`--owner` is the pid of the L1 host process (`$CLAUDE_PID`), never the CLI's own pid. Success prints
JSON and exits 0; a refusal prints `{"status":"BLOCKED","error":…,…details}` and exits 2 without
changing state. Every write runs inside one file lock and requires `.dryforge/` to be git-ignored in
the workspace.

| Command | Arguments | Effect |
| --- | --- | --- |
| `doctor` | `--host claude` | `{host, claude: path\|null, version, dryforge: {installed, enabled}}`; never exit 2 for a missing host |
| `draft` | `--proposal <file>` | DRAFT, ACTIVE or STOPPED → replaces `proposal.md` of the current run, clears the shown digest and copy, appends `draft` (the revision must be shown and approved again); COMPLETE → archives the run first and starts a new DRAFT; refuses a live foreign owner |
| `shown` | — | records the digest of `proposal.md` as shown; keeps a copy (`proposal.shown.md`) for diffs |
| `show` | — | summary: status, run_id, shown and current digests, limits, spent, session, open cycle, `stopped_at` |
| `approve` | — | writes `proposal.approved.md` (the governing text L1 re-reads) on every activation, amendment or resume; no proposal → BLOCKED "nothing proposed"; digest ≠ shown → BLOCKED with both digests and a unified diff; DRAFT → ACTIVE + first approval (`activated`); ACTIVE same digest → no-op summary; STOPPED same digest → `resumed`: an approval entry is appended, status ACTIVE, `stopped_reason`/`stopped_at` cleared; ACTIVE/STOPPED with a newer shown digest → `amended`: amendment appended, status ACTIVE. Refuses a proposal missing a required section or a parsable `Limits` section |
| `cycle-start` | `--kind migration\|development --goal <file> --checkpoint <commit>` | opens `c<n>`; refuses unless ACTIVE, no open cycle and no limit already reached; emits pending `amend_applied` |
| `cycle-stage` | `--stage ready\|go\|review\|done [--ready-digest <hex>] [--checkpoint <commit>]` | advances the open cycle; `go` requires a ready digest; `--checkpoint` sets `checkpoint_after` |
| `evaluate` | `--decision CONTINUE\|REPLAN\|ESCALATE\|COMPLETE --basis <file>` | closes the cycle; REPLAN/ESCALATE count as stalled; COMPLETE needs a non-empty basis and sets the run COMPLETE; limits reached → STOPPED `limit:cycles\|stalled\|budget` |
| `event` | `--actor human\|L1\|L2\|host --kind <kind> [--cycle <id>] --data <file>` | appends one event; JSON ≤ 8 KB embedded, otherwise copied to `turns/event-<n>.<ext>` |
| `stop` | `--reason abort\|limit:<which>` | STOPPED with `stopped_at` {cycle, stage, checkpoint}; the open cycle stays open |
| `archive` | — | moves a finished run under `archive/<run_id>/` |
| `session-start` | `--skill ready\|go\|migration --message <file> [--fresh --reason <text>]` | detached turn; message = `/dryforge:<skill> ` + file text; `--resume` of the recorded session unless `--fresh`; refused while a limit is exceeded, and `go --fresh` is refused while the open cycle has a recorded `session_id` (Ready ran there) |
| `session-send` | `--message <file>` | detached `--resume` turn with the file text; refused while a limit is exceeded |
| `session-wait` | `[--timeout <s>]` | blocks until the turn exits **or the worker asks a structured question**; prints the parsed result, `{state: QUESTION, round, questions}` for an open question, or `{state: RUNNING, waited}` on timeout |
| `session-answer` | `--answers <file> [--basis <file>]` | answers the open question round: JSON object `{"<question text>": "<label>" \| ["<label>", …] (multiSelect) \| {"other": "<text>"}}`; every question must be answered, an unknown question or a non-option answer is BLOCKED; writes `turns/<n>.a<k>.json`, records `question` (L2) and `answer` (L1) events, turn back to RUNNING |
| `session-status` | — | `{state: RUNNING, pid, turn}`, `{state: QUESTION, …}` or the parsed result; never blocks |
| `session-stop` | — | SIGTERM the process group (outside the record lock), SIGKILL after 5 s; turn `STOPPED`; a turn that has already exited is settled like `session-status` instead |

**Worker process and channel.** Each turn runs `claude -p --input-format stream-json --output-format
stream-json --verbose --permission-prompt-tool stdio [--resume <id>] --allowedTools … --max-turns N`
under a relay (`ouroboros/relay.py`) that holds its stdin/stdout, sends the message, mirrors every
event to `turns/<n>.stream.jsonl`, writes `turns/<n>.init.json` (session id, slash commands),
`turns/<n>.q<k>.json` for each structured question round, forwards `turns/<n>.a<k>.json` as the
answer, allows any other permission request automatically (listed in `turns/<n>.auto.json`), and
writes the final result to `turns/<n>.json`. `session-start`/`session-send` are refused while a
question is open. Turn states: `RUNNING`, `QUESTION`, `COMPLETE`, `INTERRUPTED`, `STOPPED`.

**Parsed turn result:** `state` (`QUESTION` | `COMPLETE` | `INTERRUPTED` | `STOPPED`), `session_id`, `text`,
`questions` (answered rounds), `skills` (the `dryforge:` commands the session saw), `auto_allowed[]`
({tool_name, tool_use_id}), `stream_path`,
`num_turns`, `cost_usd` (this turn's charge), `cost_total_usd` (the host's cumulative total for the
session, as reported), `usage` (`input_tokens`, `cache_read_input_tokens`,
`cache_creation_input_tokens`, `output_tokens`; a count the host did not report is null),
`permission_denials`, `is_error`, `subtype`, `raw_path`, `stderr_path`, `exit_code`, `text_path`,
`reason`, `turn`, `pid`, `kind`, plus `run_status` and `stopped_reason` of the run after the turn.
INTERRUPTED covers non-zero exit, empty or non-JSON output, a missing session id, `is_error`, or a
session id that differs from the recorded one. Any turn that names a session id binds it when none
is recorded yet (an INTERRUPTED first turn included). The host reports `total_cost_usd` cumulatively
over a resumed session, so `cost_usd` is the delta against `session.cost_total_usd` (the last total
seen for the session; 0 for a fresh session; a smaller total than before is charged in full and
becomes the new baseline). `cost_usd` is added to `spent_usd` once per turn; when the sum then
exceeds `budget_usd` the run is set STOPPED `limit:budget` (a `stop` event, actor L1) and the result
shows `run_status: STOPPED`. `session-stop` records its `stop` event with actor L1 (it is L1's
action); only the run-level `stop --reason abort` is the human's.

**Run record (`run.json`):** `run_id`, `workspace`, `status` ∈ {DRAFT, ACTIVE, COMPLETE, STOPPED},
`proposal_digest_shown`, `approvals[] {time, digest, applied}`, `limits {max_cycles,
max_stalled_cycles, budget_usd|null}`, `spent_usd`, `stalled_cycles`, `host`, `session {id, started,
reason, cost_total_usd}`, `cycles[] {id, goal, kind, started, session_id, stage, checkpoint_before, checkpoint_after,
ready_digest, evaluation}`, `stopped_reason`, `stopped_at`, `turn_count`, `turn`.
**Events (`events.jsonl`):** `{time, actor, kind, cycle_id, data}`; kinds written by the CLI:
`draft`, `shown`, `approve`, `amend`, `amend_applied`, `cycle_start`, `cycle_stage`, `evaluate`,
`stop`, `archive`, `session`, `turn`, `turn_result`, `interrupt`, plus whatever L1 records with `event`.
**Owner (`owner.json`):** `{pid, session_id, started}`; a live foreign pid blocks `draft`, `approve`
and every `session-*` command; a dead pid is replaced.
