"""Packaging and authored policy checks for the skill text, separate from live agent execution."""
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PACKAGES=('claude/skills','codex/plugin/skills','grok/skills','agent-plugin/skills','antigravity/skills')
SKILL_TEXT=('init/SKILL.md','approve/SKILL.md','init/references/interview.md',
            'init/references/orchestration.md','init/references/runtime.md')


def text(rel):
    return (ROOT/'src/skills'/rel).read_text(encoding='utf-8')


class MissionContractTest(unittest.TestCase):
    def test_public_entrypoints_separate_discussion_and_execution(self):
        for package in ('src/skills', *PACKAGES):
            root = ROOT/package
            self.assertFalse((root/'mission').exists())
            self.assertTrue((root/'init/SKILL.md').is_file())
            self.assertTrue((root/'approve/SKILL.md').is_file())
            for legacy in ('ready','go','migration'):
                self.assertFalse((root/legacy).exists(), f'{package}/{legacy} must not ship')
        init=text('init/SKILL.md')
        for s in ('references/interview.md','references/runtime.md','.gitignore','Do not start any worker session','conversation stays open'):
            self.assertIn(s,init)
        approve=text('approve/SKILL.md')
        for s in ('exactly as last shown','../init/references/orchestration.md','no further consent','Codex'):
            self.assertIn(s,approve)

    def test_loop_vocabulary_and_commands(self):
        t=text('init/references/orchestration.md')
        for s in ('/dryforge:ready','/dryforge:go','/dryforge:migration','same','session-wait','background',
                  'CONTINUE','REPLAN','ESCALATE','COMPLETE','session-stop','stop --reason abort','doctor',
                  '--fresh','cycle-start','evaluate','$CLAUDE_PID','QUESTION','session-answer'):
            self.assertIn(s,t)
        self.assertNotIn('--kind question',t)
        r=text('init/references/runtime.md')
        for cmd in ('doctor','draft','shown','show','approve','cycle-start','cycle-stage','evaluate','event',
                    'stop','archive','session-start','session-send','session-wait','session-answer','session-status','session-stop'):
            self.assertIn(f'`{cmd}',r)
        self.assertIn('budget',text('init/references/interview.md'))

    def test_legacy_wording_is_gone(self):
        for rel in SKILL_TEXT:
            t=text(rel)
            for s in ('human-only','runtime_policy','bind_runtime','worker_runtime.py','mission_state.py',
                      'runtime-bridge.md','ouroboros:ready','ouroboros:go','bundled','policy v','SDK',
                      'bypassPermissions','dangerously-skip'):
                self.assertNotIn(s,t,f'{rel} still mentions {s!r}')

    def test_frontmatter_has_no_host_keys(self):
        for rel in ('init/SKILL.md','approve/SKILL.md'):
            head=text(rel).split('---')[1]
            self.assertIn('name: '+rel.split('/')[0],head)
            self.assertIn('description:',head)
            for key in ('allowed-tools','disable-model-invocation'):
                self.assertNotIn(key,head)

    def test_platform_mission_files_identical(self):
        source=ROOT/'src/skills/init'
        for f in source.rglob('*'):
            if not f.is_file() or f.name=='SKILL.md':continue
            for package in PACKAGES:
                target=ROOT/package/'init'/f.relative_to(source)
                with self.subTest(path=str(target)):
                    self.assertEqual(f.read_bytes(),target.read_bytes())


if __name__=='__main__':unittest.main()
