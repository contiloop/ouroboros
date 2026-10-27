"""Host-session port: the fixed interface a host adapter implements so core and skill text never change per host.

An adapter drives one headless worker session (L2) of a coding-agent host. Every turn runs detached; the
adapter launches, terminates and reads results, and relays the host's structured questions to the caller
as files. It never interprets the result and never puts anything but the caller's message text in front of
the host. Permission requests for tools outside the allow-list are allowed automatically and recorded
(`auto_allowed`); the host's own deny rules are applied before anything reaches the adapter. Questions are
never answered by the adapter: they wait, without a time limit, for `answer()`.

Turn states: RUNNING (the host process is alive), QUESTION (alive, one question bundle open), COMPLETE,
INTERRUPTED and STOPPED (exited). RUNNING and QUESTION are the live states.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class Turn:
    """Handle of one launched turn: the host process (group leader) and the file its raw result is written to.
    The CLI rebuilds it from the run record, so it carries nothing adapter-specific."""

    pid: int
    raw_path: Path


class HostSession(Protocol):
    """Start, continue, terminate and read turns of one host session."""

    def start(self, workspace: Path, message: str, raw_path: Path) -> Turn:
        """Launch a new session whose first user message is `message` (the leading `/dryforge:<kind>`
        selects the installed skill). Runs detached with cwd=workspace; the host's raw JSON result goes to
        `raw_path`. Returns immediately."""

    def send(self, workspace: Path, session_id: str, message: str, raw_path: Path) -> Turn:
        """Launch one more turn on the existing `session_id` with `message` as the user message."""

    def alive(self, turn: Turn) -> bool:
        """True while the turn's process is still running (RUNNING or QUESTION)."""

    def terminate(self, turn: Turn) -> None:
        """Stop a running turn now (its whole process group). Idempotent on an exited turn."""

    def questions(self, turn: Turn) -> dict | None:
        """The open question bundle of a live turn, {round, questions, request_id, tool_use_id}, or None.
        `questions` is the host's list of {question, header, options: [{label, description}], multiSelect}."""

    def answer(self, turn: Turn, round_: int, answers: dict) -> None:
        """Deliver the answers of bundle `round_` (question text → answer string in the host's wire form);
        the turn continues. The caller validates before calling."""

    def session_id(self, turn: Turn) -> str | None:
        """The session id the host announced for this turn, available while the turn is still live, or None
        until it is known."""

    def result(self, turn: Turn) -> dict:
        """Parse a finished turn's raw result: {state ∈ {COMPLETE, INTERRUPTED}, session_id, text, num_turns,
        cost_usd, cost_total_usd (the host's cumulative session total; the caller charges the delta as
        cost_usd), permission_denials, is_error, subtype, usage, raw_path, stderr_path, exit_code, reason,
        skills (the installed dryforge commands the host listed), auto_allowed (permission requests allowed
        automatically: [{tool_name, tool_use_id}]), questions (answered bundles), stream_path}. `state` is a
        turn state, never a run status. Missing session id, non-zero exit or malformed output → INTERRUPTED
        (with `reason`)."""

    def doctor(self) -> dict:
        """Report the host prerequisites: {host, <executable>: path | null, version, dryforge: {installed, enabled}}.
        Reports, never refuses."""
