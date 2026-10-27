# Changelog

## Unreleased — rebuild from the concept

- Remove the bundled `ready`, `go` and `migration` skills and their build mappings. `src/skills/`
  now contains `init` and `approve` only; L1 invokes the user's installed Dryforge plugin and
  reports a missing plugin instead of substituting procedure text.
- Remove the legacy runtime: the per-call permission classifier and policy versions 1–4, the
  five-schema intent ledger, the SQLite mailbox, the Claude SDK and Codex app-server adapters, and
  their tests. Legacy `.dryforge/mission/` ledgers are ignored, not migrated.
- Add a private run record under the target project's git-ignored `.dryforge/ouroboros/`
  (`proposal.md`, `run.json`, append-only `events.jsonl`, raw turn results) with explicit limits:
  max cycles, max stalled cycles and a USD budget or explicit "no cap". Reaching a limit stops the
  run; a revised proposal approved again resumes it.
- Run L2 as one persistent headless Claude Code session (`claude -p`, resumed between turns) in
  the target project, with every host tool pre-allowed by list and the user's deny rules intact.
  Ready and Go of one cycle use the same session; the session is kept across cycles by default.
- Delegate fully after `approve`: L1 answers worker questions, approves Ready documents, merges,
  pushes and spends within the budget without further consent. Clarification is folded in, a scope
  change is a re-approved proposal applied between cycles, and "stop" aborts immediately.
- Fold the still-true parts of `docs/MISSION.md` and `docs/RUNTIME_POLICY.md` into `README.md` and
  delete both files; mark the translated READMEs as pending against the English one.
- Claude Code is the supported execution host. The Codex package is built and installable, but
  `approve` reports that no Codex host adapter exists yet. Grok, Agent Plugins and Antigravity
  packages are format-only. A full unattended run is not yet live-verified.

## v1.4.1 (2026-10-24) — L1-managed Migration preparation

- Let L1 assign the existing Dryforge Migration procedure, relay questions, review actual
  documentation and independent-review evidence, and checkpoint an accepted result.
- Add explicit migration assignments, real artifact digests, stale-review guards and a fresh
  session requirement before subsequent Ready/Go. Preserve interruption and budget rules.
- Add `worker_runtime.py send --kind migration` with ordinary caller semantics. Existing runtime
  policy scopes remain unchanged; Migration only delegates eligible documentation edits and
  separately requested, accepted-document checkpoints. Protected metadata remains protected.
- Migration-authorized active runs use schema 4; existing runs remain readable without gaining
  new authority. Add local files/Git/SQLite/CLI regressions; full live model execution is unverified.

## v1.4.0 (2026-10-24) — init conversation and approve handoff

- Replace the public mission skill with `ouroboros:init` for ongoing intent discussion and
  `ouroboros:approve` for handing the reviewed proposal to L1's ordinary Ready/Go loop.
- Add durable DRAFT/revise/activate transitions. No cycle execution or active tool authority
  before activation; one human handoff binds exact intent and proposed execution scope.
- Keep the user conversation open during execution and isolate the interview procedure for
  future upgrades. Preserve independent Ready/Go review and caller-neutral lower tiers.
- Retain existing mission ledgers and IDs. Repeated commands do not reset runs, refill budgets
  or expand authority. Formal intent amendments still commit at evaluated cycle boundaries.
- Regenerate all five platform packages with five explicit-invocation skills. State/CLI tests
  verify handoff semantics; a complete fresh live-model loop remains unverified.
- Preserve the separate v3 `integration_branch` grant for exact-commit merges without
  granting worktree lifecycle operations. Reject mixed policy shapes.
- Retain the outer callback drain and the contract-level human-only `merge` restriction.

## v1.3.11 (2026-10-24) — ordinary caller interface and child request lifetime

- Keep Mission identity and authority in the outer controller; Ready/Go use their ordinary
  caller interface, and structured Codex questions use contract-bound question delegation.
- Drain observed Codex child work and callbacks after parent turn completion, preserving live
  request bindings without extra model turns; refuse successful settlement with open requests.
- Add explicit policy v3 local Go creation/integration/cleanup, bound to branch, path and Git-state
  scope. Old grants stay unchanged; cleanup preserves unmerged, dirty, untracked and ignored data.
- Recognize exact approved Python verification argv with `-B` before `-m`.
- Add actual local Git and controller/protocol regressions. These do not certify a complete live
  Mission or Claude child-lifecycle behavior.

## v1.3.10 (2026-10-24) — bounded Go worktree permissions

- Add a separately human-approved `go_worktrees` opt-in under runtime policy version 2;
  existing version-1 grants remain base-only and cannot silently expand on upgrade.
- Permit scoped Git staging, local commits, file edits and exact verification commands from
  registered `.dryforge/worktrees/<task-id>` checkouts of the approved repository.
- Validate Git's worktree registry, linked `.git` pointer, common metadata and effective index;
  reject foreign checkout, traversal, symlink, unapproved paths and dangerous commands.
- Bind delegated callback consumption to the **same reviewed operation and index digest**, fixing
  a record/consume gap where an additional in-scope file could be staged after an L1 approval.
- Keep worktree creation, removal, task-branch merging and remote/destructive commands human-only;
  real model end-to-end behavior remains unverified.

## v1.3.9 (2026-10-24) — experimental scoped delegation

- Let L1 approve exact local tool requests within an explicitly human-approved runtime policy.
- Validate paths, exact verification argv, active Go/doc/session identity and policy version at
  response recording and consumption. Preserve human provenance for grants and L1 provenance
  for decisions; old missions remain human-only until opted in.
- Add human-only grant/revoke events without changing the current mission goal, documents or
  budgets. State schema 3 preserves this authority across optional skill-interface events.
- Unknown commands, remote/destructive operations and permission expansion remain human-only.
- Include real Git/SQLite and mock-host CLI tests; live model behavior remains unverified.
- Bump plugin cache identity; restart/reconcile active controllers rather than silently hot-reload.

## Unreleased — experimental fork mission extension

- Add optional persistent Claude SDK / Codex App Server workers, durable local messaging and
  request/permission relay with explicit same-ID recovery and uncertain-delivery handling.
- Connect Mission to executable transport without changing intent, review or approval ownership.
- Add deterministic protocol/subprocess tests; live model acceptance remains unverified.

- Rebrand public plugin identity and documentation as **Ouroboros**; preserve upstream attribution and legacy `.dryforge/` state paths.
- Add centered GitHub README layouts with architecture diagrams and quick-start instructions; leave live session support explicitly experimental.
- Add opt-in mission intent ownership, persistent ready-go cycle workers, decision relay and
  cycle-boundary reuse/replacement. Keep existing task dispatch and independent-review gates.
- Preserve existing ready/go procedures in force-loaded workflow references, with separate
  session/relay additions at their entrypoints.
- Add SPAWN/RESUME/FRESH_REVIEW lifecycle contracts and explicit artifact/checkpoint handoffs.
- Bundle a standard-library local ledger with approval/session/revision/idempotency guards.
- Document capability preflight, hook limitations and untested live-host acceptance; no global service
  or permission-bypassing hook is installed. Upstream version 1.3.8 is retained; this is not a release.

## v1.3.8 (2026-10-17)

- Updated the Codex package to the current plugin format; older Codex versions keep working
- Added the community Discord

## v1.3.7 (2026-09-27)

- Added Chinese and Japanese READMEs

## v1.3.6 (2026-09-26)

- Replaced typographic ellipses and circled numerals in skill text with plain ASCII so plugin security scanners no longer misread them; no change to skill behavior

## v1.3.5 (2026-09-25)

- Relicensed under Apache-2.0
- migration and go now back up and review an existing AGENTS.md before rewriting it, as they do for CLAUDE.md
- Rewrote the skill descriptions, fixed the README install and update steps, and added contribution guidelines

## v1.3.1 (2026-09-24)

- Rewrote the README in English and Korean, with light and dark graphics and per-agent install and update instructions
- No changes to skills

## v1.3.0 (2026-09-24)

- Added Antigravity CLI support with its official plugin manifest and plugin rules
- Added the Antigravity CLI install guide to the README

## v1.2.0 (2026-09-23)

- Added Grok Build support, based in part on @williamjeong2’s contribution in #3
- Added GitHub Copilot CLI support through Agent Plugins 1.0 packaging

## v1.1.2 (2026-09-23)

- Refined plugin marketplace metadata

## v1.1.1 (2026-06-12)

- Brought the skill instructions in line with each other
- Added update instructions to the README

## v1.1.0 (2026-06-09)

- Merged set into ready, reducing the skills from four to three
- Reworked how ready finds the decisions that are yours to make
- go and migration now finish only on evidence from checks that ran

## v1.0.2 (2026-06-08)

- Streamlined the set skill and refined how go runs tasks

## v1.0.1 (2026-06-07)

- Added the project documentation layout to the README

## v1.0.0 (2026-06-07)

- First stable release
- Added migration for bringing existing projects in
- ready and go now create and keep project documentation that the next cycle starts from

## v0.5.1 (2026-06-06)

- Refined how go runs tasks

## v0.5.0 (2026-06-03)

- Added Codex support, with Claude Code and Codex built from one skill source
- Made go's task execution more efficient

## v0.2.5 (2026-06-02)

- Made go's task execution more efficient

## v0.2.0 (2026-06-01)

- Reworked ready and go for leaner runs

## v0.1.2 (2026-06-01)

- Made task execution more efficient

## v0.1.1 (2026-06-01)

- Fixed output files colliding with paths in your project
