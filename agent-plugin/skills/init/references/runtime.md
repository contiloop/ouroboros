# Run record and worker sessions

All commands: `python3 -B <skill root>/scripts/ouroboros_cli.py --workspace <abs git root>
--owner <pid> <command> …`. The skill root is the directory containing this skill's `SKILL.md`.
`<pid>` is this host process (`$CLAUDE_PID` on Claude Code). Success prints JSON and exits 0; a
refusal prints `{"status":"BLOCKED","error":…}`, exits 2 and changes nothing. The record lives in
the target project's git-ignored `.dryforge/ouroboros/` (`run.json`, `events.jsonl`, the four
documents `scenario.md`, `validation.md`, `spec.md`, `delegation.md`, their copies under `shown/`
and `approved/` (the governing text after `approve`), `interview.md` (the interview log you write
directly; no command writes it), `workgraph.yaml`, `turns/`, `archive/`). Writes refuse while
`.dryforge/` is not ignored there.

| Command | Use |
| --- | --- |
| `doctor --host claude` | `claude` on PATH, its version, `dryforge` plugin installed and enabled |
| `draft --scenario <f> --validation <f> --spec <f> --delegation <f>` | write the four documents (all four for a new run; any subset revises the current DRAFT, ACTIVE or STOPPED run, which must be shown and approved again); a COMPLETE run or a legacy record is archived first and a new run starts (a legacy ACTIVE run must be stopped first) |
| `shown` | mark the current set as shown to the user (keeps copies under `shown/`) |
| `show` | status, `legacy`, combined digest, `content_digest`, limits, models, `effort`, `reviews` (the last `intent` and `gate` entries or null), `stalled_cycles`, `beta_cycles`, session, open cycle, open question |
| `review --kind intent\|gate --findings <file>` | record an independent reviewer's result on the current set: JSON `{"findings": [{"id": "F1", "text": "<verbatim finding>", "disposition": "open\|settled\|technical", "note": "<log entry or what changed>"}]}` (`text` required, `id` and `note` optional); stores `{kind, time, content_digest, log_digest, findings, open}` and a `review` event with the findings; a review passes when `open` is 0; bound to the content digest of `scenario.md` + `validation.md` + `spec.md` (not `delegation.md`); refused with nothing proposed or on a COMPLETE run |
| `approve` | approve exactly the shown set: activates a DRAFT, amends an active or stopped run whose set changed, resumes a stopped run whose set is unchanged. Checks in order: COMPLETE, never shown, changed since shown (prints a diff per changed file), the gate review, completeness (a refusal names the file and the item). The gate is required for a first approval and whenever the content digest differs from the approved copies; then the last `gate` review must match the current content digest with no open finding, else `review the current set` with `reason` `no_gate_review`, `stale` (both digests given) or `open_findings` (the count given). An unchanged resume or a `delegation.md`-only revision needs no gate |
| `cycle-start --kind development\|migration\|beta --goal <file> --checkpoint <commit>` | open a cycle; `beta` runs no worker turns and does not count toward max cycles |
| `cycle-stage --stage ready\|go\|review\|done [--ready-digest <hex>] [--checkpoint <commit>]` | advance it (`go` needs a ready digest) |
| `evaluate --decision CONTINUE\|REPLAN\|ESCALATE\|COMPLETE --basis <file>` | close it; applies limits and amendments; `COMPLETE` only on a beta cycle; `ESCALATE` on a beta cycle is not a stalled cycle; max cycles stops the run when more development is asked for at the limit |
| `event --actor human\|L1\|L2\|host --kind <kind> [--cycle <id>] --data <file>` | record a decision or evidence; kinds used by the loop: `answer` (plain-text questions), `resume`, `beta` (one per validation item), `verified` (the user's own check) |
| `stop --reason abort\|limit:<which>` | set STOPPED |
| `archive` | move a finished run under `archive/<run_id>/` |
| `session-start --skill ready\|go\|migration --message <file> [--fresh --reason <text>]` | launch a detached turn whose message is `/dryforge:<skill> ` + the file text (`go --fresh` is refused once the cycle's Ready ran in a session) |
| `session-send --message <file>` | launch a detached turn on the recorded session with the file text |
| `session-wait [--timeout <s>]` | block until the turn exits or the worker asks a question, then print the parsed result (`QUESTION` carries `round` and `questions`) |
| `session-answer --answers <file> [--basis <file>]` | answer the open question round: JSON object `{"<question text>": "<label>" \| ["<label>", …] \| {"other": "<text>"}}`; records `question` and `answer` events; refuses an unknown question or a non-option answer |
| `session-status` | `RUNNING`, `QUESTION` (with the open question) or the last parsed result, without blocking |
| `session-stop` | terminate the running turn and record it (a turn that already exited is settled instead) |

## The worker process

L2 is a headless `claude` session driven through its streaming control channel, resumed by session
id on every later turn, with its working directory in the target project so the project's own
settings, hooks and deny rules apply to it as to any caller. The models in `delegation.md` are
applied on every turn: the L2 model as the session's model flag, the L3 model as the subagent
model of the worker process (`default` = the host's default). The effort level is applied on every
turn with the session's effort flag (`default` = no flag, the host's default); the effort of the
worker's subagents is not controlled. Its question tool is live: a structured
question arrives as a `QUESTION` result and you answer it with `session-answer`. Tools are
pre-allowed by list (built-in tools plus MCP tools) and any other permission request is allowed
automatically and recorded; the user's deny rules are applied by the host first; no bypass flag is
ever used. Dryforge skills are started by sending `/dryforge:<kind>` as the first words of the
message; the host loads the installed skill. A skill may still ask in plain text; then the turn
ends and your next `session-send` is the answer.

While a question is open, `session-start`/`session-send` are refused (answer or stop first) and
`show` reports the open question under `turn`.

Parsed turn result keys: `state` (`QUESTION`, `COMPLETE`, `INTERRUPTED`, `STOPPED`), `session_id`, `text`,
`questions` (answered rounds), `skills` (the installed `dryforge:` commands the session saw),
`auto_allowed` (permission requests the worker process allowed on its own),
`num_turns`, `cost_usd`, `usage` (`input_tokens`, `cache_read_input_tokens`,
`cache_creation_input_tokens`, `output_tokens`; null when the host did not report one),
`cost_total_usd` (the host's cumulative session total; `cost_usd` is this turn's share of it),
`models`, `effort`, `permission_denials`, `is_error`, `subtype`, `raw_path`, `text_path`, `reason`,
and the run's `run_status` and `stopped_reason` after the turn. The first result that names a
session id records it; a later result with a different id is an `INTERRUPTED` turn. The cost figures
are information only; nothing is charged against a limit.

## Evidence

Keep raw results in `turns/`; put decisions and their basis in events. Acceptance, completion and
recovery rest on actual documents, actual verification output and actual Git state, never on a
worker's self-report or on a turn having ended.
