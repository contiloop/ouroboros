"""Check the publicly installed identity separately from inherited on-disk state."""
import json
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

class OuroborosBrandingTest(unittest.TestCase):
    def test_canonical_plugin_identity(self):
        for p in (ROOT/'platform').glob('*/plugin*.json'):
            self.assertEqual(json.loads(p.read_text())['name'],'ouroboros',str(p))
    def test_marketplace_names(self):
        for relative in ('.agents/plugins/marketplace.json','.claude-plugin/marketplace.json',
                         '.grok-plugin/marketplace.json','.github/plugin/marketplace.json'):
            data=json.loads((ROOT/relative).read_text())
            self.assertEqual(data['name'],'ouroboros')
            self.assertEqual([p['name'] for p in data['plugins']],['ouroboros'])
    def test_codex_display_and_skill_call(self):
        for path in (ROOT/'platform/codex/skills').glob('*/agents/openai.yaml'):
            s=path.read_text()
            self.assertIn('Ouroboros',s)
            self.assertNotIn('Dryforge',s)
    def test_readme_identity_architecture_and_limits(self):
        for path in (ROOT/'README.md',ROOT/'README_ko.md'):
            s=path.read_text()
            self.assertIn('# ⟲ Ouroboros',s)
            for token in ('L1','L2','L3','/ouroboros:mission','docs/MISSION.md','Grep MCP','Context7 MCP'):
                self.assertIn(token,s)
            self.assertIn('Apache-2.0',s)
            self.assertIn('prekuter',s) # keep attribution
    def test_legacy_state_is_preserved(self):
        self.assertIn('.dryforge/', (ROOT/'src/skills/go/SKILL.md').read_text())
        self.assertTrue((ROOT/'README.upstream.md').exists())
        self.assertTrue((ROOT/'LICENSE').exists())

if __name__=='__main__': unittest.main()
