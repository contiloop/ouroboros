# 0011 — Client-grade interview, independent reviews before approve, no budget, L1-chosen models and effort

## Context
The first live unattended run (2026-10-27/28, `~/Desktop/topmemo`) completed, but: the run stopped
itself on a USD budget that is only a list-price conversion on a subscription host; the four
documents came out in Korean while the chat was English; the interview asked the user technical
questions; and `approve` checked structure only, so thin documents passed.

## Decision
- **The user is a client, not a developer.** The interview asks only what a client would know;
  technical choices are L1's, presented only when they change the user's experience, in plain
  words. Validation items are written by L1 and confirmed by the user as "this is what I will check".
- **No budget.** Limits are max cycles and max stalled cycles. Per-turn cost stays in turn results as
  information; nothing acts on it.
- **Models and effort are L1's call**, recorded in `delegation.md` (`effort:` uses the host's levels
  or `default`, validated at approve) and applied to the worker session (`--model`, `--effort`,
  subagent model). L3 effort is not controlled.
- **English documents.** The "reply in the user's language" instruction is removed.
- **The interview follows fixed stages** (orient, decompose, elicit, L1-written validation,
  independent intent review, write + fidelity check, independent gate review, show, approve), and L1
  keeps a private interview log the reviewers read.
- **`approve` requires a passing gate review** recorded with `review`, bound to the content digest
  (scenario, validation, spec): always for a first approval, for amendments only when that content
  changed; never for an unchanged resume or a `delegation.md`-only change. Pass = zero open
  findings; a finding the user settles or L1 resolves technically is recorded with that
  disposition, so "zero open" is auditable rather than an override.

## Alternatives
- **Round cap with recorded override** for the review loop. Rejected: the user's answers can settle
  every finding, so no override is needed and `approve` stays strict.
- **Four-file digest for the review binding.** Rejected: a limits/models/effort change would force
  a new review although the user's design did not change.
- **Two Ouroboros effort words mapped by the adapter.** Rejected: a hidden mapping; the host's own
  levels are recorded instead.
- **A live probe of `--effort` in this cycle.** Deferred to the next live run.

## Consequences
- `core.approve` grows a gate rule; `review` is a new CLI command; `run.json` gains `effort` and
  `reviews[]`; `interview.md` joins the run files.
- Skill text names no model; the reviewers are "an independent agent of the host".
- Translated READMEs still lag (release item).
