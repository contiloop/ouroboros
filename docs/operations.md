# Operations

## Prerequisites

| Requirement | Scope |
| --- | --- |
| git | everything |
| Python 3.11+ on macOS/Linux/WSL (POSIX `fcntl`) | tests, runtime scripts |
| bash, perl | `build/build.sh` |
| `shellcheck`, `actionlint` | CI only; optional locally |
| Claude Code with the Dryforge plugin installed and enabled | trying the plugin for real |

## Set up and verify (in order)

```bash
git clone https://github.com/contiloop/ouroboros.git
cd ouroboros
# 1. tests (macOS: /var is a symlink to /private/var; use an unsymlinked temp dir)
TMPDIR=/private/tmp PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s ci -p 'test_*.py'
# 2. regenerate the five packages from src/skills + platform/
bash build/build.sh
# 3. full consistency + reproducible-build check (requires a clean tree: commit first)
python3 -B ci/verify.py
```

Step 3 depends on step 2 having been committed: it builds again and fails if anything differs from
the committed tree, including untracked files. Run the test suite and the build one after the other,
never concurrently: the build rewrites the package trees that the mirror tests read.

## Try the plugin

Claude Code, from any target project (install Dryforge on the same host first):

```bash
claude --plugin-dir /path/to/ouroboros/claude
# inside the session: /ouroboros:init  …  /ouroboros:approve
```

Codex: register the checkout through Codex's local marketplace flow with
`.agents/plugins/marketplace.json` (points to `codex/plugin/`). `$ouroboros:init` works;
`$ouroboros:approve` reports that no Codex worker adapter exists yet.

## Runtime CLI (what L1 runs)

```bash
S=src/skills/init/scripts/ouroboros_cli.py
python3 -B $S --workspace /abs/proj --owner $CLAUDE_PID doctor --host claude
python3 -B $S --workspace /abs/proj --owner $CLAUDE_PID draft --scenario scenario.md --validation validation.md --spec spec.md --delegation delegation.md
python3 -B $S --workspace /abs/proj --owner $CLAUDE_PID shown
python3 -B $S --workspace /abs/proj --owner $CLAUDE_PID approve
python3 -B $S --workspace /abs/proj --owner $CLAUDE_PID cycle-start --kind development --goal goal.md --checkpoint <commit>
python3 -B $S --workspace /abs/proj --owner $CLAUDE_PID session-start --skill ready --message msg.md
python3 -B $S --workspace /abs/proj --owner $CLAUDE_PID session-wait            # blocks; run in the background; may return QUESTION
python3 -B $S --workspace /abs/proj --owner $CLAUDE_PID session-answer --answers answers.json --basis why.md
python3 -B $S --workspace /abs/proj --owner $CLAUDE_PID session-send --message next.md
python3 -B $S --workspace /abs/proj --owner $CLAUDE_PID evaluate --decision CONTINUE --basis basis.md
```

`doctor` is the only command that touches the real host without starting a model turn; everything
under `session-*` starts or controls a real headless `claude` process in the target project and costs
tokens. Records and raw turn output live under the target project's `.dryforge/ouroboros/`.

## Release

1. Bump `version` in `platform/claude/plugin.json`, `platform/codex/plugin.json`,
   `platform/codex/plugin.portable.json`, `platform/grok/plugin.json`, `platform/agent-plugin/plugin.json`.
2. Add `## vX.Y.Z (YYYY-MM-DD) — <title>` to `CHANGELOG.md` (move items out of `## Unreleased`).
3. `bash build/build.sh`, run the tests, commit source and generated packages together.
4. Tag `vX.Y.Z` and push; CI runs `verify.py --tag vX.Y.Z` and fails on any mismatch.

## CI

`.github/workflows/ci.yml` runs on pull requests, pushes to `main`/`release/**`, `v*` tags and manual
dispatch: actionlint (pinned 1.7.12 with SHA check) → shellcheck → `ci/verify.py` → unittest. Ubuntu
runner, system `python3`.
