"""Static cross-stage checks for decision-first discovery and gated feasibility.

These tests verify skill *instructions* and generated copies; they do NOT prove
that an LLM follows the skill or that an external API integration works.
"""

from pathlib import Path
import unittest
from skill_text import skill_text

ROOT = Path(__file__).resolve().parent.parent
READY = ROOT / 'src/skills/ready'
GO = ROOT / 'src/skills/go'


def source(path: Path) -> str:
    return skill_text(path) if path.name == 'SKILL.md' else path.read_text(encoding='utf-8')


class FeasibilityContractTests(unittest.TestCase):
    def test_landscape_objective_scope_and_stopping(self):
        text = source(READY / 'references/landscape-scan.md')
        for item in (
            'Discovery determines the approach; implementation research determines the mechanism.',
            'Complete solutions:', 'Extensible solutions:', 'Building blocks:',
            'Problem-first:', 'Technology-first:',
            'Coverage', 'Evidence', 'Decision stability',
            'Failure to find is not evidence of impossibility',
        ):
            with self.subTest(item=item):
                self.assertIn(item, text)

    def test_three_dispositions_and_no_negative_inference(self):
        text = source(READY / 'references/landscape-scan.md')
        for item in ('`VERIFIED`', '`UNVERIFIED`', '`RULED_OUT`',
                     'specific route under stated constraints/version',
                     'does not', 'bounded'):
            with self.subTest(item=item):
                self.assertIn(item, text)

    def test_ready_stage_requires_targeted_research_and_spike(self):
        skill = source(READY / 'SKILL.md')
        for item in ('## LANDSCAPE', '## ELICIT', '## PLAN',
                     'Coverage + Evidence + Decision stability',
                     'targeted\nimplementation research', 'first-task feasibility spike',
                     'stop-on-failure', '`UNVERIFIED`'):
            with self.subTest(item=item):
                self.assertIn(item, skill)
        self.assertLess(skill.index('## LANDSCAPE'), skill.index('## ELICIT'))
        self.assertLess(skill.index('## ELICIT'), skill.index('## PLAN'))

    def test_no_user_decision_escapes_approval(self):
        elicitation = source(READY / 'references/elicitation.md')
        technical = source(READY / 'references/project-design-technical.md')
        rubric = source(READY / 'references/first-cycle-review.md')
        self.assertIn('explicitly approve', elicitation)
        self.assertIn('negative result → stop and return to user', elicitation)
        self.assertIn('no `assumed` slot survives', source(READY / 'SKILL.md'))
        self.assertIn('No open user-owned technical decision remains', technical)
        self.assertIn('factual feasibility', rubric)

    def test_three_doc_contract_and_graph_dependency(self):
        output = source(READY / 'references/output-format.md')
        graph = source(READY / 'references/dependency-calc.md')
        gate = source(READY / 'references/3-doc-gate.md')
        self.assertIn('## Conditional feasibility', output)
        self.assertIn('**SPEC**', output)
        self.assertIn('**HANDOFF**', output)
        self.assertIn('**PLAN**', output)
        self.assertIn('no new graph keys', output)
        self.assertIn('every task that assumes', graph)
        self.assertIn('a verifiable feasibility spike', gate)

    def test_go_must_stop_without_switch_or_retry(self):
        skill = source(GO / 'SKILL.md')
        orch = source(GO / 'references/orchestration.md')
        implementer = source(GO / 'references/implementer-prompt.md')
        self.assertIn('Prove feasibility before reliance', skill)
        self.assertIn('## Feasibility-first gate', orch)
        self.assertIn('do not auto-switch', orch)
        self.assertIn('do not** apply the bounded', orch)
        self.assertIn('negative experiment', implementer)
        self.assertIn('expected outcome', implementer)
        self.assertIn('`BLOCKED`', implementer)

    def test_no_new_graph_fields_in_go_contract(self):
        graph = source(GO / 'references/graph-contract.md')
        self.assertIn('`depends`', graph)
        self.assertNotIn('feasibility:', graph)
        self.assertNotIn('spike:', graph)

    def test_platform_mirrors_all_updated_source_files(self):
        packages = (
            'claude/skills', 'codex/plugin/skills', 'grok/skills',
            'agent-plugin/skills', 'antigravity/skills',
        )
        files = (
            'ready/references/landscape-scan.md',
            'ready/references/elicitation.md',
            'ready/references/output-format.md',
            'ready/references/first-cycle-review.md',
            'go/references/orchestration.md',
            'go/references/implementer-prompt.md',
        )
        for rel in files:
            expected = (ROOT / 'src/skills' / rel).read_bytes()
            for package in packages:
                with self.subTest(rel=rel, package=package):
                    self.assertEqual(expected, (ROOT / package / rel).read_bytes())


if __name__ == '__main__':
    unittest.main()
