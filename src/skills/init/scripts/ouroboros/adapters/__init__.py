"""Host adapters implementing `ports.HostSession`. `for_host(name)` is the only lookup the CLI uses."""
from __future__ import annotations

from ..ports import HostSession


def for_host(name: str) -> HostSession:
    if name == 'claude':
        from .claude import ClaudeAdapter
        return ClaudeAdapter()
    raise ValueError(f'no host adapter for {name!r}; supported: claude')
