# 0005 — One canonical skill tree, generated packages committed

## Context
Each host wants a different layout: Claude needs `allowed-tools` frontmatter and
`.claude-plugin/plugin.json`; Codex needs `agents/openai.yaml` per skill and two manifests; Grok and
Agent Plugins need `disable-model-invocation` but reject `allowed-tools`; Antigravity needs
byte-identical skills plus a rules file. Hosts install directly from repository paths named in
marketplace manifests, so the installable layout must exist in Git.

## Decision
`src/skills/` is the only hand-edited skill tree. `build/build.sh` generates the five package
directories, and those directories are committed. `ci/verify.py` rebuilds from a clean tree and fails
on any diff, so a stale or hand-edited package cannot merge.

## Alternatives
- **Build at install time / CI artifacts only.** Rejected: marketplace manifests point at
  repository paths; hosts do not run a build step.
- **Hand-maintain each package.** Rejected: five copies of every skill drift immediately.

## Consequences
- Every skill change is a two-step commit (edit source, regenerate) and doubles the diff size.
- Anything under `src/skills/` is shipped; developer material must live elsewhere.
- Version is declared ten times (five inputs, five outputs) and reconciled by the build and `verify.py`.
