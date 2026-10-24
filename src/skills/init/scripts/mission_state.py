#!/usr/bin/env python3
"""Trusted local mission ledger. No LLM calls, SDK adapter or permission bypass.

State validation is not authentication, proof of runtime behavior, or exactly-once execution.
Host adapters must verify evidence and authority before submitting events.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import os
import re
import sys
import tempfile
from pathlib import Path

CAPABILITIES = ('persistent_session', 'decision_relay', 'nested_agents', 'explicit_procedure_loading')
DELEGATED = {'answer', 'approve_ready', 'accept_result', 'complete'}
HUMAN_ONLY = {'merge', 'deploy', 'spend', 'delete', 'disclose'}


class ContractError(ValueError):
    """Invalid transition or unproven precondition; callers must not silently advance."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def text(value: object, label: str) -> str:
    require(isinstance(value, str) and bool(value.strip()), f'{label} must be nonempty text')
    return value


def strings(value: object, label: str, *, nonempty: bool = False) -> list:
    require(isinstance(value, list), f'{label} must be a list')
    require(not nonempty or bool(value), f'{label} must not be empty')
    for item in value:
        text(item, label)
    require(len(set(value)) == len(value), f'{label} must not contain duplicates')
    return value


def init_state(contract: dict) -> dict:
    require(isinstance(contract, dict), 'contract must be an object')
    for key in ('mission_id', 'goal', 'workspace', 'approval_ref'):
        text(contract.get(key), key)
    require(Path(contract['workspace']).is_absolute(), 'workspace must be absolute')
    require(contract.get('approved_by') == 'human', 'initial intent requires a human approval record')
    strings(contract.get('success_criteria'), 'success_criteria', nonempty=True)
    strings(contract.get('constraints'), 'constraints')
    strings(contract.get('human_only'), 'human_only')
    actions = strings(contract.get('delegated_actions'), 'delegated_actions')
    require(set(actions) <= DELEGATED, 'unsupported delegated authority')
    for key in ('max_cycles', 'max_stalled_cycles'):
        require(type(contract.get(key)) is int and contract[key] > 0, f'{key} must be a positive integer')
    return dict(schema_version=1, revision=0, contract=copy.deepcopy(contract), status='ACTIVE',
                cycle=None, cycles=[], workers=[], stalled=0, events=[])


def draft_state(contract: dict, runtime_policy=None) -> dict:
    """Conversation state is intentionally incomplete and grants no authority."""
    require(isinstance(contract, dict), 'draft contract must be an object')
    text(contract.get('mission_id'), 'mission ID')
    text(contract.get('workspace'), 'workspace')
    require(Path(contract['workspace']).is_absolute(), 'workspace must be absolute')
    require(not {'approved_by', 'approval_ref'} & contract.keys(), 'draft cannot claim approval')
    if runtime_policy is not None:
        api = _runtime_api()
        try:
            api.validate_policy(runtime_policy)
        except api.PolicyError as exc:
            raise ContractError(str(exc)) from exc
    return dict(schema_version=3, revision=0, contract=copy.deepcopy(contract), status='DRAFT',
                draft_runtime_policy=copy.deepcopy(runtime_policy), cycle=None, cycles=[],
                workers=[], stalled=0, events=[])


def proposal_digest(state: dict) -> str:
    require(state['status'] == 'DRAFT', 'no unapproved draft')
    proposal = dict(contract=state['contract'], runtime_policy=state['draft_runtime_policy'])
    return hashlib.sha256(json.dumps(proposal, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def document_digest(directory: Path) -> str:
    """Bind approval to ordered names and exact bytes, not file paths or mtimes."""
    h = hashlib.sha256()
    for name in ('handoff.md', 'spec.md', 'plan.md'):
        data = (directory / name).read_bytes()
        h.update(name.encode() + b'\0' + str(len(data)).encode() + b'\0' + data)
    return h.hexdigest()


def l3_action(*, role: str, same_task: bool, same_contract: bool, same_workspace: bool,
              resume_available: bool, context: str, old_writer_stopped: bool) -> str:
    """Policy for a new assignment; a reviewer-only recheck is handled by its parent."""
    require(role in {'implementer', 'researcher', 'reviewer', 'spec-reviewer'}, 'unknown L3 role')
    require(context in {'sufficient', 'insufficient', 'unknown'}, 'unknown context disposition')
    for value in (same_task, same_contract, same_workspace, resume_available, old_writer_stopped):
        require(type(value) is bool, 'capability and identity checks must be explicit booleans')
    if not old_writer_stopped:
        return 'WAIT'
    if role in {'reviewer', 'spec-reviewer'}:
        return 'FRESH_REVIEW'
    if all((same_task, same_contract, same_workspace, resume_available)) and context == 'sufficient':
        return 'RESUME'
    return 'SPAWN'


def authority(s: dict, e: dict, action: str) -> None:
    text(e.get('basis'), 'decision basis')
    require(e['actor'] in {'L1', 'human'}, 'only the decision provider may approve or answer')
    if e['actor'] == 'L1':
        require(action not in HUMAN_ONLY | set(s['contract']['human_only']), 'human-only decision')
        require(action in s['contract']['delegated_actions'], 'decision outside delegated authority')


def _skill_api():
    """Load only our shipped sibling, including when this CLI is imported by file path."""
    path = Path(__file__).with_name('skill_contract.py')
    spec = importlib.util.spec_from_file_location('_ouroboros_skill_contract', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _runtime_api():
    path = Path(__file__).with_name('runtime_permissions.py')
    spec = importlib.util.spec_from_file_location('_ouroboros_runtime_permissions', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def apply(state: dict, event: dict) -> dict:
    """Pure transaction: reject invalid input without changing the supplied state."""
    require(isinstance(state, dict) and type(state.get('schema_version')) is int
            and state['schema_version'] in (1, 2, 3), 'unsupported state schema')
    require('extensions' not in state or state['schema_version'] >= 2, 'extensions require state schema 2 or later')
    require('runtime_authority' not in state or state['schema_version'] == 3, 'runtime authority requires state schema 3')
    require(isinstance(event, dict), 'event must be an object')
    e = copy.deepcopy(event)
    text(e.get('id'), 'event ID')
    require(e.get('actor') in {'L1', 'L2', 'human', 'host'}, 'unknown actor')
    require(e.get('mission_id') == state['contract']['mission_id'], 'event belongs to a different mission')
    op = text(e.get('op'), 'operation')
    fingerprint = hashlib.sha256(json.dumps({k:v for k,v in e.items() if k != 'expected_revision'},
                                            sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    for prior in state['events']:
        if prior['id'] == e['id']:
            require(prior['fingerprint'] == fingerprint, 'event ID reused for different content')
            return copy.deepcopy(state)
    require(type(e.get('expected_revision')) is int and e['expected_revision'] == state['revision'],
            'stale or absent expected_revision')
    s = copy.deepcopy(state)
    c = s['cycle']
    require(s['status'] != 'COMPLETE' or op == 'observe', 'mission is complete')
    extension = op.startswith('skill_')
    if s['status'] == 'DRAFT':
        require(op in {'revise_draft', 'activate', 'observe'}, 'approve the reviewed draft before execution')
    if s['status'] == 'PAUSED':
        require(op in {'observe', 'resume', 'abort', 'continue'} or extension or op == 'runtime_policy', 'mission is paused')
    if not extension and op not in {'start', 'observe', 'continue', 'runtime_policy', 'revise_draft', 'activate'}:
        require(c is not None, 'no active cycle')
        require(e.get('cycle_id') == c['id'], 'event belongs to a different cycle')
        if e['actor'] == 'L2':
            require(e.get('session_id') == c['session_id'], 'L2 session identity changed')

    if op == 'revise_draft':
        require(s['status'] == 'DRAFT' and e['actor'] in {'L1', 'human'}, 'only revise an unapproved conversation draft')
        text(e.get('basis'), 'draft source evidence')
        require('runtime_policy' in e, 'replacement draft needs an explicit proposed policy or null')
        revised = draft_state(e.get('contract'), e['runtime_policy'])
        require(all(revised['contract'][k] == s['contract'][k] for k in ('mission_id', 'workspace')),
                'draft identity and workspace cannot change')
        s['contract'] = revised['contract']
        s['draft_runtime_policy'] = revised['draft_runtime_policy']
    elif op == 'activate':
        require(s['status'] == 'DRAFT' and c is None and e['actor'] == 'human', 'only the human can activate a draft')
        text(e.get('approval_ref'), 'actual user handoff reference')
        text(e.get('basis'), 'reviewed proposal reference')
        require(e.get('expected_proposal_digest') == proposal_digest(s), 'reviewed proposal changed')
        contract = dict(s['contract'], approved_by='human', approval_ref=e['approval_ref'])
        approved = init_state(contract)  # Full intent and finite cycle guards required now.
        policy = s['draft_runtime_policy']
        draft_state(s['contract'], policy)  # Validate the attached execution scope again.
        s['contract'] = approved['contract']
        s['status'] = 'ACTIVE'
        if policy is not None:
            s['runtime_authority'] = dict(version=1, revision=1,
                mission_id=contract['mission_id'], workspace=contract['workspace'],
                policy=copy.deepcopy(policy), approved_by='human', approval_ref=e['approval_ref'], event_id=e['id'])
        del s['draft_runtime_policy']
    elif op == 'runtime_policy':
        # Separate execution authority: may grant/revoke while a tool callback is waiting.
        # Does not mutate the mission WHAT, approved documents, budgets or active phase.
        require(e['actor'] == 'human', 'only a human may grant or revoke runtime authority')
        text(e.get('basis'), 'runtime authority basis')
        text(e.get('approval_ref'), 'human runtime approval reference')
        api = _runtime_api()
        previous = s.get('runtime_authority')
        require(e.get('expected_policy_digest') == api.fingerprint(previous), 'stale runtime authority')
        if c is not None:
            require(e.get('cycle_id') == c['id'], 'runtime authority targets another active cycle')
        else:
            require(e.get('cycle_id') is None, 'no active cycle for this authority event')
        require('policy' in e, 'runtime_policy needs explicit policy or null')
        policy = e['policy']
        if policy is not None:
            try:
                api.validate_policy(policy)
            except api.PolicyError as exc:
                raise ContractError(str(exc)) from exc
        s['runtime_authority'] = dict(version=1, revision=(previous or {}).get('revision', 0) + 1,
            mission_id=s['contract']['mission_id'], workspace=s['contract']['workspace'],
            policy=copy.deepcopy(policy), approved_by='human', approval_ref=e['approval_ref'],
            event_id=e['id'])
        s['schema_version'] = 3  # Older runtimes reject instead of losing/reinterpreting grants.
    elif extension:
        api = _skill_api()
        try:
            api.require(op in api.OPERATIONS, 'unknown skill operation')
            api.transition(s, e, init_state)
            s['schema_version'] = max(2, s['schema_version'])  # Old runtimes fail closed instead of skipping pending extensions.
        except api.ContractError as exc:
            raise ContractError(str(exc)) from exc
    elif op == 'start':
        require(e['actor'] == 'L1', 'L1 assigns cycles')
        require(c is None, 'previous cycle has not been evaluated')
        if 'extensions' in s:
            require(not _skill_api().pending(s), 'resolve or explicitly cancel pending skill work before a cycle')
        require(len(s['cycles']) < s['contract']['max_cycles'], 'cycle budget exhausted')
        require(s['stalled'] < s['contract']['max_stalled_cycles'], 'progress budget exhausted')
        cid, sid = text(e.get('cycle_id'), 'cycle ID'), text(e.get('session_id'), 'worker session')
        require(cid not in [x['id'] for x in s['cycles']], 'duplicate cycle ID')
        caps = e.get('capabilities')
        require(isinstance(caps, dict) and all(caps.get(k) is True for k in CAPABILITIES),
                'persistent relay/nested-agent capability is not verified')
        require(type(e.get('reuse')) is bool, 'reuse must be explicit')
        if e['reuse']:
            require(sid in s['workers'] and e.get('context') == 'sufficient'
                    and e.get('session_resumable') is True, 'unsafe or unverified L2 reuse')
        else:
            require(sid not in s['workers'], 'SPAWN must have a fresh session identity')
            s['workers'].append(sid)
        s['cycle'] = dict(id=cid, session_id=sid, stage='READY', goal=text(e.get('goal'), 'cycle goal'),
                          checkpoint_ref=text(e.get('checkpoint_ref'), 'checkpoint'), pending={},
                          decisions=[], digest=None, approved_digest=None)
    elif op == 'ready':
        require(e['actor'] == 'L2' and c['stage'] in {'READY','READY_REVIEW','APPROVED'}, 'not in ready')
        require(re.fullmatch('[0-9a-f]{64}', text(e.get('digest'), '3-doc digest')), 'invalid digest')
        c.update(stage='READY_REVIEW', digest=e['digest'], approved_digest=None)
    elif op == 'approve':
        authority(s, e, 'approve_ready')
        require(c['stage'] == 'READY_REVIEW' and not c['pending'], 'ready review or answers pending')
        require(e.get('digest') == c['digest'], 'stale artifact approval')
        c.update(stage='APPROVED', approved_digest=e['digest'])
        c['decisions'].append(e)
    elif op == 'go':
        require(e['actor'] == 'L2' and c['stage'] == 'APPROVED', 'go requires approval')
        require(not c['pending'] and e.get('digest') == c['approved_digest'], 'stale approval or pending answer')
        c['stage'] = 'GO'
    elif op == 'question':
        require(e['actor'] == 'L2' and c['stage'] in {'READY','READY_REVIEW','APPROVED','GO','RESULT_REVIEW'},
                'not a decision point')
        rid = text(e.get('request_id'), 'request ID')
        require(rid not in c['pending'] and not any(d.get('request_id') == rid for d in c['decisions']),
                'duplicate request ID')
        text(e.get('question'), 'question'); text(e.get('scope'), 'scope')
        c['pending'][rid] = e
    elif op == 'answer':
        rid = text(e.get('request_id'), 'request ID')
        require(rid in c['pending'], 'no matching pending request')
        authority(s, e, c['pending'][rid]['scope'])
        text(e.get('answer'), 'answer')
        c['decisions'].append(e); del c['pending'][rid]
    elif op == 'result':
        require(e['actor'] == 'L2' and c['stage'] == 'GO' and not c['pending'], 'go is not ready to finish')
        require(e.get('blockers') == [] and e.get('children_quiescent') is True, 'blockers or live children')
        require(e.get('digest') == c['approved_digest'], 'result uses a different approved contract')
        checks = e.get('checks')
        require(isinstance(checks, list) and bool(checks), 'missing captured checks')
        for check in checks:
            require(isinstance(check, dict), 'invalid check')
            text(check.get('command'), 'check command')
            require(type(check.get('exit_code')) is int and check['exit_code'] == 0
                    and check.get('observed') is True, 'negative/inconclusive check')
        review = e.get('review')
        require(isinstance(review, dict) and review.get('independent') is True, 'independent review missing')
        text(review.get('evidence_ref'), 'review evidence')
        text(e.get('result_ref'), 'result evidence')
        require(re.fullmatch('[0-9a-f]{40,64}', text(e.get('commit'), 'commit')), 'invalid commit')
        c.update(stage='RESULT_REVIEW', result=e)
    elif op == 'accept':
        authority(s, e, 'accept_result')
        require(c['stage'] == 'RESULT_REVIEW' and not c['pending'], 'result acceptance is premature')
        c['stage'] = 'ACCEPTED'; c['decisions'].append(e)
    elif op == 'close':
        require(e['actor'] == 'L2' and c['stage'] == 'ACCEPTED', 'accept before archiving/closing')
        require(e.get('children_quiescent') is True, 'children still running')
        text(e.get('archive_ref'), 'archive'); text(e.get('checkpoint_ref'), 'checkpoint')
        c.update(stage='EVALUATION', checkpoint=e)
    elif op == 'evaluate':
        require(e['actor'] in {'L1', 'human'} and c['stage'] == 'EVALUATION', 'decision provider evaluates a closed cycle')
        text(e.get('basis'), 'evaluation basis')
        decision = e.get('decision')
        require(decision in {'CONTINUE','REPLAN','ESCALATE','COMPLETE'}, 'invalid mission decision')
        require(type(e.get('progress')) is bool, 'progress must be evidenced true/false')
        if decision == 'COMPLETE':
            authority(s, e, 'complete')
            evidence = e.get('success_evidence')
            require(isinstance(evidence, dict), 'missing success evidence')
            for criterion in s['contract']['success_criteria']:
                text(evidence.get(criterion), f'evidence for {criterion}')
            s['status'] = 'COMPLETE'
        s['stalled'] = 0 if e['progress'] else s['stalled'] + 1
        c.update(stage='EVALUATED', evaluation=e)
        s['cycles'].append(c); s['cycle'] = None
        if decision != 'COMPLETE' and (decision == 'ESCALATE' or s['stalled'] >= s['contract']['max_stalled_cycles']):
            s['status'] = 'PAUSED'
    elif op == 'interrupt':
        require(e['actor'] == 'host' and e.get('session_id') == c['session_id'], 'wrong interrupted session')
        text(e.get('reason'), 'interruption reason'); s['status'] = 'PAUSED'
    elif op == 'resume':
        require(e['actor'] == 'L1' and s['status'] == 'PAUSED', 'resume only a paused cycle')
        require(e.get('session_id') == c['session_id'] and e.get('reconciled') is True,
                'must reconcile and resume the original L2')
        text(e.get('checkpoint_ref'), 'recovery checkpoint'); s['status'] = 'ACTIVE'
    elif op == 'abort':
        require(e['actor'] == 'human' and e.get('children_quiescent') is True, 'abort requires human and stopped children')
        text(e.get('basis'), 'abort authorization'); text(e.get('checkpoint_ref'), 'abort checkpoint')
        c.update(stage='ABORTED', abort=e); s['cycles'].append(c); s['cycle']=None; s['status']='ACTIVE'
    elif op == 'continue':
        require(e['actor'] == 'human' and s['status'] == 'PAUSED' and c is None, 'human review required')
        text(e.get('basis'), 'human continuation decision')
        require(len(s['cycles']) < s['contract']['max_cycles'], 'new budget approval/contract required')
        s['stalled'] = 0; s['status'] = 'ACTIVE'
    elif op == 'observe':
        require(e['actor'] == 'host', 'observations come from the host adapter')
        text(e.get('event'), 'host event'); text(e.get('reference'), 'host evidence reference')
    else:
        raise ContractError(f'unknown operation: {op}')
    s['revision'] += 1
    s['events'].append(dict(id=e['id'], fingerprint=fingerprint, revision=s['revision'], event=e))
    return s


def _write(path: Path, state: dict) -> None:
    name = None
    try:
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent, delete=False) as f:
            name = f.name
            json.dump(state, f, ensure_ascii=False, indent=2); f.write('\n'); f.flush(); os.fsync(f.fileno())
        os.replace(name, path)
    finally:
        if name and os.path.exists(name): os.unlink(name)


def _transaction(path: Path, change) -> dict:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    require(not path.is_symlink(), 'state must not be a symlink')
    lock = path.with_suffix(path.suffix + '.lock')
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise ContractError('state writer lock exists; reconcile owner/crash before removing it') from exc
    try:
        with os.fdopen(fd, 'w') as f: f.write(str(os.getpid()))
        old = json.loads(path.read_text(encoding='utf-8')) if path.exists() else None
        new = change(old); _write(path, new); return new
    finally:
        lock.unlink()


def initialize(path: Path, contract: dict, *, draft=False, runtime_policy=None) -> dict:
    def create(old):
        require(old is None, 'state already exists; do not reset a mission')
        return draft_state(contract, runtime_policy) if draft else init_state(contract)
    return _transaction(path, create)


def save_event(path: Path, event: dict) -> dict:
    def change(old):
        require(old is not None, 'initialize a draft or approved run first'); return apply(old, event)
    return _transaction(path, change)


def _extension_summary(state: dict) -> dict:
    """Do not print every skill payload/source excerpt on each ledger transition."""
    return {rid: dict(skill=item['request']['skill'], stage=item['stage'],
                      result_digest=item.get('result_digest'))
            for rid, item in state.get('extensions', {}).get('requests', {}).items()}


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='command', required=True)
    init=sub.add_parser('init');init.add_argument('--state',type=Path,required=True);init.add_argument('--contract',type=Path,required=True)
    draft=sub.add_parser('draft');draft.add_argument('--state',type=Path,required=True);draft.add_argument('--contract',type=Path,required=True)
    draft.add_argument('--policy',type=Path)
    act=sub.add_parser('apply');act.add_argument('--state',type=Path,required=True);act.add_argument('--event',type=Path,required=True)
    show=sub.add_parser('show');show.add_argument('--state',type=Path,required=True)
    digest=sub.add_parser('digest');digest.add_argument('--docs-dir',type=Path,required=True)
    args=p.parse_args()
    try:
        if args.command=='digest': print(document_digest(args.docs_dir));return 0
        if args.command in ('init', 'draft'):
            policy = json.loads(args.policy.read_text(encoding='utf-8')) if args.command == 'draft' and args.policy else None
            s=initialize(args.state,json.loads(args.contract.read_text(encoding='utf-8')),
                         draft=args.command == 'draft', runtime_policy=policy)
        elif args.command=='apply': s=save_event(args.state,json.loads(args.event.read_text(encoding='utf-8')))
        else: s=json.loads(args.state.read_text(encoding='utf-8'))
        print(json.dumps(dict(schema_version=s['schema_version'],status=s['status'],revision=s['revision'],cycle=s['cycle'],
                              completed_cycles=len(s['cycles']),stalled=s['stalled'],
                              extensions=_extension_summary(s),
                              proposal_digest=proposal_digest(s) if s['status'] == 'DRAFT' else None,
                              runtime_policy_digest=_runtime_api().fingerprint(s.get('runtime_authority'))),ensure_ascii=False,indent=2))
        return 0
    except (ContractError,OSError,ValueError,KeyError,TypeError) as exc:
        print(f'BLOCKED: {exc}',file=sys.stderr);return 2


if __name__=='__main__':raise SystemExit(main())
