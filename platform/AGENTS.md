# platform/ — per-host packaging inputs

## Scope
Hand-edited, host-specific files that `build/build.sh` combines with `src/skills/`:

| Dir | Files | Consumed as |
| --- | --- | --- |
| `claude/` | `plugin.json` | copied to `claude/.claude-plugin/plugin.json` |
| `codex/` | `plugin.portable.json` (Agent Plugins 1.0 root manifest, Codex settings under `extensions["com.openai"]`), `plugin.json` (`.codex-plugin` compatibility overlay), `skills/<name>/agents/openai.yaml` per skill | root `codex/plugin/plugin.json`, `codex/plugin/.codex-plugin/plugin.json`, overlay copied into each skill dir |
| `grok/` | `plugin.json` | `grok/plugin.json` |
| `agent-plugin/` | `plugin.json` (Agent Plugins 1.0) | `agent-plugin/plugin.json` |
| `antigravity/` | `plugin.json` (`$schema`, `name`, `description` only), `rules/invocation.md` | `antigravity/plugin.json`, `antigravity/rules/` |

## Not this module's scope
Skill text (`src/skills/`), the generated packages, the root marketplace manifests
(`.claude-plugin/`, `.agents/plugins/`, `.grok-plugin/`, `.github/plugin/` — committed by hand, not
built).

## Invariants
- `version` is identical in `claude/plugin.json`, `codex/plugin.json`, `codex/plugin.portable.json`,
  `grok/plugin.json`, `agent-plugin/plugin.json` and equals the first `## vX.Y.Z` in `CHANGELOG.md`.
  Antigravity's manifest has no version by design.
- `name` is `ouroboros` everywhere; `homepage`/`repository` are
  `https://github.com/contiloop/ouroboros`; `license` is `Apache-2.0`.
- Codex root and overlay agree on name, version, description, author, homepage, repository, license,
  keywords and the whole `interface` object; the root manifest may contain only Agent Plugins 1.0
  fields; the overlay may contain only identity fields plus `skills`, `hooks`, `mcpServers`, `apps`,
  `interface`, `onboardingSkill`.
- Every `codex/skills/<name>/agents/openai.yaml` has `policy:\n  allow_implicit_invocation: false`,
  an `interface` with `display_name`, and mentions `Ouroboros` but never `Dryforge`.
- One `openai.yaml` must exist for every directory in `src/skills/` (today `init` and `approve`);
  a new skill without it fails the build. Removing a skill means removing its overlay too, or
  `verify.py` reports a skills mismatch.
- `antigravity/rules/invocation.md` must keep the three phrases `verify.py` checks: "Only invoke an
  ouroboros skill when the user explicitly enters", "Do not select or invoke ouroboros from semantic
  similarity", "Without an explicit ouroboros slash command".

## Testing
`python3 -B ci/verify.py` (clean tree) validates all of the above; `ci/test_ouroboros_branding.py`
covers names and URLs without a build.
