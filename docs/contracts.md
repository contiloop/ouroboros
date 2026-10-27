# Contracts

## User-facing commands (the stable contract)

| Host | Command | Input | Effect | Errors |
| --- | --- | --- | --- | --- |
| Claude Code | `/ouroboros:init` | free text about the goal, over any number of turns | starts or continues the client interview that fills `scenario.md`, `validation.md`, `spec.md`, `delegation.md` (English), keeps the interview log, runs the two independent reviews and records them; ensures `.dryforge/` is ignored; writes the draft record; never runs a cycle | project without git is reported |
| Codex | `$ouroboros:init` | same | same | same |
| Claude Code | `/ouroboros:approve` | none | requires a passing gate review on the shown content, checks the set is complete, approves it exactly as last shown and starts L1's loop in the session; conversation stays open | no passing gate review on this content → `review the current set`; incomplete → the missing file and item; nothing proposed → "nothing proposed"; changed since shown → the difference per file is shown, nothing approved |
| Codex | `$ouroboros:approve` | none | reports that no Codex worker adapter exists; records nothing | — |

Any later message to L1 is conversation: in-scope clarification, a revision of the set (approved
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
| `draft` | `--scenario <f> --validation <f> --spec <f> --delegation <f>` | new run: all four required; DRAFT, ACTIVE or STOPPED → any subset replaces those files of the current run, clears the shown digest and the `shown/` copies, appends `draft` (the revision must be shown and approved again); COMPLETE, or a legacy record (single `proposal.md`) that is DRAFT/COMPLETE/STOPPED → archived first and a new DRAFT starts; legacy ACTIVE → BLOCKED "stop it first"; refuses a live foreign owner |
| `shown` | — | records the combined digest of the four files as shown (`core.set_digest`: SHA-256 over `<name>\n<byte length>\n<bytes>` per file in the order scenario, validation, spec, delegation); keeps copies under `shown/` |
| `show` | — | summary: status, run_id, `legacy`, shown and current combined digests, limits, `models {l2, l3}`, `effort`, `content_digest`, `reviews {intent, gate}` (last entry of each or null), `beta_cycles`, session, open cycle, `stopped_at`, open question |
| `approve` | — | order of checks: COMPLETE run → BLOCKED; never shown → BLOCKED; digest ≠ shown → BLOCKED with both digests, `changed[]` and a unified diff per changed file; gate review (below) → BLOCKED `review the current set` with `reason` `no_gate_review` \| `stale` (reviewed and current content digests) \| `open_findings` (count); completeness → BLOCKED `<file>: <item>`; then: DRAFT → ACTIVE + first approval (`activated`); ACTIVE same digest → no-op summary; STOPPED same digest → `resumed`; ACTIVE/STOPPED with a newer shown digest → `amended`. On success writes the approved copies under `approved/` (the governing text L1 re-reads) and stores `limits`, `models` and `effort` from `delegation.md`. The gate review is required for a DRAFT and whenever the content digest (scenario, validation, spec) differs from that of `approved/` (missing copies count as different); not for an unchanged resume or a `delegation.md`-only change |
| `review` | `--kind intent\|gate --findings <file>` | records a reviewer's result: the JSON `{"findings": [{"id", "text", "disposition": "open\|settled\|technical", "note"}]}` (`text` required); appends `reviews[] {kind, time, content_digest, log_digest, findings, open}` to `run.json` and a `review` event (actor L1) with the verbatim list under `items`; pass = `open` 0; refused when nothing is proposed, on a legacy or COMPLETE record, under a live foreign owner, or on malformed findings |
| `cycle-start` | `--kind migration\|development\|beta --goal <file> --checkpoint <commit>` | opens `c<n>`; refuses unless ACTIVE and no cycle is open; a development cycle also refuses at the cycles limit; a beta cycle is exempt from `max cycles` and increments `beta_cycles`; emits pending `amend_applied` |
| `cycle-stage` | `--stage ready\|go\|review\|done [--ready-digest <hex>] [--checkpoint <commit>]` | advances the open cycle; `go` requires a ready digest; `--checkpoint` sets `checkpoint_after` |
| `evaluate` | `--decision CONTINUE\|REPLAN\|ESCALATE\|COMPLETE --basis <file>` | closes the cycle; REPLAN counts as stalled, ESCALATE too except on a beta cycle; COMPLETE needs a non-empty basis, is accepted only on a beta cycle and sets the run COMPLETE; stalled limit reached → STOPPED; the cycles limit stops the run only when more development is asked for (REPLAN anywhere, ESCALATE on a development cycle) — after a CONTINUE at the limit the run stays ACTIVE so a beta cycle can open |
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
stream-json --verbose --permission-prompt-tool stdio [--resume <id>] --allowedTools … --max-turns N [--model <l2>] [--effort <level>]`
under a relay (`ouroboros/relay.py`) that holds its stdin/stdout, sends the message, mirrors every
event to `turns/<n>.stream.jsonl`, writes `turns/<n>.init.json` (session id, slash commands),
`turns/<n>.q<k>.json` for each structured question round, forwards `turns/<n>.a<k>.json` as the
answer, allows any other permission request automatically (listed in `turns/<n>.auto.json`), and
writes the final result to `turns/<n>.json`. `session-start`/`session-send` are refused while a
question is open. Turn states: `RUNNING`, `QUESTION`, `COMPLETE`, `INTERRUPTED`, `STOPPED`.

**Parsed turn result:** `state` (`QUESTION` | `COMPLETE` | `INTERRUPTED` | `STOPPED`), `session_id`, `text`,
`questions` (answered rounds), `skills` (the `dryforge:` commands the session saw), `auto_allowed[]`
({tool_name, tool_use_id}), `stream_path`,
`num_turns`, `cost_usd` (this turn's share, information only), `cost_total_usd` (the host's cumulative total for the
session, as reported), `usage` (`input_tokens`, `cache_read_input_tokens`,
`cache_creation_input_tokens`, `output_tokens`; a count the host did not report is null),
`permission_denials`, `is_error`, `subtype`, `raw_path`, `stderr_path`, `exit_code`, `text_path`,
`reason`, `turn`, `pid`, `kind`, `models`, `effort`, plus `run_status` and `stopped_reason` of the run after the turn.
INTERRUPTED covers non-zero exit, empty or non-JSON output, a missing session id, `is_error`, or a
session id that differs from the recorded one. Any turn that names a session id binds it when none
is recorded yet (an INTERRUPTED first turn included). The host reports `total_cost_usd` cumulatively
over a resumed session, so `cost_usd` is the delta against `session.cost_total_usd` (the last total
seen for the session; 0 for a fresh session; a smaller total than before counts in full and
becomes the new baseline). Cost is information only; nothing acts on it. `session-stop` records its `stop` event with actor L1 (it is L1's
action); only the run-level `stop --reason abort` is the human's.

**Run record (`run.json`):** `run_id`, `workspace`, `status` ∈ {DRAFT, ACTIVE, COMPLETE, STOPPED},
`proposal_digest_shown` (combined set digest), `approvals[] {time, digest, applied}`, `limits {max_cycles,
max_stalled_cycles}`, `models {l2, l3}` and `effort` (literal strings, `default` for the host
default; `effort` ∈ default, low, medium, high, xhigh, max), `reviews[] {kind, time, content_digest,
log_digest, findings, open}`, `beta_cycles`, `stalled_cycles`, `host`, `session {id, started,
reason, cost_total_usd}`, `cycles[] {id, goal, kind, started, session_id, stage, checkpoint_before, checkpoint_after,
ready_digest, evaluation}`, `stopped_reason`, `stopped_at`, `turn_count`, `turn`.
**Events (`events.jsonl`):** `{time, actor, kind, cycle_id, data}`; kinds written by the CLI:
`draft`, `shown`, `approve`, `amend`, `amend_applied`, `cycle_start`, `cycle_stage`, `evaluate`,
`stop`, `archive`, `review`, `session`, `turn`, `turn_result`, `interrupt`, `question`, `answer`, `unanswered`,
plus whatever L1 records with `event` — the loop uses `beta` (one per validation item, actor L1),
`verified` (the user's own check, actor human), `answer` (plain-text questions) and `resume`.
**Files:** the four documents, `interview.md` (L1's private interview log, moved with the run on archive), `shown/<name>`, `approved/<name>`, `workgraph.yaml` (L1's plan of
nodes; the only file L1 edits on its own after approval), `run.json`, `events.jsonl`, `turns/`,
`archive/<run_id>/`, `owner.json`, `lock`.
**Owner (`owner.json`):** `{pid, session_id, started}`; a live foreign pid blocks `draft`, `approve`
and every `session-*` command; a dead pid is replaced.
