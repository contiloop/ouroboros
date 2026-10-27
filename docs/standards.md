# Standards

## Source of truth and generated outputs

- **MUST** edit skills only under `src/skills/`. **MUST NOT** hand-edit `claude/`, `codex/plugin/`,
  `grok/`, `agent-plugin/` or `antigravity/`; `ci/verify.py` regenerates them and fails on any diff.
- **MUST** run `bash build/build.sh` after changing `src/skills/` or `platform/` and commit the
  regenerated packages in the same commit. Violation: CI's reproducible-build check fails with
  "generated outputs are stale or uncommitted".
- Anything placed under `src/skills/` ships to users in all five packages. **MUST NOT** place
  developer-only material there (module notes, design docs, tests).

## Skill frontmatter and manifests

- Every `src/skills/<name>/SKILL.md` **MUST** start with YAML frontmatter containing `name:` equal to
  its directory and a non-empty `description:`. Allowed keys: `name`, `description`, `license`,
  `compatibility`, `metadata`. `allowed-tools` and `disable-model-invocation` are injected by the
  build for the hosts that need them and **MUST NOT** appear in source.
- Adding a skill directory **MUST** be accompanied by (a) a `claude_tools` case in
  `build/build.sh` and (b) `platform/codex/skills/<name>/agents/openai.yaml` with
  `policy.allow_implicit_invocation: false`. Violation: build fails ("missing Claude tool mapping" /
  "missing Codex openai.yaml overlay").
- The ten versioned manifests (`platform/*/plugin*.json` and their generated copies) **MUST** carry
  the same `version`, and it **MUST** equal the first `## vX.Y.Z` heading in `CHANGELOG.md`.
  An `## Unreleased …` heading above it is allowed. A release tag **MUST** be exactly `v<version>`.
- Plugin name in every manifest and marketplace **MUST** be `ouroboros`; `homepage`/`repository`
  **MUST** be `https://github.com/contiloop/ouroboros`. Codex `openai.yaml` text **MUST NOT**
  mention Dryforge (branding test).
- `codex/plugin/.codex-plugin/` **MUST** contain only `plugin.json`, and that overlay **MUST** agree
  with the root manifest on name, version, description, author, homepage, repository, license,
  keywords and the `interface` object.

## README

- `README.md` and `README_ko.md` **MUST** contain: `# ⟲ Ouroboros`, the tokens `L1`, `L2`, `L3`,
  `/ouroboros:init`, `/ouroboros:approve`, `Grep MCP`, `Context7 MCP`,
  `Apache-2.0`, `prekuter`, and the clone line
  `git clone --depth 1 https://github.com/contiloop/ouroboros.git`. `README.upstream.md` **MUST**
  exist. Violation: `ci/test_ouroboros_branding.py` fails.
- Translations `README_ko.md`, `README_ja.md`, `README_zh.md` follow `README.md`; only the Korean one
  is test-checked.

## Verification gates (before merging to `main`)

1. `PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s ci -p 'test_*.py'` passes
   (on macOS set `TMPDIR=/private/tmp`; never run it concurrently with the build).
2. `bash build/build.sh` succeeds and leaves no diff.
3. `python3 ci/verify.py` passes from a **clean** tree (no untracked files anywhere in the repo).
4. CI additionally runs `actionlint` on workflows and `shellcheck build/build.sh`; both must pass.

## Runtime code

- Python **MUST** stay standard-library only (`ci/test_runtime_contract.py` checks imports).
- Private runtime state **MUST** live under the *target project's* git-ignored
  `.dryforge/ouroboros/`; every record write refuses if `.dryforge/` is not ignored there. The
  Ouroboros repository itself also ignores `.dryforge/`.
- The worker process **MUST** be started with a tool allow-list, never with
  `--dangerously-skip-permissions` or `--permission-mode bypassPermissions`
  (`ci/test_runtime_contract.py`). The message sent to the worker carries only caller text.
- Tests **MUST NOT** call a live model or host; the adapter is tested against `ci/fixtures/fake_claude.py`.

## Git conventions (current practice, changeable)

- Work on a feature branch; merge to `main` through a pull request. Commit subjects use
  `feat:`, `fix:`, `docs:`, `chore:`, `refactor:` prefixes.
- A release = version bump in the five `platform/` manifests, regenerated packages, a `## vX.Y.Z
  (date) — title` CHANGELOG entry, commit, tag `vX.Y.Z`. CI validates the tag against the manifests.
