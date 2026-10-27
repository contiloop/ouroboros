# Architecture

Ouroboros is a repository of **skill text plus a small Python runtime**, packaged for several
coding-agent hosts. There is no server, database service or network listener. Everything runs inside
the user's host session (Claude Code) or as a local same-user subprocess that it starts.

## Repository topology

```
src/skills/            canonical skills (single source of truth)
   ├── init/           L1 entry: SKILL.md + references/ (interview, orchestration, runtime) + scripts/ (the runtime)
   └── approve/        L1 handoff entry (text only; reuses init's references and scripts)
platform/<host>/       per-host manifest and overlay inputs (not skills)
build/build.sh         copies src/skills + platform inputs → five generated packages
claude/  codex/plugin/  grok/  agent-plugin/  antigravity/   generated packages, committed
.claude-plugin/ .agents/plugins/ .grok-plugin/ .github/plugin/   marketplace manifests pointing at the packages
ci/                    unittest suite + verify.py (consistency and reproducible build)
docs/                  project documentation for agents and RESEARCH_MCP_SETUP.md
```

Dependency direction is strictly `src/skills` → generated packages. Nothing reads from a generated
package except the host that installs it and `ci/verify.py`, which compares packages back to the
source. Hosts discover the plugin through a marketplace manifest at the repository root.

## Runtime components

All runtime code sits under `src/skills/init/scripts/` and is copied verbatim into every package.
It is standard-library Python 3.11+ (POSIX), structured as ports and adapters:

| Component | Role | Depends on |
| --- | --- | --- |
| `ouroboros_cli.py` | The one entry point L1 calls. Sixteen commands: record (doctor, draft, shown, show, approve, cycle-start, cycle-stage, evaluate, event, stop, archive) and session (start, send, wait, status, stop); JSON on stdout, `BLOCKED` + exit 2 on refusal, a refusal never changes state. Every command takes `--workspace` and `--owner`. | `ouroboros.core`, `ouroboros.store`, `ouroboros.adapters` |
| `ouroboros/core.py` | Pure rules over the run record: proposal parsing (required sections, limits), shown/approve/amend digest rules, cycle open/stage/evaluate, stalled and limit accounting, stop, summary. Functions take a record and return a new one; nothing touches disk. | — |
| `ouroboros/store.py` | The private directory `<workspace>/.dryforge/ouroboros/`: 0700/0600 modes, the `git check-ignore` guard, the transactional `fcntl` lock, the owner record, `events.jsonl` appends, payload spill to `turns/`, archive of finished runs. | git CLI |
| `ouroboros/ports.py` | `HostSession` protocol (`start`, `send`, `alive`, `terminate`, `result`, `doctor`) and the `Turn` value (pid + raw output path). The only thing the CLI knows about a host. | — |
| `ouroboros/adapters/claude.py` | The Claude Code implementation: builds `claude -p … --output-format json [--resume id] --allowedTools … --max-turns N`, launches it detached through `/bin/sh` so the exit code survives, parses the JSON result, terminates a process group, parses `claude plugin list` for `doctor`. Tunables are module constants. | `claude` CLI |
| `ouroboros/adapters/__init__.py` | `for_host(name)` lookup; `claude` is the only host today. | — |

### One cycle through the runtime

```
L1 (user's Claude Code session)                      ouroboros_cli.py                      claude -p (L2, detached)
 │ cycle-start --kind development …        ──▶ run.json: cycle c1 open, stage ready
 │ session-start --skill ready --message m ──▶ launch `/dryforge:ready <m>` [--resume id] ──▶ turns/1.json, 1.err, 1.exit
 │ session-wait  (run as a background shell command; L1 ends its turn)
 │   ◀── parsed result {state, session_id, text, cost_usd, permission_denials} ◀── process exit
 │ session-send --message answer           ──▶ `--resume <id>` turn 2 …
 │ cycle-stage --stage go --ready-digest d ──▶ run.json
 │ session-start --skill go --message m    ──▶ `/dryforge:go <m>` in the same session
 │ cycle-stage --stage review --checkpoint c; evaluate --decision CONTINUE --basis b
```

The record (`run.json`, `events.jsonl`, `turns/`) is the only persistent state and lives under the
target project's git-ignored `.dryforge/ouroboros/`. Nothing is written into the Ouroboros
repository at runtime, and the legacy `.dryforge/mission/` directory is never read.

### Why a headless process and not a subagent

Installed Dryforge skills are user-invocable only; a Claude Code subagent cannot see them and has no
question tool. A headless `claude -p` process receives `/dryforge:<kind>` as its user message, so the
host loads the real skill, and `--resume` keeps one session across Ready, Go and later cycles
(decision 0008).

## Packaging topology

`build/build.sh` produces each package from the same `src/skills` tree:

| Package | Added by build | Installed how |
| --- | --- | --- |
| `claude/` | `disable-model-invocation: true` + per-skill `allowed-tools` injected into SKILL.md frontmatter; `.claude-plugin/plugin.json` | `claude --plugin-dir ./claude`, or marketplace `.claude-plugin/marketplace.json` |
| `codex/plugin/` | `agents/openai.yaml` overlay per skill; root `plugin.json` (Agent Plugins 1.0 with `extensions["com.openai"]`) plus `.codex-plugin/plugin.json` compatibility overlay | marketplace `.agents/plugins/marketplace.json` |
| `grok/` | `disable-model-invocation: true` only | `.grok-plugin/marketplace.json` |
| `agent-plugin/` | `disable-model-invocation: true` only; Agent Plugins 1.0 manifest | `.github/plugin/marketplace.json` |
| `antigravity/` | byte-identical skills + `rules/invocation.md` manual-only rule | manifest with `$schema`, `name`, `description` only |

Claude Code is the only execution host with an adapter. The Codex package installs and its `init`
works (it only writes the draft), but `approve` reports the missing adapter. The other three packages
are produced for format compatibility only.

## External dependencies

| Dependency | Used by | Required? |
| --- | --- | --- |
| git | runtime (workspace must be a git root with `.dryforge/` ignored), verify.py, Dryforge itself | yes |
| Python 3.11+ (POSIX `fcntl`) | all scripts, tests | yes |
| `claude` CLI 2.1+ with the Dryforge plugin installed and enabled | every cycle (checked by `doctor`) | yes, on the execution host |
| Grep MCP, Context7 MCP | Dryforge's research stage inside L2 | optional |
