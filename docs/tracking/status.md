# Status

Snapshot as of 2026-10-28, branch `dryforge/cycle-004` (cycle 004) (v1.4.1 released 2026-10-24; an
`Unreleased` changelog section describes the rebuild).

## Direction

The project has been **rebuilt from its concept** (decision 0002). What stays: the L1/L2/L3 model,
`init` as an open-ended intent conversation, `approve` as the single human handoff, L1 invoking the
*installed* Dryforge, full L1 authority after approval. What went: the per-call permission model,
the five-schema ledger, the SQLite mailbox, the SDK/app-server adapters and the bundled
Dryforge-derived skills. Completion target: a real, unattended `init → approve → cycles → goal
complete` run on **Claude Code**. Codex follows; Grok, Agent Plugins and Antigravity stay
packaging-only.

## Built and verified

| Area | State | Evidence |
| --- | --- | --- |
| Bundled `ready`/`go`/`migration` removed, build guard and overlays dropped | done | `src/skills/` holds `init` and `approve` only; `ci/verify.py` passes |
| Run record (`run.json`, `events.jsonl`, owner, lock, archive) and record commands; the four-document proposal set with completeness checks, per-file diffs, models, beta cycle kind, legacy handling | built, unit-tested | `ci/test_run_record.py` |
| Claude Code host adapter: headless turns through the streaming control channel, resume, allow-list, relay, structured questions (`QUESTION` / `session-answer`), automatic allow of remaining permission requests, stop, doctor | built, unit-tested against a fake `claude`; smoke-run once against the real host (two question rounds, answer echoed, resume after a mid-question stop) | `ci/test_claude_adapter.py`; engineering notes |
| Skill text: the elicitation interview for the four documents, the work graph, whole-context worker messages, the beta test with human-only verification via ESCALATE, the question branch | written, contract-pinned | `ci/test_mission_contract.py`, `ci/test_runtime_contract.py` |
| Host facts the design rests on (skill loads headlessly, resume, allow-list behavior) | live-probed once on 2026-10-27 with claude 2.1.311 | probe results recorded in the engineering notes |
| README and product docs for the new model | done; translations patched minimally | `ci/test_ouroboros_branding.py` |
| Five-platform build, manifest/version/marketplace validation, reproducible-build check | passes | `build/build.sh`, `ci/verify.py` |
| First live unattended run on Claude Code (2026-10-27/28, `~/Desktop/topmemo`): `init → approve → 2 development cycles → beta cycle → ESCALATE for on-screen checks → COMPLETE` | done; the mechanism held | engineering notes ("First live unattended run") |
| Cycle 004: budget removed (limits = max cycles, max stalled cycles; cost kept as information), `effort` in `delegation.md` validated and passed as `--effort`, English documents, the client interview stage for stage with the interview log, `review` command, `approve` requires a passing gate review bound to the content digest (decision 0011) | built, unit-tested | `ci/test_run_record.py`, `ci/test_claude_adapter.py`, `ci/test_mission_contract.py` |

## Remaining (in order)

1. **Second live unattended run on Claude Code** with the cycle-004 interview: a client-only
   dialogue, both independent reviews recorded, `approve` refusing until the gate passes, English
   documents, no budget stop. Observe whether the headless resumed session honors `--effort`
   (record the observation in the engineering notes) and whether L3 effort needs control.
2. Codex adapter.
3. Release: version bump (ten manifests + CHANGELOG heading + tag), translated READMEs.

## Blockers

None recorded.
