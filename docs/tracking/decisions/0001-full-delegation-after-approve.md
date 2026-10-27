# 0001 — Full delegation after `approve`

## Context
The current runtime hands the user one approval but then still routes many actions back to the
human: a `human_only` set (`merge`, `deploy`, `spend`, `delete`, `disclose`), per-call tool
permission policies with allow-listed paths and exact verification argv, separate human grants for
worktrees and merges. In practice this means the user is interrupted during execution, which
contradicts the product promise "hand over the work when you are ready".

## Decision
Approval is the one and only consent. After it, L1 may do anything the goal requires, including
merging, pushing, tagging, releasing, deleting its own branches and spending within the budget the
proposal stated. No category of action is reserved for the human during execution. The human is
asked again only when the approved goal itself must change or L1 is truly blocked.

## Alternatives
- **Keep per-call policy objects, default them to "allow everything in scope".** Rejected: keeps a
  large classifier whose only remaining job is to say yes; its Git-state checks would still refuse
  legitimate actions (e.g. force-free but off-branch commits) and keep interrupting.
- **Keep a small human-only set (push/deploy).** Rejected by the user: the whole point of the handoff
  is that execution does not come back for consent.

## Consequences
- The permission classifier (`runtime_permissions.py`, `runtime_git.py`, `runtime_cycle.py`,
  `runtime_merge.py`), policy versions 1–4 and the `runtime_policy`/`bind_runtime`/`bind_tasks`
  ledger operations have no role in the rebuilt system.
- Safety now rests on the quality of the `init` conversation (clear goal, criteria, limits) and on
  Dryforge's own gates inside each cycle, not on runtime interception.
- A proposal must state the budget and limits explicitly, because nothing else bounds L1 afterwards.
