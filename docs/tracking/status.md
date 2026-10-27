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

Findings from the first live unattended run on Claude Code (2026-10-27/28, sample project
`~/Desktop/topmemo`, a macOS always-on-top memo app; the human side was played by the maintainer's
assistant session). The run went `init → approve → 2 development cycles → beta cycle → ESCALATE for
on-screen checks → COMPLETE`. Everything below is what the next cycle changes; the mechanism itself held.

1. **Remove the budget.** Claude Code runs on a subscription, so `budget usd` is only a list-price
   conversion. The run still stopped itself at 22 USD of a 20 USD limit and needed an amendment to
   continue. Drop the budget from `delegation.md` and the limits, the budget stop in `_settle`, and
   the spend accounting (keep `cost_usd` in turn results as information or drop it; decide in `ready`).
   Limits become max cycles and max stalled cycles only.
2. **Ask the models and effort in the interview.** `delegation.md` `Models` stays `default` unless
   asked; the interview should present L2/L3 model choices and an effort level with a recommendation.
   Apply effort with the host's `--effort` flag on the worker session (not yet passed by the adapter).
3. **Language.** Remove the "reply in the user's language" instruction from the skill text; keep one
   line that the four documents are written in English (the run produced Korean documents while the
   chat was English).
4. **Content completeness before approve, with re-asking.** `approve` checks structure only. Add an
   independent review of the four documents (an agent that did not author them) before approval; its
   findings are re-asked to the user by L1 until none remain; the passing review is recorded and
   `approve` requires it.
5. Then: Codex adapter; release (version bump, translated READMEs).

## Blockers

None recorded.
