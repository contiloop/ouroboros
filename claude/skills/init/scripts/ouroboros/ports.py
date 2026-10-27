"""Host-session port: the fixed interface a host adapter implements so core and skill text never change per host.

An adapter drives one headless worker session (L2) of a coding-agent host. Every turn runs detached; the
adapter only launches, terminates and reads results. It never interprets the result, never answers
permission prompts, and never puts anything but the caller's message text in front of the host.
"""
from __future__ import annotations

from pathlib import Path
from typing import Protocol


class Turn(Protocol):
    """Handle of one launched turn: the host process and the file its raw result is written to."""

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

    def terminate(self, turn: Turn) -> None:
        """Stop a running turn now (its whole process group). Idempotent on an exited turn."""

    def result(self, turn: Turn) -> dict:
        """Parse a finished turn's raw result: {state ∈ {COMPLETE, INTERRUPTED}, session_id, text, num_turns,
        cost_usd, permission_denials, is_error, subtype, raw_path}. `state` is a turn state, never a run
        status. Missing session id, non-zero exit or malformed output → INTERRUPTED."""
