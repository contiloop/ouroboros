# Status

Snapshot as of 2026-10-27, commit `13711a5` on `main` (v1.4.1 released 2026-10-24; an `Unreleased`
changelog section exists for cycle-aware delegation work).

## Direction

The project is being **rebuilt from its concept**. What stays: the L1/L2/L3 model, `init` as an
open-ended intent conversation, `approve` as the single human handoff, L1 invoking the *installed*
Dryforge, and full L1 authority after approval. What goes: the current runtime code and its
fine-grained permission model, and the bundled Dryforge-derived skills. Completion target: a real, unattended `init → approve → cycles → goal complete` run
on **Claude Code**. Codex follows; Grok, Agent Plugins and Antigravity stay packaging-only.

## Built and verified (current code, to be replaced)

| Area | State | Evidence |
| --- | --- | --- |
| `init`/`approve` skill text, L1 loop procedure, runtime guide | built; still phrased around human-only decisions and policy v4 bindings (legacy wording) | `src/skills/init`, `src/skills/approve`; contract tests in `ci/test_init_approve.py`, `test_mission_contract.py` |
| Intent ledger (`mission_state.py`), schemas 1–5, DRAFT→ACTIVE→cycles | built, unit-tested | `ci/test_mission_state.py`, `test_intent_changes.py` (247 tests pass locally with `TMPDIR=/private/tmp`) |
| External L2 runtime: SQLite mailbox, controller, Claude SDK adapter, Codex app-server adapter | built, tested with protocol doubles and a fake app-server, **not** live-verified end to end | `ci/test_runtime_bridge.py`, `ci/fixtures/fake_app_server.py` |
| Delegated tool-permission classifier, policy v1–v4, worktree/merge/lifecycle Git checks | built, tested with real local Git | `ci/test_runtime_permissions.py`, `test_runtime_cycle.py`, `test_runtime_go_permissions.py`, `test_runtime_merge.py` |
| Delegated Migration flow in the ledger and runtime | built, tested with synthetic consent | `ci/test_migration_orchestration.py` |
| Five-platform build, manifest/version/marketplace validation, reproducible-build check | built, passes in CI | `build/build.sh`, `ci/verify.py`, `.github/workflows/ci.yml` |
| Native skill invocation on Codex (`skills/list` resolution, `$dryforge:*` with skill input) | live-checked once on 2026-10-25 for invocation and same-session continuity only | logs under git-ignored `.dryforge/verification/` in this checkout, not committed |
| Native skill invocation on Claude Code (`/dryforge:*` after `slash_commands` check) | built, not live-verified | `runtime_bridge/adapters.py` |

## Remaining (in order)

1. **Decide the rebuilt shape.** Produce the first spec of the new implementation: how L1 holds the
   proposal, creates L2, invokes installed Dryforge, answers questions, approves Ready, accepts
   results and evaluates completion, with full authority after `approve` and no per-call policy
   objects. Decide what, if anything, of the ledger/mailbox is reused versus rewritten.
2. **Remove the bundled `ready`, `go`, `migration` skills** from `src/skills/` and the build
   mappings (`claude_tools`, Codex overlays, shared-reference pairs), and drop the contract tests
   that read them (`test_feasibility_contract.py`, `test_landscape_contract.py`, the `go`-reading
   parts of `test_mission_contract.py`, `test_legacy_state_is_preserved` in
   `test_ouroboros_branding.py`, `skill_text.py`).
3. **Replace the runtime code** per the new spec; remove `runtime_permissions.py`, `runtime_git.py`,
   `runtime_cycle.py`, `runtime_merge.py` and their tests, or whatever the spec supersedes.
4. **Rewrite the skill text and product docs** for full delegation: `src/skills/init/SKILL.md`
   ("human-only decisions" in the proposal), `src/skills/approve/SKILL.md`,
   `src/skills/init/references/orchestration.md` (policy v4 binding, "human-only boundaries"),
   `interview.md` ("what needs the human"), `runtime-bridge.md`, `docs/MISSION.md` and
   `docs/RUNTIME_POLICY.md` (all describe the per-call policy model).
5. **Live run on Claude Code:** `init → approve → ≥2 cycles → COMPLETE` with no human input after
   approve, on a trusted sample project with Dryforge installed. Record the evidence.
6. **Live run on Codex** with the same shape.
7. Release and update the four READMEs (`README.md`, `README_ko.md`, `README_ja.md`, `README_zh.md`).

## Blockers

None recorded. The rebuild has no external dependency beyond the user's Claude Code/Codex hosts and
an installed Dryforge.
