# L1 operating ordinary Dryforge Migration

Migration prepares an existing codebase's durable project documentation. It is a separate
assignment before development, not another Ready stage. L1 keeps the user's intent and history;
the worker follows `../migration/SKILL.md` (relative to the init skill root) and its references.
No special worker mode, provider identity or private ledger is needed in that worker's prompt.

## Choose preparation only when needed

Inspect the existing code and project documentation, including `.dryforge/status.json`, rather
than treating an absent ignored marker in a new checkout as proof that migration is necessary.
New projects go directly to Ready. Prepared projects retain their existing harness; transfer or
reconcile missing state. An unfamiliar worker/session alone never justifies Migration.

The reviewed intent must include preparation of this existing project, with `migration` in
`delegated_actions`. Include question answering and result acceptance where delegated. This can
be approved with the original `ouroboros:approve`; do not ask again for the same authority.
Older contracts do not acquire Migration authority on upgrade. A necessary scope change follows
the existing intent amendment procedure, not a manually edited ledger or fabricated approval.

The ordinary runtime policy separately governs exact file edits and Git operations. Include the
actual documentation paths (root/module AGENTS.md, CLAUDE.md, docs/, .gitignore) and authorized
checkpoint operations in the proposal. Existing protected metadata rules still apply: callbacks
for `.dryforge/status.json` and backups are not automatically delegated by this addition. Use
existing host authority or the actual human decision when that host requires one; never bypass
the host or claim that Migration delegation grants arbitrary `.dryforge` writes. The external
runtime requires a Git repository with `.dryforge/` ignored before startup; establish those
prerequisites through the existing authorized setup path first.

## Run and review

1. Verify the ordinary host capabilities and create a fresh worker. Record ledger `start` with
   `kind: migration`, `reuse: false`, the real `session_id`, goal, checkpoint, capabilities,
   `basis` for delegated preparation and `need_ref` for the observed preparation need. It counts
   against the already approved cycle/stall budget; it does not replenish any limit.
2. With the external runtime, send `--kind migration --ledger <state> --cycle <id>` plus the
   existing codebase, original intent/constraints and relevant decisions in `--text-file`.
   Native hosts load the same complete Migration skill. Migration has its procedure in SKILL.md;
   unlike Ready/Go, it does not require a `references/workflow.md` entrypoint.
3. Answer the worker's ordinary questions from original human intent and code evidence. Return
   missing product/business decisions to the user only when needed. Preserve the ordinary
   SCAN → ELICIT → GENERATE → independent REVIEW procedure. L1's acceptance never replaces the
   independent review. Continue through `--kind message` in the same Migration session.
4. Read the actual generated/updated harness files, the reviewer evidence and captured checks.
   Require all generated/updated documentation paths, root AGENTS.md and CLAUDE.md, project docs,
   `.dryforge/status.json`, and .gitignore if modified. Save the path list as a JSON array and run
   `mission_state.py migration-digest --workspace <repo> --paths-file <paths.json>`.
   Record `result` as L2 with that `paths` list and `digest`, `result_ref`, observed successful
   `checks` (command/exit_code/observed), independent `review` (independent/evidence_ref),
   `blockers: []` and `children_quiescent: true`. Do not invent check results or reviewer evidence.
   This verifies recorded evidence and file identity, not the truth of the worker's claims.
5. If corrections are needed, continue Migration in its existing session and record a replacement
   `result` after the independent review covers the corrected artifacts. Accept with `accept`,
   the exact reviewed `digest`, and L1's `basis`. Changed files invalidate acceptance; recapture
   and review the actual result instead of approving an old hash. An answer or completed host
   turn cannot record acceptance automatically.

## Checkpoint and start development

Migration itself writes documentation and does not commit, merge or implement product code.
After acceptance, L1 separately arranges the approved harness checkpoint: use its authorized Git
tools or an explicit follow-up message to the same worker. This is a distinct checkpoint action,
not part of running Migration. Delegated staging/commit callbacks must concern only reviewed
documentation, match the human runtime policy and retain the accepted content digest. They do
not authorize branches, lifecycle cleanup, source changes or arbitrary commands.

After observing the actual checkpoint and stopped children, record `close` as L2 with
`children_quiescent: true`, `checkpoint_ref` and `handoff_ref` containing the commit, complete
artifact/review references, outstanding facts and necessary ignored-state transfer information.
Migration has no 3-doc archive. L1 then records the normal `evaluate` decision against the full
goal. Preparation alone is not completion of a goal that still requires product implementation.

For subsequent Ready, stop/reconcile the Migration worker and SPAWN a fresh session with the
accepted checkpoint and original intent. Record ordinary `start` and use Ready → Go there.
Never reuse the Migration session for development, even if its context capacity is sufficient.
During interruption, use the existing `interrupt → resume` path for that exact Migration session;
do not restart preparation or replay writes merely because a turn was lost.

## State compatibility

Migration-authorized active runs use ledger schema 4 so older runtimes reject them. Existing
schema 1–3 runs and runtime-policy v1–v3 grants remain readable and retain their scope. The flow is
`start(kind=migration) → result → accept → close → evaluate`; questions and recovery work as above.
No Ready approval or Go event is manufactured for a Migration assignment.
