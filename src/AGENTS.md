# src/ — canonical skills and the Python runtime

## Scope
- `skills/<name>/SKILL.md` + `references/` — the text each host loads. Five directories today:
  `init` (L1 entry: conversation, proposal, the L1 loop in `references/orchestration.md`, the runtime
  guide in `references/runtime-bridge.md`), `approve` (handoff; points at init's references), and the
  legacy `ready`, `go`, `migration` copies.
- `skills/init/scripts/` — all executable code: `mission_state.py` (ledger CLI),
  `worker_runtime.py` (external L2 controller CLI), `runtime_bridge/` (SQLite store, serve loop,
  Claude SDK / Codex app-server adapters), `runtime_permissions.py` + `runtime_git.py` +
  `runtime_cycle.py` + `runtime_merge.py` (delegated-permission classifier, legacy),
  `migration_artifacts.py`, `runtime-requirements.txt` (optional SDK pin).

## Not this module's scope
- Host manifests and overlays (`platform/`), package generation (`build/`), tests (`ci/`).
- The generated copies under `claude/`, `codex/plugin/`, `grok/`, `agent-plugin/`, `antigravity/`.
  Edit here, rebuild there.

## Invariants
- **Everything in `skills/` is shipped verbatim** to all five packages and must be user-facing.
  No dev notes, tests or scratch files.
- `SKILL.md` frontmatter: `name` equals the directory, `description` non-empty, no `allowed-tools`
  and no `disable-model-invocation` (the build injects them).
- These pairs stay byte-identical or the build aborts:
  `migration/references/harness-format.md` ↔ `go/references/harness-format.md`,
  `migration/references/harness-review.md` ↔ `go/references/harness-review.md`,
  `ready/references/foundation-format.md` ↔ `go/references/foundation-format.md`.
- Skill text never tells L1 to paste Dryforge procedure files or use the bundled copies as a backend;
  it tells L1 to invoke the installed `dryforge:<kind>` natively and to report a missing skill.
- The worker prompt built in `runtime_bridge/controller.py::prompt_for` carries only the caller's
  text and the skill selector. No Ouroboros identity, mission ID, principal or approval bookkeeping.
- Scripts: Python 3.11+, standard library only; `claude_agent_sdk` is imported lazily inside
  `ClaudeAdapter.connect` and nowhere else. Run with `-B`.
- Ledger and mailbox files are created under the *target project's* `.dryforge/mission/` with
  mode 0700/0600, and `worker_runtime.py` refuses a workspace whose `.gitignore` does not ignore
  `.dryforge/`.

## Patterns
- Refusals raise `ContractError` / `BridgeError` / `PolicyError` (all `ValueError` subclasses) via a
  local `require(cond, message)`; CLIs catch them and print `BLOCKED` with exit code 2. New code
  follows the same shape: validate, raise, never partially apply.
- State changes are pure functions (`mission_state.apply(state, event) -> new_state`) wrapped in a
  file-lock transaction (`_transaction`); SQLite writes use `Store.tx()` (`BEGIN IMMEDIATE`).
- Identity re-validation happens twice: when an answer is recorded (`Store.answer`) and when the
  host consumes it (`Store.take_answer` → `controller.check_answer`); keep both if the code survives.
- Lazy imports (`import mission_state` inside functions) exist because `scripts/` is not a package
  and `runtime_bridge/` imports siblings by script-dir path. Do not convert to a package without
  updating `ci/` imports and the shipped layout.

## Testing
- Tests live in `ci/` (not here) and import these modules by path. Run
  `TMPDIR=/private/tmp PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s ci -p 'test_*.py'`
  from the repository root.
- Skill text changes are pinned by `ci/test_mission_contract.py`, `test_runtime_contract.py`,
  `test_feasibility_contract.py`, `test_landscape_contract.py` (the last two read the legacy
  `ready` skill).
- After any change here: `bash build/build.sh`, then check `git status` shows only intended
  regenerated files.

## Direction
The permission classifier, policy versions 1–4 and the bundled `ready`/`go`/`migration` skills are
legacy under the rebuild. Fix defects if they block work; do not add features to them.
