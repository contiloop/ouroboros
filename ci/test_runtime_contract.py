"""Packaged runtime boundary checks, not claims of live model compatibility."""
import json
from pathlib import Path
import subprocess
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
PACKAGES=('claude/skills','codex/plugin/skills','grok/skills','agent-plugin/skills','antigravity/skills')
class RuntimeContractTests(unittest.TestCase):
    def test_optional_mission_connection(self):
        t=(ROOT/'src/skills/init/references/orchestration.md').read_text()
        for s in ('runtime-bridge.md','worker_runtime.py','Transport receipts','never auto-install'):self.assertIn(s,t)
    def test_runtime_mirrored(self):
        source=ROOT/'src/skills/init'
        for rel in ('scripts/worker_runtime.py','scripts/runtime_permissions.py','references/runtime-permissions.md','scripts/runtime_bridge/store.py','scripts/runtime_bridge/adapters.py','scripts/runtime_bridge/controller.py','references/runtime-bridge.md'):
            for pkg in PACKAGES:self.assertEqual((source/rel).read_bytes(),(ROOT/pkg/'init'/rel).read_bytes())
    def test_packaged_cli_does_not_require_sdk_for_help(self):
        for pkg in PACKAGES:
            r=subprocess.run([sys.executable,'-B',str(ROOT/pkg/'init/scripts/worker_runtime.py'),'--help'],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr);self.assertIn('resume',r.stdout)
    def test_doctor_never_claims_live_verification(self):
        r=subprocess.run([sys.executable,'-B',str(ROOT/'src/skills/init/scripts/worker_runtime.py'),'doctor','--backend','codex'],capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr);d=json.loads(r.stdout)
        self.assertFalse(d['live_verified']);self.assertFalse(d['authentication_verified'])
    def test_fake_host_is_not_selectable_backend(self):
        t=(ROOT/'src/skills/init/scripts/worker_runtime.py').read_text();self.assertNotIn('fake_app_server',t)
    def test_no_bypass_modes(self):
        t=(ROOT/'src/skills/init/scripts/runtime_bridge/adapters.py').read_text()
        for s in ('bypassPermissions','danger-full-access','dangerouslySkipPermissions'):self.assertNotIn(s,t)
    def test_guides_explain_verification_and_auth_limits(self):
        t=(ROOT/'docs/RUNTIME.md').read_text()
        for s in ('UNCERTAIN','not an adversarial','not a promise','SDK-shaped doubles','not live authenticated model runs'):
            self.assertIn(s,t.replace('**',''))
if __name__=='__main__':unittest.main()
