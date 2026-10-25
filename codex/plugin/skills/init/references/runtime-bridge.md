# Host sessions and optional runtime

Read this when selecting or operating a transport. Prefer verified native persistent sessions;
otherwise `scripts/worker_runtime.py` supplies a full Codex App Server or Claude SDK controller.
Verify real identity/resume, question relay, installed skill invocation, L3 tools/independent
reviewers, workspace access and limits. Presence of a tool, dependency or PID is not certification.
A one-shot process plus summary does not preserve a session. Model behavior is not certified by
static/unit checks; live verification needs cycles, questions, reviews, handoffs and recovery.

## Host setup

Use actual installed APIs rather than assumed nesting depths or resume parameters. Codex resolves
skills through workspace `skills/list`. Claude SDK checks `slash_commands` in its init event;
ordinary subagents may lack AskUserQuestion or manual-skill preloading, so verify the actual relay.
An SDK controller can provide full sessions without spending a native subagent nesting level.
L2 still needs verified L3 access. Invoke skills as specified in `orchestration.md`.

The external controller requires Python 3.11+, POSIX locks, a Git repository and ignored
`.dryforge/`. Codex needs its CLI; Claude needs the SDK in the selected environment. Use absolute
script/workspace paths. Do not auto-install, log in or change host permissions. Claude settings/MCP
loading is explicit via `--load-settings`; `--dryforge-plugin <root>` selects an installed plugin
whose `.claude-plugin/plugin.json` identifies `dryforge`. Codex uses host discovery instead.

## Commands

Use script `--help` for arguments. Use the Records section below for ledger events.

1. `doctor --backend claude|codex` checks dependencies, not authentication/live operation.
   `start --workspace <repo> --worker <id> --backend <host>` creates the controller with finite
   turn/lifetime/message limits within the reviewed budget. Claude bootstrap can incur cost.
   Wait for `status` to report a real `session_id` and IDLE. Use read-only `send --kind probe`
   with `--id`/`--text-file` to verify capabilities; self-report alone is insufficient.
2. Record ledger `start` using observed identity/capabilities. Send
   `send --kind ready --id <id> --ledger <state> --cycle <id> --text-file <goal>`.
   The host loads installed Dryforge; the controller adds no role or procedure-body prompt.
   Missing/disabled/ambiguous skills fail before the model turn or Go start.
3. `wait --id <id> --timeout 30` returns replies or pending input. Timeout is not task failure.
   Answer yielded prose questions with `send --kind message` to the same worker. Record decision
   provenance; an answer is not Go approval. Ordinary message text is preserved verbatim.
4. Review and record `ready`/`approve`; for v4 also `bind_runtime`. `send --kind go` rechecks
   identity, intent, questions and document approval at enqueue/dispatch and records the **go**
   event immediately before sending. Do not pre-record it. A subsequent error is UNCERTAIN/GO.
5. Record result/accept/close/evaluate from evidence. For corrections, record `rework` then send
   `message`; after acceptance use messages for cleanup in the same session. TURN_COMPLETE only
   reports a settled host turn, not accepted work. Migration uses `--kind migration` and
   `orchestration.md#migration`, followed by a fresh development session.

## Pending requests

`status.pending` carries request ID/content, session_id, fingerprint and delegation eligibility.
Use `answer --request-id <id> --response-file <json>` with `session_id`, `request_digest`,
`principal` (L1/human), actual `basis` and `action`. These records are not self-authenticating.

For questions, `action: answer` supplies `answers` keyed by Codex question ID or Claude original
question text. For tools, use Execution scope below; eligibility is a hint, not approval.
A delegated allow uses `principal: L1`, `action: allow`, the current `policy_digest` and decision
basis. Deny with `action: deny`; out-of-scope authority needs the human. Use exact-call responses,
never session-wide approval or permission amendments. Host controls may resolve requests earlier.
Permission expansion, MCP elicitation and unsupported RPC methods fail closed. Child JSON grants
no authority. Keep private state/provider identity outside worker messages.

## Recovery and evidence

Receipts: QUEUED, DISPATCHED, TURN_COMPLETE, TURN_FAILED, REJECTED, CANCELLED, UNCERTAIN.
Identical message-ID retries return the existing receipt; changed content fails. One OS-locked
controller writes turns per workspace. Codex drains observed child callbacks within the original
budget before settling; this does not certify unobserved children or Claude child drainage.

On timeout/disconnection, inspect effects and children before
`resume --reconciled --basis <evidence>`. Resume retains the recorded host ID and limits, expires
old callbacks and cancels unsent input for explicit reissue. Never automatically replay uncertain
writes. New workers require `--handoff-ref` and reconciled workspace/children. Plugin updates do
not hot-reload a controller: stop/reconcile and resume the same session on the updated runtime.

`stop` requires confirmed STOPPED/ERROR plus separate child inspection. `result --id` returns a
compact reply; `events --after <cursor> --limit 50` exposes activity. Use `--full` only for needed
protected evidence; keep logs ignored. Hooks observe, never authorize or complete work.
No auto-go-on-stop hook. This same-user controller is not a hostile-process security sandbox.

## Records

Use `scripts/mission_state.py` with ignored `.dryforge/mission/state.json`; preserve existing runs.
Keep original intent/decisions, current L2 ID, phase and artifact/checkpoint references. Detailed
checks/logs stay in files. Use `show` for current revision/digests and read stored evidence as needed.
Records validate consistency, not user identity or whether model claims are true.

- `draft --state <path> --contract <json> [--policy <json>]` starts an unapproved draft with stable
  `mission_id` and absolute `workspace`. `revise_draft` replaces its full `contract` and
  `runtime_policy` (explicit null if absent), preserving identity and source `basis`.
- Before activation, complete goal, success_criteria, constraints, delegated_actions, human_only,
  max_cycles and max_stalled_cycles; include applicable host limits in the reviewed proposal.
  Available delegated actions: answer, approve_ready, accept_result, complete, migration.
  `activate` uses `actor: human`, actual approval_ref, review basis and expected_proposal_digest
  from `show`. It activates intent and proposed execution policy together, without a second prompt.
- Events use `apply --state <path> --event <json>` with id, op, actor, mission_id, expected_revision;
  cycle events add cycle_id and L2 events add session_id. Record actual evidence. Identical event
  retries are idempotent; changed content under the same ID fails. Persist then reconcile delivery.
- Development flow: `start → ready → approve → go → result → accept → close → evaluate`.
  `start` binds session_id, goal, checkpoint_ref, explicit reuse and verified capabilities
  (persistent_session, decision_relay, nested_agents, explicit_procedure_loading). Reuse also
  needs session_resumable and sufficient context. `ready`/`approve` use the exact digest from
  `digest --docs-dir <repo>/.dryforge`; changed docs invalidate approval. Record decision basis.
  The external controller records `go` at dispatch; do not pre-advance it.
- `result` records approved digest, commit, result_ref, checks (command/exit_code/observed),
  independent review (independent/evidence_ref), empty blockers and children_quiescent.
  Inspect this evidence before `accept`. Corrections use `rework` with approved digest, basis
  and feedback_ref, then an ordinary message to the same L2. `close` needs archive_ref,
  checkpoint_ref and children_quiescent; `evaluate` records decision, progress and basis.
  COMPLETE additionally requires success_evidence for every criterion.
- Migration uses `start(kind=migration, reuse=false)` with need_ref, then result/accept/close/evaluate.
  Digest the actual changed doc paths with `migration-digest --workspace <repo> --paths-file <json>`;
  record paths/digest and the same check/review evidence in result. Accept the exact digest.
  Close with handoff_ref, checkpoint_ref and children_quiescent after the authorized docs commit.
- `question` records request_id, question and authority scope; `answer` records that ID, answer
  and decision basis. `interrupt` is a host event; after reconciliation `resume` uses the same
  session_id, reconciled=true and checkpoint_ref. An active-cycle `abort` requires the human,
  basis, checkpoint_ref and quiescent children. `observe` records host events, never approvals.
- For an approved change to goal, success_criteria, constraints, priorities or non_goals, record
  one `amend` event at a cycle boundary: actor=human, patch, actual approval_ref, reviewed basis
  and expected_intent_digest from `show`. History, workers, consumed limits and pause status stay
  intact. This cannot change authority, workspace or budgets. In-scope clarification needs no amendment.
- Old extension records are historical evidence. New skill_* workflows are removed. If `show`
  reports pending legacy_extensions, explicitly retire each via `skill_cancel` (L1, request_id,
  basis) at a cycle boundary before proceeding. Cancellation does not approve its proposal or
  resolve a product question; retain the evidence and settle any consequential open decision.

## Execution scope

L1 decides exact requests within the user's reviewed grant. Policy eligibility alone is not a
reason to allow a command. Ready approval and tool authority are distinct, but can be included
in one user handoff. Preserve host controls and explicit human-only decisions; do not expand
an old grant by relabeling its version. Current existing-project Go uses policy v4:

```json
{
  "version": 4,
  "operations": ["workspace_edit", "git_add", "git_commit", "verify", "git_checkout",
                 "git_worktree_add", "git_merge", "git_worktree_remove", "git_branch_delete"],
  "paths": ["src", "tests", "README.md", "AGENTS.md", "CLAUDE.md", "docs", ".gitignore"],
  "verification_commands": [["python3", "-B", "-m", "unittest", "discover", "-v"]],
  "trust_workspace_code": true,
  "go_worktrees": true,
  "go_workflow": {"integration_branch": "main", "cycle_branch_prefix": "dryforge/",
                  "task_branch_prefix": "dryforge/task-"}
}
```

This is an example, not consent: choose actual task paths, tests and needed operations. Trusting
project code covers effects of tests and Git hooks; this runtime is not a security sandbox.
File grants cover ordinary additions/updates, not protected metadata, deletion or arbitrary shell.
Git staging names explicit files; commits use `git commit -m`. Verification uses exact approved
argv. No force/reset/amend, push, install or permission expansion is inferred. The classifier
provides the actual eligible operation/reason. If rejected, inspect the reason and real effects;
use existing host/human authority where required rather than bypassing the classifier.

After Ready approval and before Go, record `bind_runtime` as L1 with basis, current policy_digest
and targets: cycle_branch, tasks (task-ID → branch), archive_dir. Pin the final integration tip;
select targets from the approved plan and send their names to L2 as ordinary caller instructions.
An inline-only cycle has an empty tasks map; greenfield may use main as the cycle branch.
For additional in-scope Go repair tasks, `bind_tasks` adds new IDs/branches under the same grant.

Only registered task worktrees under `.dryforge/worktrees/<task-id>` qualify; the runtime verifies
Git common-directory and reverse pointers, not just path names. Task changes merge to the cycle
branch. After result acceptance, the exact accepted cycle commit may merge into the unchanged
integration target. Cleanup requires clean, merged work; archive identity must remain unchanged.
Use the actual base/task cwd (Claude Git callbacks require explicit `git -C <root>`).

For an existing run, a human `runtime_policy` event grants/revokes scope using actual approval_ref,
basis, expected_policy_digest and policy (explicit null to revoke), plus cycle_id when active.
It changes neither the goal nor phase. For pending eligible requests use the answer fields above;
record and consumption both recheck policy, stage, documents and Git state. A mismatch needs a
new decision. Policy versions 1–3 keep their existing narrower scope.
