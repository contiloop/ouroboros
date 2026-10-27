# ci/ — tests and repository verification

## Scope
- `test_*.py` — unittest modules run by CI with `python3 -m unittest discover -s ci -p 'test_*.py'`.
- `verify.py` — repository consistency checker: JSON validity of all `plugin.json`/
  `marketplace.json`, equal versions across ten manifests and the CHANGELOG heading, marketplace
  `source` targets, Agent Plugins 1.0 schema fields, Codex root/overlay agreement, Grok/Antigravity
  manual-only rules, Codex `allow_implicit_invocation: false`, and a reproducible rebuild from a
  clean tree. `--tag vX.Y.Z` adds the release-tag check.
- `fixtures/fake_claude.py` — env-driven stand-in for the `claude` CLI (`FAKE_CLAUDE_LOG`,
  `FAKE_CLAUDE_SLEEP`, `FAKE_CLAUDE_MODE`, `FAKE_CLAUDE_SESSION`, `FAKE_CLAUDE_COST`,
  `FAKE_CLAUDE_DRYFORGE`). Tests copy it to a temp `bin/claude` first on `PATH`. It is not Claude
  and must never be wired as a host.

## Not this module's scope
- Production code (`src/skills/init/scripts/`), the build (`build/`), manifests (`platform/`).

## Test families
| File | Exercises | Needs |
| --- | --- | --- |
| `test_run_record.py` | every record command: draft/shown/approve/amend, required sections and limits, cycles, evaluate and stalled/limit stops, events and payload spill, owner and lock refusals, ignore guard, archive | real temp Git repos, subprocess, `TMPDIR` without symlinks |
| `test_claude_adapter.py` | argv shape (resume, allow-list, no bypass flags), detached launch, wait/status, cost once, session id recording and mismatch, INTERRUPTED paths, stop, doctor | the fake `claude` on `PATH` |
| `test_mission_contract.py` | pinned phrases in the skill text, absence of legacy wording, frontmatter rules, package mirror of `init/` | — |
| `test_runtime_contract.py` | packaged scripts byte-identical, packaged CLI `--help` runs, no bypass modes, no legacy private dir, no third-party imports | — |
| `test_ouroboros_branding.py` | plugin name `ouroboros`, repo URL, README tokens, no `Dryforge` in Codex overlays, `README.upstream.md` present | — |

## Invariants
- Tests use the fake host and temp repos; **none** calls a live model or authenticated host. A
  passing suite is not evidence of live behavior, and no test may be written to imply it.
- Fixtures create workspaces in temp dirs; on macOS run with `TMPDIR=/private/tmp`.
- `verify.py` is read-only except for running `build/build.sh`, and requires a clean tree before
  and after; it must keep refusing untracked files (that is how stale outputs are caught).
- `test_claude_adapter.py` imports the `Workspace` fixture from `test_run_record.py`, so `ci/` must
  stay importable as a package path from the repo root.
- Never run the suite concurrently with `build/build.sh`.

## Running
```bash
TMPDIR=/private/tmp PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s ci -p 'test_*.py'
python3 -B ci/verify.py            # clean committed tree only
python3 -B -m unittest ci.test_run_record -v   # one module
```
