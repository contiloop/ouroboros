"""Portable packaging and policy integration; not live LLM behavior validation."""
from pathlib import Path
import subprocess
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
PACKAGES=('claude/skills','codex/plugin/skills','grok/skills','agent-plugin/skills','antigravity/skills')


class SkillInterfaceContractTest(unittest.TestCase):
    def test_reference_is_loaded_only_at_optional_boundary(self):
        entry=(ROOT/'src/skills/init/references/orchestration.md').read_text()
        self.assertIn('Optional skill boundary',entry)
        self.assertIn('references/skill-interface.md',entry)
        self.assertIn('at that point',entry)
        self.assertIn('No extension is mandatory',entry)
        self.assertIn('PROPOSE → REVIEW → APPROVE → COMMIT',entry)
        for skill in ('ready','go'):
            self.assertNotIn('skill-interface.md',(ROOT/f'src/skills/{skill}/SKILL.md').read_text())

    def test_original_philosophy_has_operational_constraints(self):
        s=(ROOT/'src/skills/init/references/skill-interface.md').read_text()
        for token in ('Floor, not ceiling','Enumerate ≠ ask','Work-changing','Evidence over self-report',
                      'same event ID','original words','not authentication','cycle boundary',
                      'No registry','UNVERIFIED'):
            self.assertIn(token,s)

    def test_interface_and_validator_mirrored_in_all_packages(self):
        for rel in ('references/skill-interface.md','scripts/skill_contract.py'):
            source=(ROOT/'src/skills/init'/rel).read_bytes()
            for package in PACKAGES:
                self.assertEqual(source,(ROOT/package/'init'/rel).read_bytes())

    def test_packaged_validator_is_standalone(self):
        for package in PACKAGES:
            proc=subprocess.run([sys.executable,str(ROOT/package/'init/scripts/skill_contract.py'),'--help'],
                                text=True,capture_output=True)
            self.assertEqual(proc.returncode,0,proc.stderr)

    def test_guides_distinguish_interface_from_installed_skill(self):
        s=(ROOT/'docs/SKILL_INTERFACE.md').read_text()
        for token in ('not a new agent runtime','No Interview implementation',
                      'schema 2','schema 1','64 KiB','trusted runtime', 'human approval'):
            self.assertIn(token,s)
        self.assertFalse((ROOT/'src/skills/interview').exists())


if __name__=='__main__':unittest.main()
