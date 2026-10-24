"""Packaging and authored policy checks, separate from live agent execution."""
import unittest
from pathlib import Path
from skill_text import skill_text

ROOT=Path(__file__).resolve().parents[1]
PACKAGES=('claude/skills','codex/plugin/skills','grok/skills','agent-plugin/skills','antigravity/skills')


class MissionContractTest(unittest.TestCase):
    def test_public_entrypoints_separate_discussion_and_execution(self):
        for package in ('src/skills', *PACKAGES):
            root = ROOT/package
            self.assertFalse((root/'mission').exists())
            self.assertTrue((root/'init/SKILL.md').is_file())
            self.assertTrue((root/'approve/SKILL.md').is_file())
        init = (ROOT/'src/skills/init/SKILL.md').read_text()
        approve = (ROOT/'src/skills/approve/SKILL.md').read_text()
        self.assertIn('references/interview.md', init)
        self.assertIn('Do not launch cycle workers', init)
        self.assertIn('expected_proposal_digest', approve)
        self.assertIn('../init/references/orchestration.md', approve)
        self.assertIn('conversation remains open', init)

    def test_mission_is_one_cycle_not_a_sector_loop(self):
        t=(ROOT/'src/skills/init/references/orchestration.md').read_text()
        for s in ('one ready-go cycle','not** an','same L2 session','REUSE','SPAWN','migration','CONTINUE','REPLAN','ESCALATE','COMPLETE'):
            self.assertIn(s,t)

    def test_ready_go_do_not_identify_their_decision_provider(self):
        for skill in ('ready','go'):
            t=(ROOT/f'src/skills/{skill}/SKILL.md').read_text()
            self.assertIn('## Caller interface',t)
            self.assertNotIn('../init/references/cycle-contract.md',t)
            self.assertNotIn('Mission mode',t)
            self.assertNotIn('L1',t)

    def test_go_lifecycle_preserves_original_dispatch(self):
        t=skill_text(ROOT/'src/skills/go/SKILL.md')
        for s in ('agent-lifecycle.md','single-task `MECHANICAL`/`NONE`','single `RISKY`','≤8','Final review'):
            self.assertIn(s,t)
        t=(ROOT/'src/skills/go/references/agent-lifecycle.md').read_text()
        for s in ('RESUME','SPAWN','FRESH_REVIEW','same task','worktree pool','negative feasibility'):
            self.assertIn(s,t)

    def test_no_auto_approval_hook_claim(self):
        t=(ROOT/'src/skills/init/references/host-adapter.md').read_text()
        self.assertIn('No auto-go-on-stop hook',t)
        self.assertIn('SDK controller',t)
        self.assertIn('runtime-bridge.md',t)
        self.assertIn('not certified',t)
        self.assertIn('AskUserQuestion',t)

    def test_platform_mission_files_identical(self):
        source=ROOT/'src/skills/init'
        for f in source.rglob('*'):
            if not f.is_file() or f.name=='SKILL.md':continue
            for package in PACKAGES:
                target=ROOT/package/'init'/f.relative_to(source)
                with self.subTest(path=str(target)):
                    self.assertEqual(f.read_bytes(),target.read_bytes())

    def test_lifecycle_and_modified_references_mirrored(self):
        for rel in ('go/references/agent-lifecycle.md','go/references/orchestration.md',
                    'go/references/implementer-prompt.md','go/references/reviewer-prompt.md'):
            for package in PACKAGES:
                self.assertEqual((ROOT/'src/skills'/rel).read_bytes(),(ROOT/package/rel).read_bytes())

    def test_readmes_link_mission_and_keep_optional_mcp(self):
        for language in ('','_ko'):
            t=(ROOT/f'README{language}.md').read_text()
            for token in ('/init','docs/MISSION.md','Context7 MCP','Grep MCP','Optional'):
                self.assertIn(token.lower(),t.lower())

    def test_preserved_workflows_are_loaded_and_mirrored(self):
        for skill in ('ready','go'):
            entry=(ROOT/f'src/skills/{skill}/SKILL.md').read_text()
            self.assertIn('Force-load the complete `references/workflow.md`',entry)
            source=(ROOT/f'src/skills/{skill}/references/workflow.md').read_bytes()
            for package in PACKAGES:
                self.assertEqual(source,(ROOT/package/skill/'references/workflow.md').read_bytes())

    def test_packaged_cli_is_runnable(self):
        import subprocess
        import sys
        for package in PACKAGES:
            result=subprocess.run([sys.executable,str(ROOT/package/'init/scripts/mission_state.py'),'--help'],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)


if __name__=='__main__':unittest.main()
