# 0009 — Structured questions through the control channel; remaining permission requests auto-allowed

## Context
In plain headless mode (`claude -p`) the session has no question tool, so Dryforge asks in prose and
the turn ends. A probe on 2026-10-27 showed that a session started with `--input-format stream-json
--output-format stream-json --permission-prompt-tool stdio` has the question tool: each call arrives
as a `can_use_tool` control request on stdout and is answered by a control response on stdin. The
installed skill still loads from a `/dryforge:<kind>` message on stdin, and `--resume` works.

## Decision
L2 turns run through that channel under a small relay process. A structured question becomes a
`QUESTION` turn state with the questions and options; L1 answers it with `session-answer`, and the
answer is fed back so the turn continues. Question and answer are recorded automatically. Permission
requests for anything other than the question tool are allowed by the relay at once and recorded; the
user's deny rules remain the boundary. If L1 disappears while a question is open, the worker keeps
waiting and the next L1 takes the question over. The mechanism was proposed by L1 (the producer of
the cycle) and accepted by the user; the auto-allow and the keep-waiting rules were the user's choices.

## Alternatives
- **Plain-text questions only (cycle 001).** Kept as the fallback, but the structured path gives L1
  the options and the recommendation Dryforge intends, and matches what a human caller sees.
- **Interactive terminal session driven by L1.** Rejected: driving a terminal UI is fragile and
  unnecessary once the channel exists.
- **Route remaining permission requests to L1 or deny them.** Rejected by the user: after approval
  L1 holds every permission, so a round trip per request only adds latency, and denial would stall
  cycles.

## Consequences
- The allow-list is no longer a ceiling (decision 0008 amended): the deny rules are.
- `AskUserQuestion` must never be allow-listed, or questions stop reaching the channel.
- The host reports a cumulative session cost per turn; the runtime charges the delta.
- Verified once on the real host (2026-10-27): two question rounds in one Ready turn, a single-label
  answer echoed back, and a session stopped mid-question resumed with the same id. Multi-select and
  free-text answers are not yet host-verified.
