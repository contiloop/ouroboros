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

0. **Governing principle for the interview (the user's words):** the user is a client, not a
   developer. They know what they want, when and how it is used, how it should look and feel, and
   what would satisfy them; they do not need to know the technology. L1 is the expert who knows the
   technology and the code and decides everything else. So the interview asks only what a client
   would know (scenarios, observable conditions, taste and references, priorities); technical
   choices are L1's, presented to the user only when they change the user's experience and then in
   plain words. Validation items are written by L1 from the scenarios and shown to the user as
   "this is what I will check" for confirmation; environment, evidence and efficient checks are L1's.
   Questions from the independent reviews pass the same filter.
1. **Remove the budget.** Claude Code runs on a subscription, so `budget usd` is only a list-price
   conversion. The run still stopped itself at 22 USD of a 20 USD limit and needed an amendment to
   continue. Drop the budget from `delegation.md` and the limits, the budget stop in `_settle`, and
   the spend accounting (keep `cost_usd` in turn results as information or drop it; decide in `ready`).
   Limits become max cycles and max stalled cycles only.
2. **Models and effort are L1's call.** L1 picks the L2/L3 models and an effort level as the expert
   (recorded in `delegation.md`), tells the user in one line that they can be changed, and asks at
   most one plain-language choice ("quick and light" vs "thorough") when it matters. Apply effort
   with the host's `--effort` flag on the worker session (not yet passed by the adapter).
3. **Language.** Remove the "reply in the user's language" instruction from the skill text; keep one
   line that the four documents are written in English (the run produced Korean documents while the
   chat was English).
4. **Content completeness before approve, with re-asking.** `approve` checks structure only. Add an
   independent review of the four documents (an agent that did not author them) before approval; its
   findings are re-asked to the user by L1 until none remain; the passing review is recorded and
   `approve` requires it. Model the whole interview on Dryforge `ready`'s stages, stage for stage:
   orient → decompose the user's words into the four documents' axes (conflicts become questions) →
   elicit (decision surface, extract domain / present technical, grounds gate, ≤4 questions with a
   recommendation) → independent intent-completeness subagent (guess hunt, findings re-asked) →
   write the four documents + fidelity check → independent gate subagent on the finished documents
   (executability, contract consistency; findings re-asked) → `approve`. Both independent checks are
   recorded in the run and `approve` requires the last one to have passed on the shown set.
5. Then: Codex adapter; release (version bump, translated READMEs).

## Blockers

None recorded.
