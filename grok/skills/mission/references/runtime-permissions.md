# Scoped runtime decisions — L1 is the delegated decision provider

Load only when setting or using runtime-tool delegation. L2 need not change its question/approval
workflow based on whether its caller is human or AI. L1 may decide within human-granted authority;
it must not pretend its decision was made by the human. This is an optional execution-policy
attachment, not a change to mission intent, a new agent, or an automatic allow engine.

## One human grant, individual L1 decisions

Discuss the concrete workspace, paths, operations and trusted project code once. A human can
approve this attachment together with the initial mission contract; the two records need not
mean two user interruptions. Existing missions stay human-only until a grant is actually recorded.
Do not infer execution powers from `approve_ready`, a generic "build it", or a worker's request.

Example policy (illustrative, not consent):

```json
{
  "version": 1,
  "operations": ["git_add", "git_commit", "workspace_edit", "verify"],
  "paths": ["memo_cli", "tests"],
  "verification_commands": [["python3", "-m", "unittest", "discover", "-s", "tests"]],
  "trust_workspace_code": true
}
```

Choose paths from the actual approved task; these example directories are not universal defaults.
The effective workspace is the mission's pinned Git root. `paths` are literal relative roots,
not globs. `.` may be chosen explicitly, but protected metadata remains excluded. A permission
policy is a maximum scope, not proof that every matching operation serves the user's goal: L1
must inspect the exact request and decide whether it is warranted by the approved spec.

`trust_workspace_code` is an explicit acknowledgement, not a security check. Git can run configured
filters/hooks; tests and package scripts execute project code and may have side effects. An exact
argv/cwd match does NOT prove all effects remain local. Use delegation only in a trusted checkout,
retain the host's security controls, and require human review for unfamiliar code/configuration.
This same-user runtime cannot sandbox malicious L1/L2 code or authenticate a JSON principal.

### Supported scope

| Operation | Boundary |
| --- | --- |
| `git_add` | Existing explicit files within approved paths; optional `--`; no bulk `.`, globs, force, options, deletions or pathspec magic. |
| `git_commit` | Only `git commit -m <message>`; every staged path must be an allowed addition/modification. No amend, deletion, signing/config flags, rebase or merge. |
| `workspace_edit` | Claude Write/Edit/MultiEdit with an absolute path, or Codex file changes re-read from the exact host item; add/update only, no move/delete. |
| `verify` | Exact approved argv from recognized unittest/pytest/compileall or package-test entrypoints, in the workspace root. No arbitrary shell, install, publish or interpreter `-c`. |

Command callbacks require a host-observed workspace-root cwd, or explicit `git -C /absolute/root`.
Claude Bash lacks trusted cwd in the callback: use explicit `git -C` for delegated Git, otherwise
ask the human. A simple known shell `-c`/`-lc` wrapper is accepted, not command chains/expansion.
Linked worktrees/alternate Git metadata need a separate human decision in this first policy version.
Metadata `.git`, `.dryforge`, `.claude`, `.codex`, `.agents`, symlinks and parent traversal are not
ordinary file-write grants. Git's own index/commit updates are permitted only through matching Git
commands, never arbitrary writes into `.git`. Network/permission expansion, tool elicitation and
unknown operations remain human-only/denied under the existing adapter rules.

## Record or revoke authority

Use `scripts/mission_state.py apply --state <state.json> --event <event.json>` through the trusted
controller. Submit a `runtime_policy` event **only after actual human approval**. Required fields:

```text
id, op=runtime_policy, actor=human, mission_id, expected_revision,
expected_policy_digest, approval_ref, basis, policy
```

Set `expected_policy_digest` to SHA-256 of canonical JSON for the current `runtime_authority`
(or JSON `null` before the first grant). `mission_state.py show` reports `runtime_policy_digest`.
Include the exact `cycle_id` if a cycle is active; omit it when no cycle is active. `policy` is the
object above, or explicit `null` to revoke. Never edit state.json by hand or reset the mission.
L1 may prepare an event, but only the trusted human-decision path may submit a grant/revocation.

A grant can be recorded while a tool callback is waiting, including during Go. It does not alter
the Intent contract, approved 3-doc, session ID, stage, consumed budget or pause state. Each grant
has a new revision/event ID, so revoke-and-regrant does not revive an old queued approval. Human-
only restrictions in the contract (`runtime_permissions` or a named operation) take precedence.
The first runtime-policy event upgrades the ledger to schema 3; old code rejects it. Skill-interface
events preserve schema 3 and cannot grant runtime authority. Schema-1/2 missions still load.

## Decide on the pending request

`worker_runtime.py status` shows `pending[].delegation`. `eligible: true` is an eligibility hint,
not an approval. If it is false, read `reason`; do not change the request or pretend to be human to
make it pass. A genuine human decision remains possible through the existing path.

For an eligible request that serves the approved task, L1 sends `answer --request-id <id>
--response-file <private-json>` with:

```text
principal=L1, action=allow, basis=<why this operation serves the approved task>,
session_id=<actual pending ID>, request_digest=<pending fingerprint>,
policy_digest=<pending.delegation.policy_digest>
```

Do not ask the human again merely because the request is a tool permission if the human already
delegated this exact scope. Conversely, matching paths do not authorize remote push/deployment or
any change to the final goal. Record refusals as `action: deny`, not an invented human approval.
The host receives only its ordinary exact-call `accept`/allow response. Never use accept-for-session,
exec-policy/network amendments, bypass modes or persistent permission updates.

The runtime checks the active mission/cycle/session, unchanged intent, approved document digest,
no unresolved decision, current grant and exact host operation both at answer storage and just
before consumption. Revocation/stale scope denies the callback instead of forwarding an old allow.
`request.delegation_checked` audit events name the grant, operation, paths/argv and record/consume
phase; `request.answered` preserves principal and basis. Delivery/approval still does not prove
execution success. A local same-user filesystem can change after a check: these guards are not a
TOCTOU-proof security boundary or an alternative to host permissions.

## Updating a running installation

Plugin/package updates do not hot-reload an existing controller. For an old live worker: stop,
inspect effects and child sessions, then explicitly reconcile/resume the SAME host session on the
updated runtime. Old callbacks expire and must be reissued; never blindly replay an uncertain Git
operation. New installation alone grants nothing to existing contracts. Do not claim live Claude/
Codex verification from unit/protocol tests; test the target host's real callback before relying on it.
