# Run record and worker sessions

All commands: `python3 -B <skill root>/scripts/ouroboros_cli.py --workspace <abs git root>
--owner <pid> <command> …`. The skill root is the directory containing this skill's `SKILL.md`.
`<pid>` is this host process (`$CLAUDE_PID` on Claude Code). Success prints JSON and exits 0; a
refusal prints `{"status":"BLOCKED","error":…}`, exits 2 and changes nothing. The record lives in
the target project's git-ignored `.dryforge/ouroboros/` (`run.json`, `events.jsonl`,
`proposal.md`, `turns/`, `archive/`). Writes refuse while `.dryforge/` is not ignored there.

| Command | Use |
| --- | --- |
| `doctor --host claude` | `claude` on PATH, its version, `dryforge` plugin installed and enabled |
| `draft --proposal <file>` | create or replace the DRAFT proposal (archives a finished run first; refuses on ACTIVE) |
| `shown` | mark the current proposal as shown to the user |
| `show` | status, digests, limits, spent budget, session, open cycle |
| `approve` | approve exactly the shown proposal; amendment on an active or stopped run |
| `cycle-start --kind development\|migration --goal <file> --checkpoint <commit>` | open a cycle |
| `cycle-stage --stage ready\|go\|review\|done [--ready-digest <hex>] [--checkpoint <commit>]` | advance it (`go` needs a ready digest) |
| `evaluate --decision CONTINUE\|REPLAN\|ESCALATE\|COMPLETE --basis <file>` | close it; applies limits and amendments |
| `event --actor human\|L1\|L2\|host --kind <kind> [--cycle <id>] --data <file>` | record a question, answer, decision or evidence |
| `stop --reason abort\|limit:<which>` | set STOPPED |
| `archive` | move a finished run under `archive/<run_id>/` |
| `session-start --skill ready\|go\|migration --message <file> [--fresh --reason <text>]` | launch a detached turn whose message is `/dryforge:<skill> ` + the file text |
| `session-send --message <file>` | launch a detached turn on the recorded session with the file text |
| `session-wait [--timeout <s>]` | block until the turn exits, then print the parsed result |
| `session-status` | `RUNNING` or the last parsed result, without blocking |
| `session-stop` | terminate the running turn and record it |

## The worker process

L2 is `claude -p <message> --output-format json`, resumed by session id on every later turn, with
its working directory in the target project so the project's own settings, hooks and deny rules
apply to it as to any caller. Every tool is pre-allowed by list (built-in tools plus MCP tools);
no bypass flag is ever used. Dryforge skills are started by sending `/dryforge:<kind>` as the
first words of the message; the host loads the installed skill. Without a question tool the skill
asks in plain text and the turn ends; your next `session-send` is the answer.

Parsed turn result keys: `state` (`COMPLETE`, `INTERRUPTED`, `STOPPED`), `session_id`, `text`,
`num_turns`, `cost_usd`, `permission_denials`, `is_error`, `subtype`, `raw_path`, `text_path`,
`reason`. The first result records the session id; a later result with a different id is an
`INTERRUPTED` turn. Cost is added to the run's spent budget once per turn.

## Evidence

Keep raw results in `turns/`; put decisions and their basis in events. Acceptance, completion and
recovery rest on actual documents, actual verification output and actual Git state, never on a
worker's self-report or on a turn having ended.
