# Changelog

## v1.3.11 (2026-10-24) — live callback lifetime and optional scoped integration

- Preserve live nested L3 permission/question requests after the parent L2 turn yields;
  keep the parent dispatched until actual callback consumption or original bounded timeout.
- Recognize `python3 -B -m unittest` as an eligible verification entrypoint **only**
  when that exact command was human-granted in the runtime policy.
- Add optional policy v3 `git_merge`, separately granted by a human for one named
  destination branch. Require a pinned commit from a registered clean Dryforge task worktree,
  an ancestor base, clean root and scoped addition/modification-only diff; no blanket merges.
- Existing v1/v2 authorizations remain unchanged. Worktree add/remove, branch deletion,
  forced integration and remote operations are still outside delegation.
- Add real-Git negative/positive tests and callback-lifecycle regressions. Authenticated
  live Codex/Claude E2E, resumed T1/T2 integration and child quiescence remain unverified.

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
