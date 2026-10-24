"""Outer conversation/handoff gates, using real ledger files and CLI processes."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from test_mission_state import m, contract


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.contract = contract()
        del self.contract['approved_by']
        del self.contract['approval_ref']
        self.policy = dict(version=1, operations=['git_add'], paths=['tests'],
                           verification_commands=[], trust_workspace_code=True)
        self.s = m.draft_state(self.contract, self.policy)

    def event(self, op='activate', **kwargs):
        e = dict(id='handoff', op=op, actor='human', mission_id='demo', expected_revision=self.s['revision'],
                 approval_ref='FIXTURE: user invokes ouroboros:approve', basis='FIXTURE reviewed proposal',
                 expected_proposal_digest=m.proposal_digest(self.s))
        e.update(kwargs)
        return e

    def test_partial_conversation_has_no_execution_authority(self):
        partial = m.draft_state(dict(mission_id='demo', workspace='/tmp/demo'))
        self.assertEqual(partial['status'], 'DRAFT')
        self.assertNotIn('runtime_authority', self.s)
        for op in ('start', 'runtime_policy', 'skill_request'):
            with self.subTest(op=op), self.assertRaises(m.ContractError):
                m.apply(self.s, self.event(op))
        with self.assertRaises(m.ContractError):
            m.apply(partial, dict(self.event(), expected_proposal_digest=m.proposal_digest(partial)))

    def test_one_human_handoff_activates_reviewed_intent_and_execution_scope(self):
        result = m.apply(self.s, self.event())
        self.assertEqual(result['status'], 'ACTIVE')
        self.assertEqual(result['contract']['approval_ref'], result['runtime_authority']['approval_ref'])
        self.assertEqual(result['runtime_authority']['policy'], self.policy)
        self.assertEqual(result['contract']['goal'], self.contract['goal'])
        self.assertEqual(result['cycle'], None)  # Recording approval does not fabricate host execution.
        self.assertEqual(result['events'][-1]['event']['actor'], 'human')
        self.assertEqual(self.s['status'], 'DRAFT')  # Pure transaction.

    def test_l1_cannot_self_activate_or_attach_an_undisclosed_policy(self):
        with self.assertRaises(m.ContractError): m.apply(self.s, self.event(actor='L1'))
        changed = copy.deepcopy(self.s)
        changed['draft_runtime_policy']['paths'].append('docs')
        with self.assertRaises(m.ContractError): m.apply(changed, self.event())
        changed = copy.deepcopy(self.s)
        changed['contract']['goal'] = 'A different goal'
        with self.assertRaises(m.ContractError): m.apply(changed, self.event())

    def test_conversation_refinement_invalidates_previous_review(self):
        approved_event = self.event()
        revised_contract = dict(self.contract, goal='Refined through conversation')
        revised = m.apply(self.s, self.event('revise_draft', id='revision', actor='L1',
                                           contract=revised_contract, runtime_policy=None))
        self.assertEqual(revised['status'], 'DRAFT')
        self.assertEqual(revised['contract']['goal'], revised_contract['goal'])
        with self.assertRaises(m.ContractError):
            m.apply(revised, dict(approved_event, expected_revision=revised['revision']))
        result = m.apply(revised, dict(approved_event, expected_revision=revised['revision'],
                                     expected_proposal_digest=m.proposal_digest(revised)))
        self.assertNotIn('runtime_authority', result)

    def test_repeated_handoff_does_not_reset_run_or_expand_authority(self):
        event = self.event()
        result = m.apply(self.s, event)
        self.assertEqual(m.apply(result, event), result)
        with self.assertRaises(m.ContractError):
            m.apply(result, dict(event, id='second', expected_revision=result['revision']))
        with self.assertRaises(m.ContractError):
            m.apply(result, dict(event, id='revision', op='revise_draft', expected_revision=result['revision'],
                                 contract=self.contract, runtime_policy=None))

    def test_runtime_cannot_dispatch_ready_from_a_draft(self):
        sys.path.insert(0, str(Path(m.__file__).parent))
        from runtime_bridge.controller import prepare
        from runtime_bridge.store import BridgeError
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            ledger = root/'.dryforge/mission/state.json'; ledger.parent.mkdir(parents=True)
            ledger.write_text(json.dumps(m.draft_state(dict(self.contract, workspace=str(root)))))
            with self.assertRaisesRegex(BridgeError, 'ACTIVE'):
                prepare(dict(workspace=str(root)), 'sid', 'ready', 'Do the work', ledger, 'c1')

    def test_real_cli_draft_revision_handoff_and_persistence(self):
        script = Path(m.__file__)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); state = root/'state.json'; draft = root/'draft.json'; event_file = root/'event.json'
            draft.write_text(json.dumps(self.contract))
            def run(*args):
                return subprocess.run([sys.executable, '-B', str(script), *args], capture_output=True, text=True)
            result = run('draft', '--state', str(state), '--contract', str(draft))
            self.assertEqual(result.returncode, 0, result.stderr)
            summary = json.loads(result.stdout)
            self.assertEqual(summary['status'], 'DRAFT')
            event_file.write_text(json.dumps(dict(self.event(), expected_proposal_digest=summary['proposal_digest'])))
            result = run('apply', '--state', str(state), '--event', str(event_file))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['status'], 'ACTIVE')
            before = state.read_bytes()
            self.assertNotEqual(run('draft', '--state', str(state), '--contract', str(draft)).returncode, 0)
            self.assertEqual(state.read_bytes(), before)


if __name__ == '__main__': unittest.main()
