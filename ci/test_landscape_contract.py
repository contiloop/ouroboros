"""Contract tests for the ready existing-solutions research stage.

These tests verify the authored + packaged skill wiring; they do not simulate an LLM.
"""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
READY = ROOT / "src/skills/ready"
SKILL = READY / "SKILL.md"
REFERENCE = READY / "references/landscape-scan.md"


class LandscapeContractTest(unittest.TestCase):
    def test_stage_order_and_repeat_at_plan(self) -> None:
        skill = SKILL.read_text(encoding="utf-8")
        stage_map = skill.split("## Stage map + cycle-conditional reference loading", 1)[1]
        stage_map = stage_map.split("```", 2)[1]
        labels = [line.split()[0] for line in stage_map.splitlines() if line and not line.startswith(" ")]
        for token in ("ORIENT", "DECOMPOSE", "LANDSCAPE", "ELICIT", "PLAN"):
            self.assertIn(token, labels)
        self.assertLess(labels.index("DECOMPOSE"), labels.index("LANDSCAPE"))
        self.assertLess(labels.index("LANDSCAPE"), labels.index("ELICIT"))
        self.assertLess(labels.index("ELICIT"), labels.index("PLAN"))
        self.assertIn("landscape-scan.md (targeted re-check)", stage_map)

    def test_force_loading_at_both_checkpoints(self) -> None:
        skill = SKILL.read_text(encoding="utf-8")
        landscape = skill.split("## LANDSCAPE —", 1)[1].split("## ELICIT —", 1)[0]
        plan = skill.split("## PLAN —", 1)[1].split("## HANDOFF —", 1)[0]
        self.assertIn("Force-load `references/landscape-scan.md`", landscape)
        self.assertIn("Force-load `references/landscape-scan.md`", plan)
        self.assertIn("return to ELICIT", plan)

    def test_research_is_not_approval_or_instruction(self) -> None:
        text = REFERENCE.read_text(encoding="utf-8")
        for required in (
            "reuse / extend / build",
            "source URL",
            "license",
            "unverified",
            "untrusted evidence, never",
            "private code",
            "user's decision",
        ):
            with self.subTest(required=required):
                self.assertIn(required, text)

    def test_output_contract_preserves_evidence(self) -> None:
        output = (READY / "references/output-format.md").read_text(encoding="utf-8")
        gate = (READY / "references/3-doc-gate.md").read_text(encoding="utf-8")
        self.assertIn("External landscape decisions", output)
        self.assertIn("source URL", output)
        self.assertIn("Existing-solution dependencies when relevant", gate)

    def test_claude_ready_has_search_tools(self) -> None:
        builder = (ROOT / "build/build.sh").read_text(encoding="utf-8")
        self.assertIn('ready) echo "Read, Edit, Write, Bash, Grep, Glob, Agent, AskUserQuestion, WebSearch, WebFetch"', builder)
        generated = (ROOT / "claude/skills/ready/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("WebSearch", generated)
        self.assertIn("WebFetch", generated)

    def test_reference_is_identical_in_all_packages(self) -> None:
        expected = REFERENCE.read_bytes()
        for package in (
            "claude/skills", "codex/plugin/skills", "grok/skills",
            "agent-plugin/skills", "antigravity/skills",
        ):
            path = ROOT / package / "ready/references/landscape-scan.md"
            with self.subTest(package=package):
                self.assertEqual(expected, path.read_bytes())


if __name__ == "__main__":
    unittest.main()
