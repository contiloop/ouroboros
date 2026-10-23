"""Read the actual entrypoint plus its mandatory preserved procedure for contract tests."""
from pathlib import Path


def skill_text(path: Path) -> str:
    entry = path.read_text(encoding="utf-8")
    if "references/workflow.md" in entry:
        assert "Force-load the complete" in entry, "workflow must not become optional"
        return entry + "\n" + (path.parent / "references/workflow.md").read_text(encoding="utf-8")
    return entry
