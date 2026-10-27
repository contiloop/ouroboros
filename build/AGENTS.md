# build/ — package generation

## Scope
`build.sh`: regenerates `claude/`, `codex/plugin/`, `grok/`, `agent-plugin/`, `antigravity/` from
`src/skills/` and `platform/`. Builds into a temporary directory, runs all guards, then swaps the
five output directories atomically (old outputs are staged aside and restored if any move fails).

## Not this module's scope
Deciding manifest content (`platform/`), skill text (`src/skills/`), validation of the committed
result (`ci/verify.py`).

## Guards (each aborts the build with a `FAILED:` line)
1. Three shared reference pairs under `src/skills/` are byte-identical.
2. Skill list is discovered from `src/skills/*/`; every skill needs a `claude_tools` case (bash 3.2
   `case`, no associative arrays) and a Codex `agents/openai.yaml` overlay.
3. Frontmatter injection is verified after the fact: exactly one `disable-model-invocation: true`
   (and for Claude exactly one `allowed-tools:`) per generated `SKILL.md`; Grok and Agent Plugin
   outputs must contain no `allowed-tools:`.
4. Ten manifest versions (five inputs, five outputs) are identical and equal the first `## v…`
   heading in `CHANGELOG.md`.

## Invariants
- Runs under `set -euo pipefail`; must pass `shellcheck` (CI) and `bash -n`.
- Never writes outside the repo; uses `mktemp -d "$ROOT/.build.XXXXXX"` and removes it on exit.
- Per-skill Claude `allowed-tools` lists are the only place tool permissions for the plugin are
  declared; changing a skill's needed tools means editing `claude_tools()` here.
- Output must be deterministic: running twice on the same inputs produces no diff. `.DS_Store` is
  removed from outputs.
- Root marketplace manifests are not build outputs and must not be touched here.

## Testing
```bash
bash -n build/build.sh && bash build/build.sh && git status --short   # only intended files change
python3 -B ci/verify.py                                              # from a clean committed tree
```
