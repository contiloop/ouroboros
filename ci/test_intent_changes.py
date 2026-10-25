"""Direct reviewed goal changes and recovery of retired extension records."""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from test_mission_state import m, contract


class IntentChangesTest(unittest.TestCase):
    def setUp(self):
        self.s = m.init_state(contract())

    def amendment(self, **overrides):
        e = dict(id='change-1', op='amend', actor='human', mission_id='demo',
                 expected_revision=self.s['revision'], expected_intent_digest=m.intent_digest(self.s['contract']),
                 approval_ref='conversation:approved-change', basis='reviewed outcome and impact',
                 patch={'goal': 'Search existing notes'})
        e.update(overrides)
        return e

    def legacy(self, stage='REQUESTED'):
        self.s['schema_version'] = 2
        self.s['extensions'] = {'requests': {'old-1': {
            'request': {'skill': 'old-interview'}, 'stage': stage,
            'result': {'proposal': 'evidence to preserve'}}}, 'intent_history': []}

    def cancel(self, **overrides):
        e = dict(id='cancel-1', op='skill_cancel', actor='L1', mission_id='demo',
                 expected_revision=self.s['revision'], request_id='old-1',
                 basis='retired protocol; discuss the unresolved decision directly')
        e.update(overrides)
        return e

    def start(self):
        return dict(id='start-1', op='start', actor='L1', mission_id='demo',
                    expected_revision=self.s['revision'], cycle_id='c1', session_id='w1',
                    goal='Implement the approved goal', checkpoint_ref='git:accepted', reuse=False,
                    capabilities={key: True for key in m.CAPABILITIES})

    def test_change_preserves_authority_history_budget_and_pause(self):
        self.s.update(status='PAUSED', stalled=1, workers=['old-session'], cycles=[{'id': 'old-cycle'}])
        self.s['schema_version'] = 3
        self.s['runtime_authority'] = {'preserved': 'grant'}
        before = copy.deepcopy(self.s)
        changed = m.apply(self.s, self.amendment())
        self.assertEqual(self.s, before)
        self.assertEqual(changed['contract']['goal'], 'Search existing notes')
        self.assertEqual(changed['intent_history'][0]['previous_contract'], before['contract'])
        for key in ('status', 'stalled', 'workers', 'cycles', 'runtime_authority', 'schema_version'):
            self.assertEqual(changed[key], before[key])
        for key in ('mission_id', 'workspace', 'delegated_actions', 'human_only', 'max_cycles', 'max_stalled_cycles'):
            self.assertEqual(changed['contract'][key], before['contract'][key])

    def test_only_exact_human_approved_change_applies(self):
        for override in ({'actor': 'L1'}, {'actor': 'L2'}, {'actor': 'host'},
                         {'approval_ref': ''}, {'basis': ''}, {'expected_intent_digest': 'a'*64},
                         {'expected_revision': 99}):
            with self.subTest(override=override), self.assertRaises(m.ContractError):
                m.apply(self.s, self.amendment(**override))

    def test_cannot_change_identity_authority_or_limits(self):
        for key in ('mission_id', 'workspace', 'runtime_policy', 'delegated_actions',
                    'human_only', 'max_cycles', 'max_stalled_cycles', 'approved_by'):
            with self.subTest(key=key), self.assertRaises(m.ContractError):
                m.apply(self.s, self.amendment(patch={key: 'replacement'}))

    def test_validate_patch_and_reject_empty_changes(self):
        for patch in ({}, {'goal': ''}, {'success_criteria': []}, {'priorities': 'high'},
                      {'non_goals': [False]}, {'constraints': ['same', 'same']},
                      {'goal': self.s['contract']['goal']}):
            with self.subTest(patch=patch), self.assertRaises(m.ContractError):
                m.apply(self.s, self.amendment(patch=patch))
        self.assertEqual(m.apply(self.s, self.amendment(patch={'constraints': []}))['contract']['constraints'], [])

    def test_change_cannot_replace_running_cycle_or_reopen_completed_run(self):
        self.s = m.apply(self.s, self.start())
        with self.assertRaises(m.ContractError):
            m.apply(self.s, self.amendment())
        self.s.update(cycle=None, status='COMPLETE')
        with self.assertRaises(m.ContractError):
            m.apply(self.s, self.amendment())

    def test_identical_retry_is_idempotent_but_changed_retry_fails(self):
        event = self.amendment()
        updated = m.apply(self.s, event)
        self.assertEqual(m.apply(updated, event), updated)
        with self.assertRaises(m.ContractError):
            m.apply(updated, dict(event, patch={'goal': 'Different request'}))

    def test_pending_legacy_record_requires_explicit_disposition(self):
        self.legacy()
        original = copy.deepcopy(self.s)
        for event in (self.start(), self.amendment()):
            with self.assertRaises(m.ContractError):
                m.apply(self.s, event)
        self.s = m.apply(self.s, self.cancel())
        self.assertEqual(self.s['extensions']['requests']['old-1']['stage'], 'CANCELLED')
        self.assertEqual(self.s['extensions']['requests']['old-1']['result'],
                         original['extensions']['requests']['old-1']['result'])
        self.assertEqual(self.s['contract'], original['contract'])
        self.assertEqual(m.apply(self.s, self.start())['cycle']['session_id'], 'w1')
        self.assertEqual(m.apply(self.s, self.amendment())['contract']['goal'], 'Search existing notes')

    def test_legacy_cancellation_cannot_erase_terminal_records_or_run_midcycle(self):
        self.legacy('COMMITTED')
        with self.assertRaises(m.ContractError): m.apply(self.s, self.cancel())
        self.s = m.apply(self.s, self.start())
        self.s['extensions']['requests']['old-1']['stage'] = 'REQUESTED'
        with self.assertRaises(m.ContractError): m.apply(self.s, self.cancel())

    def test_retired_extension_operations_cannot_start_or_apply_proposals(self):
        self.legacy('APPROVED')
        for op in ('skill_request', 'skill_result', 'skill_review', 'skill_approve', 'skill_commit'):
            with self.subTest(op=op), self.assertRaises(m.ContractError):
                m.apply(self.s, dict(self.cancel(), op=op))
        for override in ({'actor': 'human'}, {'request_id': 'missing'}, {'basis': ''}):
            with self.assertRaises(m.ContractError): m.apply(self.s, self.cancel(**override))

    def test_show_exposes_digest_and_legacy_recovery_without_mutation(self):
        self.legacy()
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)/'state.json'
            state.write_text(json.dumps(self.s))
            proc = subprocess.run([sys.executable, '-B', str(Path(m.__file__)), 'show', '--state', str(state)],
                                  capture_output=True, text=True, check=True)
            shown = json.loads(proc.stdout)
            self.assertEqual(shown['intent_digest'], m.intent_digest(self.s['contract']))
            self.assertEqual(shown['legacy_extensions']['old-1']['stage'], 'REQUESTED')
            self.assertEqual(json.loads(state.read_text()), self.s)


if __name__ == '__main__': unittest.main()
