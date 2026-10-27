# Status

Snapshot as of 2026-10-27, branch `dryforge/four-doc-proposal` (cycle 003) (v1.4.1 released 2026-10-24; an
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

## Remaining (in order)

1. **Live run on Claude Code:** `init → approve → ≥2 cycles → COMPLETE` with no human input after
   approve, on a trusted sample project with Dryforge installed. Record commands, exit codes and
   observed behavior in the engineering notes and this file. Expect to tune `MAX_TURNS`, when to
   start a fresh session (the parsed result carries `usage`), and the proposal wording from what
   the run shows. Also host-verify multi-select and free-text answers, and watch how well the
   interview fills the four documents on a real goal.
2. **Codex adapter** behind the same `HostSession` port (`codex exec` or app-server), then a live
   run on Codex.
3. **Release:** version bump in the five manifests, changelog heading, full rewrites of
   `README_ko.md`, `README_ja.md`, `README_zh.md`.

## Blockers

None recorded.
