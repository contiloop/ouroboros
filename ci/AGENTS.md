# ci/ — tests and repository verification

## Scope
- `test_*.py` — unittest modules run by CI with `python3 -m unittest discover -s ci -p 'test_*.py'`.
- `verify.py` — repository consistency checker: JSON validity of all `plugin.json`/
  `marketplace.json`, equal versions across ten manifests and the CHANGELOG heading, marketplace
  `source` targets, Agent Plugins 1.0 schema fields, Codex root/overlay agreement, Grok/Antigravity
  manual-only rules, Codex `allow_implicit_invocation: false`, and a reproducible rebuild from a
  clean tree. `--tag vX.Y.Z` adds the release-tag check.
- `skill_text.py` — helper that returns a `SKILL.md` plus its force-loaded `references/workflow.md`
  for contract tests.
- `fixtures/fake_app_server.py` — deterministic newline-JSON-RPC stand-in for `codex app-server`
  used by transport tests. It is not Codex and must never be wired as a backend.

## Not this module's scope
- Production code (`src/skills/init/scripts/`), the build (`build/`), manifests (`platform/`).

## Test families
| File | Exercises | Needs |
| --- | --- | --- |
| `test_mission_state.py`, `test_intent_changes.py`, `test_init_approve.py`, `test_migration_orchestration.py` | ledger transitions, DRAFT/activate, amend, migration cycle, CLI exit codes | real temp Git repos, subprocess |
| `test_runtime_bridge.py` | SQLite store, controller gates, adapters with SDK-shaped doubles and the fake app-server | `TMPDIR` without symlinks |
| `test_runtime_permissions.py`, `test_runtime_go_permissions.py`, `test_runtime_cycle.py`, `test_runtime_merge.py` | policy validation and classifier against real local Git worktrees/merges | git, `TMPDIR` without symlinks |
| `test_mission_contract.py`, `test_runtime_contract.py`, `test_feasibility_contract.py`, `test_landscape_contract.py` | pinned phrases/structure in skill text and packaged runtime boundary | — |
| `test_ouroboros_branding.py` | plugin name `ouroboros`, repo URL, README tokens, no `Dryforge` in Codex overlays, `README.upstream.md` present | — |

## Invariants
- Tests use synthetic consent and protocol doubles; **none** calls a live model or authenticated
  host. A passing suite is not evidence of live behavior, and no test may be written to imply it.
- Fixtures create workspaces in temp dirs and must pass the production symlink/`resolve()` checks;
  on macOS run with `TMPDIR=/private/tmp`. Never relax production checks to make a fixture pass.
- `verify.py` is read-only except for running `build/build.sh`, and requires a clean tree before
  and after; it must keep refusing untracked files (that is how stale outputs are caught).
- `test_runtime_cycle.py` and `test_runtime_go_permissions.py` import fixtures from
  `ci.test_runtime_permissions`, so `ci/` must stay importable as a package path from the repo root.

## Running
```bash
TMPDIR=/private/tmp PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s ci -p 'test_*.py'
python3 -B ci/verify.py            # clean committed tree only
python3 -B -m unittest ci.test_mission_state -v   # one module
```

## Direction
Tests pinning the bundled `ready`/`go`/`migration` text and the permission classifier go away with
those modules, including `test_legacy_state_is_preserved` in `test_ouroboros_branding.py`, which
reads `src/skills/go/SKILL.md`. Keep the rest of branding, manifest and build-reproducibility tests.
