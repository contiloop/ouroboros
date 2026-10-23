# Dryforge — experimental mission/session fork

This fork preserves Dryforge ready/go and adds an opt-in three-level intent-driven harness:

```text
Human <-> L1 Mission Orchestrator
             -> L2 persistent ready -> approval -> go -> evidence/checkpoint
                    -> L3 researchers, implementers, independent reviewers
             <- evaluate -> reuse L2 or spawn a new L2 for the next cycle
```

L2 owns one cycle at a time, not an autonomous sector loop. Ready and go keep the **same session**.
L1 owns the next cycle and final intent. L3 may resume same-task fixes when its checkpoint and
context still match; independent review never reuses the implementer's conversation.

**Experimental:** this is a skill plus a tested local ledger, not a bundled SDK daemon. A capable
host must provide actual session creation/resume, question relay, nested agents, permissions and
budget enforcement. No global hooks are installed. Live multi-agent acceptance is still required.
Stop/yield notifications are not approvals or proof that a cycle succeeded.

## Test this fork

The changes live on `feature/mission-session-orchestration`, not upstream `main`.

```sh
git clone --branch feature/mission-session-orchestration --single-branch \
  https://github.com/contiloop/dryforge.git ~/dryforge-mission
# From your actual project directory, with Claude Code installed:
claude --plugin-dir ~/dryforge-mission/claude
```

Explicitly invoke `/mission` (or `/dryforge:mission`); begin by approving your goal, decision
boundaries and finite limits. Do not run mission until its host preflight passes. Ordinary
`/ready`, `/go`, and `/migration` remain usable. Codex packages include `$mission`; use your
client's supported local marketplace installation rather than assuming an upstream update
contains this branch. Avoid simultaneously enabling two dryforge plugins with colliding names.

**Recommended (Optional):** [Grep MCP](https://mcp.grep.app) for public code search and
[Context7 MCP](https://mcp.context7.com/mcp) for library/API docs. Both are optional, configured
in the host, and checked for actual L2/L3 access. No automatic install or authentication.
See [research MCP setup](docs/RESEARCH_MCP_SETUP.md).

## Guides and source

- [Mission guide, ledger and verification limits](docs/MISSION.md)
- [Korean README](README_ko.md)
- [Original upstream overview](https://github.com/prekuter/dryforge)
- [Preserved upstream README text](README.upstream.md)

The canonical source is `src/skills/`. Ready/go entrypoints force-load their preserved
`references/workflow.md`; mission/session additions are separate. Generated packages for Claude,
Codex, Grok, Agent Plugins and Antigravity are committed after build. Migration initializes a
project harness, not a replacement agent's memory. New workers use explicit checkpoint handoff.

## Development checks

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s ci -p 'test_*.py'
bash build/build.sh
# After committing generated outputs, the reproducibility check requires a clean tree:
python3 ci/verify.py
```

Tests cover state transitions and packaged contracts, not live Claude/Codex behavior. The local
ledger is not an authentication boundary: only a trusted controller may submit approval events.
See the [mission guide](docs/MISSION.md) before attempting unattended execution.

Original Dryforge by prekuter. Apache-2.0; [LICENSE](LICENSE). The upstream 1.3.8 manifest version
is retained for this development branch; the extension is not an upstream release.
