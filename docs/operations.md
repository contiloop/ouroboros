# Operations

## Prerequisites

| Requirement | Scope |
| --- | --- |
| git | everything |
| Python 3.11+ on macOS/Linux/WSL (POSIX `fcntl` is used) | tests, runtime scripts |
| bash, perl | `build/build.sh` |
| `shellcheck`, `actionlint` | CI only; optional locally |
| Claude Code and/or Codex CLI with Dryforge installed | trying the plugin for real |
| `claude-agent-sdk==0.2.173` in the Python env | only the external Claude runtime (`worker_runtime.py --backend claude`) |

## Set up and verify (in order)

```bash
git clone https://github.com/contiloop/ouroboros.git
cd ouroboros
# 1. tests (macOS: /var is a symlink to /private/var and the runtime rejects symlinked temp paths)
TMPDIR=/private/tmp PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s ci -p 'test_*.py'
# 2. regenerate the five packages from src/skills + platform/
bash build/build.sh
# 3. full consistency + reproducible-build check (requires a clean tree: commit first)
python3 -B ci/verify.py
```

Step 3 depends on step 2 having been committed: it builds again and fails if anything differs from
the committed tree, including untracked files.

## Try the plugin

Claude Code, from any target project:

```bash
claude --plugin-dir /path/to/ouroboros/claude
# then inside the session: /ouroboros:init  …  /ouroboros:approve
```

Codex: register the checkout through Codex's local marketplace flow with
`.agents/plugins/marketplace.json` (points to `codex/plugin/`), enable `ouroboros`, then use
`$ouroboros:init` and `$ouroboros:approve`. Install Dryforge on the same host; L1 invokes the
installed `dryforge:ready|go|migration`.

## External L2 runtime (optional)

Used when the host cannot hold a persistent worker session natively. All commands take
`--workspace <absolute git root of the target project> --worker <id>`; the target project must have
`.dryforge/` in its `.gitignore` or `start` refuses.

```bash
S=src/skills/init/scripts
python3 -B $S/worker_runtime.py doctor --backend claude|codex          # dependency check only
python3 -B $S/worker_runtime.py start  --workspace /abs/proj --worker w1 --backend codex \
        [--turn-seconds 600] [--lifetime-seconds 3600] [--max-messages 20] [--max-model-turns 50] \
        [--budget-usd N  (claude only)] [--load-settings user|project|local] [--dryforge-plugin /path (claude only)]
python3 -B $S/worker_runtime.py status --workspace /abs/proj --worker w1   # wait for IDLE + session_id
python3 -B $S/worker_runtime.py send   --workspace /abs/proj --worker w1 --id m1 --kind probe|ready|go|migration|message \
        --text-file goal.md [--ledger /abs/proj/.dryforge/mission/state.json --cycle c1]
python3 -B $S/worker_runtime.py wait   --workspace /abs/proj --worker w1 --id m1 --timeout 30
python3 -B $S/worker_runtime.py answer --workspace /abs/proj --worker w1 --request-id <id> --response-file answer.json
python3 -B $S/worker_runtime.py result|events|stop|resume …
```

Ledger commands: `python3 -B $S/mission_state.py draft|apply|show|digest|migration-digest …` with
`--state /abs/proj/.dryforge/mission/state.json`. Logs land beside the SQLite mailbox under
`.dryforge/mission/runtime/` in the target project.

## Release

1. Bump `version` in `platform/claude/plugin.json`, `platform/codex/plugin.json`,
   `platform/codex/plugin.portable.json`, `platform/grok/plugin.json`, `platform/agent-plugin/plugin.json`.
2. Add `## vX.Y.Z (YYYY-MM-DD) — <title>` to `CHANGELOG.md` (move items out of `## Unreleased`).
3. `bash build/build.sh`, run the tests, commit source and generated packages together.
4. Tag `vX.Y.Z` and push; CI runs `verify.py --tag vX.Y.Z` and fails on any mismatch.

## CI

`.github/workflows/ci.yml` runs on pull requests, pushes to `main`/`release/**`, `v*` tags and manual dispatch:
actionlint (pinned 1.7.12 with SHA check) → shellcheck → `ci/verify.py` → unittest. Ubuntu runner,
system `python3`.
