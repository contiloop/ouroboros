# src/ — canonical skills and the Python runtime

## Scope
- `skills/<name>/SKILL.md` + `references/` — the text each host loads. Two directories: `init`
  (L1 entry: the conversation in `references/interview.md`, the loop in
  `references/orchestration.md`, the command guide in `references/runtime.md`) and `approve`
  (handoff; points at init's references).
- `skills/init/scripts/` — all executable code: `ouroboros_cli.py` (entry point), `ouroboros/core.py`
  (pure record rules: the four proposal documents' parsers and completeness, set digest, cycles incl. beta), `ouroboros/store.py` (private dir, lock, owner, events, archive),
  `ouroboros/ports.py` (`HostSession` protocol), `ouroboros/adapters/claude.py` (headless `claude`
  through the streaming control channel), `ouroboros/relay.py` (per-turn relay: stdin/stdout of
  `claude`, question files, automatic permission allow; standard library, run by path, no package imports).

## Not this module's scope
- Host manifests and overlays (`platform/`), package generation (`build/`), tests (`ci/`).
- The generated copies under `claude/`, `codex/plugin/`, `grok/`, `agent-plugin/`, `antigravity/`.
  Edit here, rebuild there.

## Invariants
- **Everything in `skills/` is shipped verbatim** to all five packages and must be user-facing.
  No dev notes, tests or scratch files.
- `SKILL.md` frontmatter: `name` equals the directory, `description` non-empty, no `allowed-tools`
  and no `disable-model-invocation` (the build injects them).
- Skill text never tells L1 to paste Dryforge procedure text or to use a bundled copy; it tells L1
  to send `/dryforge:<kind>` through `session-start` and to report a missing plugin.
- The message handed to the host carries only the caller's text (and the `/dryforge:<kind>` prefix).
  No Ouroboros identity, run id, owner or approval bookkeeping (`adapters/claude.py`, `ouroboros_cli.py`).
- No bypass flag anywhere (`--dangerously-skip-permissions`, `bypassPermissions`); tool access is
  the allow-list constant in `adapters/claude.py` plus the relay's automatic allow of what still
  prompts (`ci/test_runtime_contract.py` pins the absence of bypass flags). `AskUserQuestion` must
  never be added to the allow-list: an allow-listed tool never reaches the channel, and L1 would
  stop seeing questions.
- The host's `total_cost_usd` is cumulative per session; `_settle` charges the delta
  (`session.cost_total_usd` is the baseline). Do not add the reported figure directly.
- Scripts: Python 3.11+, standard library only. `ouroboros_cli.py` inserts its own directory into
  `sys.path`; run it by path with `-B`.
- Record files are created under the *target project's* `.dryforge/ouroboros/` with modes 0700/0600,
  and every write refuses when `.dryforge/` is not git-ignored there.

## Patterns
- Refusals raise `core.RecordError` (a `ValueError`) via `core.require(cond, message, **details)`;
  the CLI prints `{"status":"BLOCKED","error":…}` with exit 2. Validate, raise, never partially apply.
- `core` functions are pure (`run -> new run`); `store.transaction()` wraps them with the file lock
  and the workspace check. `session-*` commands settle results inside a transaction and are
  idempotent (`turn.cost_recorded`).
- Hosts are reached only through `ports.HostSession`; `adapters.for_host(name)` is the single lookup.
  A new host = a new adapter module + one entry there, no change to the commands.
- Tunables (allow-list, max turns, model, stop grace) are module constants in the adapter.

## Testing
- Tests live in `ci/`. Run
  `TMPDIR=/private/tmp PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s ci -p 'test_*.py'`
  from the repository root, never concurrently with `build/build.sh`.
- Skill text is pinned by `ci/test_mission_contract.py`; packaged scripts by
  `ci/test_runtime_contract.py`; behavior by `ci/test_run_record.py` and `ci/test_claude_adapter.py`
  (the latter against `ci/fixtures/fake_claude.py`, never the real host).
- After any change here: `bash build/build.sh`, then check `git status` shows only intended
  regenerated files.
- The proposal is a set of four documents (`scenario.md`, `validation.md`, `spec.md`, `delegation.md`);
  `core.check_set` is the single completeness authority and `core.set_digest` the single digest; keep
  `interview.md`'s templates and the parsers' leniency in step. `delegation.md` is never quoted to L2.
- `COMPLETE` is accepted only on a `beta` cycle; the cycles limit is enforced at development
  `cycle-start` and on REPLAN / development-ESCALATE, not on CONTINUE (so a beta cycle can follow the
  last allowed development cycle).
