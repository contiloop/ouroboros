"""Contract tests for the ready existing-solutions research stage.

These tests verify the authored + packaged skill wiring; they do not simulate an LLM.
"""

from __future__ import annotations

import unittest
from skill_text import skill_text
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
READY = ROOT / "src/skills/ready"
SKILL = READY / "SKILL.md"
REFERENCE = READY / "references/landscape-scan.md"


class LandscapeContractTest(unittest.TestCase):
    def test_stage_order_and_repeat_at_plan(self) -> None:
        skill = skill_text(SKILL)
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
        skill = skill_text(SKILL)
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
        self.assertIn('ready) echo "Read, Edit, Write, Bash, Grep, Glob, Agent, AskUserQuestion, WebSearch, WebFetch, SendMessage"', builder)
        generated = (ROOT / "claude/skills/ready/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("WebSearch", generated)
        self.assertIn("WebFetch", generated)

    def test_delegated_research_but_main_owns_intent(self) -> None:
        skill = skill_text(SKILL)
        landscape = skill.split("## LANDSCAPE —", 1)[1].split("## ELICIT —", 1)[0]
        self.assertIn("read-only general-purpose research", landscape)
        self.assertIn("the main agent", landscape)
        self.assertIn("landscape-researcher-prompt.md", landscape)
        self.assertIn("two independent subagent audits", skill)

    def test_research_prompt_read_only_and_bounded(self) -> None:
        prompt = (READY / "references/landscape-researcher-prompt.md").read_text(encoding="utf-8")
        for token in ("Read-only", "Grep", "Context7", "untrusted evidence",
                      "EVIDENCE_READY", "BOUNDED_UNVERIFIED", "counter-evidence",
                      "private code", "Decision Stability"):
            self.assertIn(token.lower(), prompt.lower())

    def test_optional_host_mcp_setup_and_security(self) -> None:
        text = (ROOT / "docs/RESEARCH_MCP_SETUP.md").read_text(encoding="utf-8")
        for token in ("https://mcp.grep.app", "https://mcp.context7.com/mcp",
                      "claude mcp add", "codex mcp add", "plugin-provided agent",
                      "not merely", "without either server"):
            self.assertIn(token.lower(), text.lower())

    def test_preflight_before_delegation(self) -> None:
        skill = skill_text(SKILL)
        landscape = skill.split("## LANDSCAPE —", 1)[1].split("## ELICIT —", 1)[0]
        self.assertLess(landscape.index("run the Tool Preflight"), landscape.index("spawn **one"))
        for token in ("available", "unavailable", "unknown", "Never install",
                      "preflight tool-access snapshot", "research subagent"):
            self.assertIn(token.lower(), landscape.lower())

    def test_preflight_distinguishes_missing_from_unknown_and_has_fallback(self) -> None:
        scan = REFERENCE.read_text(encoding="utf-8")
        researcher = (READY / "references/landscape-researcher-prompt.md").read_text(encoding="utf-8")
        for token in ("## Tool preflight", "available", "unavailable", "unknown",
                      "subagent", "automatically available", "generic public",
                      "not required", "never", "UNVERIFIED"):
            self.assertIn(token.lower(), scan.lower())
        for token in ("## Tool-access confirmation", "preflight snapshot",
                      "actually callable", "install", "tool_access", "fallback"):
            self.assertIn(token.lower(), researcher.lower())

    def test_all_readmes_recommend_optional_mcp_setup(self) -> None:
        for language in ("", "_ko", "_ja", "_zh"):
            readme = (ROOT / f"README{language}.md").read_text(encoding="utf-8")
            with self.subTest(language=language or "en"):
                for token in ("Grep MCP", "Context7 MCP", "Optional",
                              "docs/RESEARCH_MCP_SETUP.md"):
                    self.assertIn(token.lower(), readme.lower())
        setup = (ROOT / "docs/RESEARCH_MCP_SETUP.md").read_text(encoding="utf-8")
        self.assertIn("## Tool preflight at runtime", setup)
        self.assertIn("never installs MCP servers", setup)

    def test_reference_is_identical_in_all_packages(self) -> None:
        for name in ("landscape-scan.md", "landscape-researcher-prompt.md"):
            expected = (READY / "references" / name).read_bytes()
            for package in (
                "claude/skills", "codex/plugin/skills", "grok/skills",
                "agent-plugin/skills", "antigravity/skills",
            ):
                path = ROOT / package / "ready/references" / name
                with self.subTest(package=package, name=name):
                    self.assertEqual(expected, path.read_bytes())


if __name__ == "__main__":
    unittest.main()
