---
name: approve
description: >
  Hand the reviewed Ouroboros proposal to L1 when the user invokes ouroboros:approve. From here
  L1 runs installed Dryforge cycles on its own until the goal is met.
---

# Hand execution to L1

This invocation is the user's approval of the four documents (`scenario.md`, `validation.md`,
`spec.md`, `delegation.md`) **exactly as last shown**. Reply in the user's language. Load
`../init/references/runtime.md` for the commands.

1. On Codex (or any host other than Claude Code) report that no worker adapter exists for this host
   yet and stop; nothing is recorded as approved. Claude Code is the supported execution host.
2. Run `approve`. The record checks the set is complete (every required item of the four files;
   a refusal names the file and the item: go back to `init` and fill it) and compares it with the
   version marked `shown`:
   - nothing proposed → say so and start the `init` conversation;
   - changed since it was shown → show the user the difference per file; nothing is approved until
     they see the current version and invoke `approve` again;
   - equal → the run is `ACTIVE` (or, for a changed proposal on an active or stopped run, an
     amendment is recorded and applied at the next cycle boundary); a stopped run approved again
     resumes, with or without a changed proposal.
3. Repeating `approve` on an active run with an unchanged proposal changes nothing.
4. Recording `ACTIVE` is not execution. Load the complete `../init/references/orchestration.md` and
   begin the loop now, in this session.

After approval there is no further consent step: L1 answers worker questions, approves Ready
documents, merges, pushes, spends within the stated budget and decides every other action the goal
requires. The user keeps talking; L1 folds clarification into the work and brings back only a
genuine change of goal or a blocker it cannot resolve. L1 records its own decisions as L1, never
as the user's.
