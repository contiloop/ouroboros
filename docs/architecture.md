# Architecture

Ouroboros is a repository of **skill text plus a small Python runtime**, packaged for several
coding-agent hosts. There is no server, database service or network listener. Everything runs inside
the user's host session (Claude Code or Codex) or as a local same-user subprocess.

## Repository topology

```
src/skills/            canonical skills (single source of truth)
   ├── init/           L1 entry: SKILL.md + references/ + scripts/ (the Python runtime lives here)
   ├── approve/        L1 handoff entry (text only; reuses init's references and scripts)
   ├── ready/ go/ migration/   bundled Dryforge-derived copies (legacy; slated for removal)
platform/<host>/       per-host manifest and overlay inputs (not skills)
build/build.sh         copies src/skills + platform inputs → five generated packages
claude/  codex/plugin/  grok/  agent-plugin/  antigravity/   generated packages, committed
.claude-plugin/ .agents/plugins/ .grok-plugin/ .github/plugin/   marketplace manifests pointing at the packages
ci/                    unittest suite + verify.py (consistency and reproducible build)
docs/                  project documentation and the older product docs MISSION.md, RUNTIME_POLICY.md, RESEARCH_MCP_SETUP.md
```

Dependency direction is strictly `src/skills` → generated packages. Nothing reads from a generated
package except the host that installs it and `ci/verify.py`, which compares packages back to the
source. Hosts discover the plugin through a marketplace manifest at the repository root, which points
at the matching generated package directory.

## Runtime components (current implementation)

All runtime code sits under `src/skills/init/scripts/` and is copied verbatim into every package.
It is standard-library Python 3.11+ with one optional third-party dependency.

| Component | Role | Depends on |
| --- | --- | --- |
| `mission_state.py` | Append-only JSON ledger of the user's intent, approval, cycles, decisions and runtime grants. Pure state machine with a CLI (`draft`, `apply`, `show`, `digest`, `migration-digest`, and the legacy `init` that creates an ACTIVE ledger directly). | `runtime_permissions`, `runtime_cycle`, `migration_artifacts` (lazy imports for validation) |
| `worker_runtime.py` | CLI controller for an external L2 session: `start/resume/stop/status/send/answer/wait/events`. Spawns a detached `__serve` process per worker. | `runtime_bridge` |
| `runtime_bridge/store.py` | SQLite mailbox (`messages`, `requests`, `events`, `workers`) under `.dryforge/mission/runtime/`. Idempotent message IDs, single-controller OS lock, record/consume double check of delegated answers. | sqlite3, fcntl |
| `runtime_bridge/controller.py` | The serve loop: claims queued messages, re-validates ledger binding at dispatch, forwards to the host adapter, relays questions/permissions back as pending requests, records the `go` event immediately before sending Go. | `store`, `adapters`, `mission_state`, `runtime_permissions` |
| `runtime_bridge/adapters.py` | Host transports. `ClaudeAdapter` drives `claude-agent-sdk` (resume by session ID, hooks, `can_use_tool` callback). `CodexAdapter` speaks newline-JSON-RPC to `codex app-server --listen stdio://` (thread/turn lifecycle, child-thread tracking, `skills/list` resolution). | `store` |
| `runtime_permissions.py`, `runtime_git.py`, `runtime_cycle.py`, `runtime_merge.py` | Classifier for delegated tool requests: maps a host callback (Claude tool input or Codex approval request) to one named operation and an observed scope, validated against a human-granted policy object (versions 1–4) and real Git state (worktree registration, index digest, branch ancestry). | git CLI |
| `migration_artifacts.py` | Which paths count as documentation for a delegated Migration and how to digest them. | — |

### Representative flow: one cycle through the external runtime

```
L1 (host session)                controller (__serve)                 host adapter            L2
 │ worker_runtime start ──────▶ create worker row, spawn serve ──▶ connect (SDK / app-server) ─▶ session id
 │ mission_state apply start    bind real session id
 │ worker_runtime send --kind ready --ledger … --cycle c1
 │                              validate binding (ACTIVE, stage, same session)
 │                              resolve installed skill (slash_commands / skills/list)
 │                              prompt = "/dryforge:ready <goal>" or "$dryforge:ready" + skill input
 │                              ──────────────────────────────────▶ run turn ───────────────▶ Ready
 │ wait --id … ◀── pending request (question / permission) ◀── relay() ◀── can_use_tool / requestApproval
 │ answer --request-id … (principal L1 or human, basis) ─▶ store.answer → take_answer rechecks → host resumes
 │ result --id … ◀── TURN_COMPLETE (text, session id)
 │ mission_state apply ready/approve (digest of handoff.md+spec.md+plan.md)
 │ send --kind go  ── controller re-validates docs digest, records `go` event, then dispatches
```

The ledger (`state.json`) and the mailbox (`mailbox.sqlite3`) are the only persistent state; both
live under the target project's git-ignored `.dryforge/mission/`. Nothing is written into the
Ouroboros repository at runtime.

### Native path

When the host itself can hold a persistent L2 session (Claude Code subagents, Codex native
threads), L1 may skip `worker_runtime.py` entirely and drive Dryforge through the host's own
mechanism. The ledger is still the record of intent and decisions in that case.

## Packaging topology

`build/build.sh` produces each package from the same `src/skills` tree:

| Package | Added by build | Installed how |
| --- | --- | --- |
| `claude/` | `disable-model-invocation: true` + per-skill `allowed-tools` injected into SKILL.md frontmatter; `.claude-plugin/plugin.json` | `claude --plugin-dir ./claude`, or marketplace `.claude-plugin/marketplace.json` |
| `codex/plugin/` | `agents/openai.yaml` overlay per skill; root `plugin.json` (Agent Plugins 1.0 with `extensions["com.openai"]`) plus `.codex-plugin/plugin.json` compatibility overlay | marketplace `.agents/plugins/marketplace.json` |
| `grok/` | `disable-model-invocation: true` only | `.grok-plugin/marketplace.json` |
| `agent-plugin/` | `disable-model-invocation: true` only; Agent Plugins 1.0 manifest | `.github/plugin/marketplace.json` |
| `antigravity/` | byte-identical skills + `rules/invocation.md` manual-only rule | manifest with `$schema`, `name`, `description` only |

Only Claude Code and Codex are supported execution hosts. The other three packages are produced
for format compatibility; nothing in the runtime targets them.

## External dependencies

| Dependency | Used by | Required? |
| --- | --- | --- |
| git ≥ any modern version | runtime (workspace must be a git root), verify.py, Dryforge itself | yes |
| Python 3.11+ (POSIX) | all scripts, tests | yes |
| Installed Dryforge plugin on the L2 host | every cycle | yes |
| `claude-agent-sdk==0.2.173` | `ClaudeAdapter` only | optional, user-installed |
| `codex` CLI with `app-server` | `CodexAdapter` only | optional, user-installed |
| Grep MCP, Context7 MCP | Dryforge's research stage | optional |
