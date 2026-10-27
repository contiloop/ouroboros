# Run record and worker sessions

All commands: `python3 -B <skill root>/scripts/ouroboros_cli.py --workspace <abs git root>
--owner <pid> <command> …`. The skill root is the directory containing this skill's `SKILL.md`.
`<pid>` is this host process (`$CLAUDE_PID` on Claude Code). Success prints JSON and exits 0; a
refusal prints `{"status":"BLOCKED","error":…}`, exits 2 and changes nothing. The record lives in
the target project's git-ignored `.dryforge/ouroboros/` (`run.json`, `events.jsonl`,
`proposal.md`, `proposal.approved.md` — the governing text after `approve`, `turns/`, `archive/`).
Writes refuse while `.dryforge/` is not ignored there.

| Command | Use |
| --- | --- |
| `doctor --host claude` | `claude` on PATH, its version, `dryforge` plugin installed and enabled |
| `draft --proposal <file>` | create the DRAFT proposal, or revise the proposal of the current DRAFT, ACTIVE or STOPPED run (it must be shown and approved again); a COMPLETE run is archived first and a new run starts |
| `shown` | mark the current proposal as shown to the user |
| `show` | status, digests, limits, spent budget, session, open cycle |
| `approve` | approve exactly the shown proposal: activates a DRAFT, amends an active or stopped run whose proposal changed, resumes a stopped run whose proposal is unchanged |
| `cycle-start --kind development\|migration --goal <file> --checkpoint <commit>` | open a cycle |
| `cycle-stage --stage ready\|go\|review\|done [--ready-digest <hex>] [--checkpoint <commit>]` | advance it (`go` needs a ready digest) |
| `evaluate --decision CONTINUE\|REPLAN\|ESCALATE\|COMPLETE --basis <file>` | close it; applies limits and amendments |
| `event --actor human\|L1\|L2\|host --kind <kind> [--cycle <id>] --data <file>` | record a question, answer, decision or evidence |
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
settings, hooks and deny rules apply to it as to any caller. Its question tool is live: a structured
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
`permission_denials`, `is_error`, `subtype`, `raw_path`, `text_path`, `reason`, and the run's
`run_status` and `stopped_reason` after the turn. The first result that names a session id records
it; a later result with a different id is an `INTERRUPTED` turn. Cost is added to the run's spent
budget once per turn and checked at once: when the budget is exceeded the run is `STOPPED`
(`limit:budget`) and no further turn launches.

## Evidence

Keep raw results in `turns/`; put decisions and their basis in events. Acceptance, completion and
recovery rest on actual documents, actual verification output and actual Git state, never on a
worker's self-report or on a turn having ended.
