"""Packaged runtime boundary checks, not claims of live model compatibility."""
from pathlib import Path
import subprocess
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
PACKAGES=('claude/skills','codex/plugin/skills','grok/skills','agent-plugin/skills','antigravity/skills')
SCRIPTS=('scripts/ouroboros_cli.py','scripts/ouroboros/__init__.py','scripts/ouroboros/core.py',
         'scripts/ouroboros/store.py','scripts/ouroboros/ports.py','scripts/ouroboros/adapters/__init__.py',
         'scripts/ouroboros/adapters/claude.py','scripts/ouroboros/relay.py')


class RuntimeContractTests(unittest.TestCase):
    def test_runtime_mirrored(self):
        source=ROOT/'src/skills/init'
        for rel in SCRIPTS:
            for pkg in PACKAGES:
                self.assertEqual((source/rel).read_bytes(),(ROOT/pkg/'init'/rel).read_bytes(),f'{pkg}/{rel}')

    def test_packaged_cli_help_runs(self):
        for pkg in PACKAGES:
            r=subprocess.run([sys.executable,'-B',str(ROOT/pkg/'init/scripts/ouroboros_cli.py'),'--help'],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr)
            for cmd in ('session-wait','approve','doctor'):self.assertIn(cmd,r.stdout)

    def test_no_bypass_modes(self):
        for path in (ROOT/'src/skills/init/scripts').rglob('*.py'):
            t=path.read_text()
            for s in ('bypassPermissions','dangerously-skip-permissions','danger-full-access'):
                self.assertNotIn(s,t,str(path))

    def test_no_legacy_private_dir(self):
        for path in (ROOT/'src/skills/init/scripts').rglob('*.py'):
            self.assertNotIn('.dryforge/mission',path.read_text(),str(path))

    def test_no_third_party_imports(self):
        for path in (ROOT/'src/skills/init/scripts').rglob('*.py'):
            for line in path.read_text().splitlines():
                s=line.strip()
                if s.startswith(('import ','from ')):
                    mod=s.split()[1].split('.')[0]
                    self.assertNotIn(mod,('claude_agent_sdk','yaml','requests'),f'{path}: {s}')


if __name__=='__main__':unittest.main()
