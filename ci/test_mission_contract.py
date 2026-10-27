"""Packaging and authored policy checks, separate from live agent execution."""
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PACKAGES=('claude/skills','codex/plugin/skills','grok/skills','agent-plugin/skills','antigravity/skills')


class MissionContractTest(unittest.TestCase):
    def test_public_entrypoints_separate_discussion_and_execution(self):
        for package in ('src/skills', *PACKAGES):
            root = ROOT/package
            self.assertFalse((root/'mission').exists())
            self.assertTrue((root/'init/SKILL.md').is_file())
            self.assertTrue((root/'approve/SKILL.md').is_file())

    def test_platform_mission_files_identical(self):
        source=ROOT/'src/skills/init'
        for f in source.rglob('*'):
            if not f.is_file() or f.name=='SKILL.md':continue
            for package in PACKAGES:
                target=ROOT/package/'init'/f.relative_to(source)
                with self.subTest(path=str(target)):
                    self.assertEqual(f.read_bytes(),target.read_bytes())


if __name__=='__main__':unittest.main()
