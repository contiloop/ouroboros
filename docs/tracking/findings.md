# Findings

## Translated READMEs lag the English one
- **Observed:** `README_ko.md`, `README_ja.md`, `README_zh.md` only had false sentences removed and
  carry a note that the English README is current; their prose still describes the older
  orchestration wording in places.
- **Why it matters:** non-English readers get a thinner picture of the rebuilt model.
- **Why not now:** full translations are scheduled with the release (tracking item 3) so they are
  written once, after the live run has settled the wording.

## `session-wait` relies on pid liveness, not the exit file
- **Observed:** `alive()` answers from `os.kill(pid, 0)`; the wrapper writes `turns/<n>.exit` on
  exit but the adapter does not consult it for liveness.
- **Why it matters:** a reused pid could make a finished turn look RUNNING until the unrelated
  process exits. Rare on a developer machine.
- **Why not now:** no live run has exercised long turns yet; revisit with the evidence from
  tracking item 1.
