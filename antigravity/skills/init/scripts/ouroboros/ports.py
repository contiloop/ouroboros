"""Host-session port: the fixed interface a host adapter implements so core and skill text never change per host.

An adapter drives one headless worker session (L2) of a coding-agent host. Every turn runs detached; the
adapter only launches, terminates and reads results. It never interprets the result, never answers
permission prompts, and never puts anything but the caller's message text in front of the host.
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
        """True while the turn's process is still running."""

    def terminate(self, turn: Turn) -> None:
        """Stop a running turn now (its whole process group). Idempotent on an exited turn."""

    def result(self, turn: Turn) -> dict:
        """Parse a finished turn's raw result: {state ∈ {COMPLETE, INTERRUPTED}, session_id, text, num_turns,
        cost_usd, permission_denials, is_error, subtype, raw_path}. `state` is a turn state, never a run
        status. Missing session id, non-zero exit or malformed output → INTERRUPTED (with `reason`)."""

    def doctor(self) -> dict:
        """Report the host prerequisites: {host, <executable>: path | null, version, dryforge: {installed, enabled}}.
        Reports, never refuses."""
