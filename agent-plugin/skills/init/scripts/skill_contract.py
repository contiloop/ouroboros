#!/usr/bin/env python3
"""Optional L1 skill boundary: data is evidence, never authority.

Pure record validation. Does not invoke skills, fetch sources, authenticate humans,
interpret arbitrary payloads, or execute next_action. Uses only the standard library.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import re
import sys
from pathlib import Path

VERSION = 1
MAX_BYTES = 65536  # Put raw logs/transcripts in protected files, not this control envelope.
IDENTITY = {'schema_version', 'request_id', 'mission_id', 'skill', 'intent_digest'}
REQUEST_FIELDS = IDENTITY | {'purpose', 'input'}
RESULT_FIELDS = IDENTITY | {'status', 'payload', 'evidence', 'unresolved', 'next_action'}
INTENT_FIELDS = {'goal', 'success_criteria', 'constraints', 'priorities', 'non_goals'}
TERMINAL = {'ACCEPTED', 'COMMITTED', 'REJECTED', 'CANCELLED'}
OPERATIONS = {'skill_request', 'skill_result', 'skill_review', 'skill_approve',
              'skill_commit', 'skill_cancel'}


class ContractError(ValueError):
    """Invalid or stale skill record; never convert this into a successful result."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def text(value: object, label: str) -> str:
    require(isinstance(value, str) and bool(value.strip()), f'{label} must be nonempty text')
    return value


def fields(value: object, required: set[str], optional: set[str] | None = None) -> None:
    require(isinstance(value, dict), 'expected a JSON object')
    require(required <= value.keys(), 'missing required fields')
    require(value.keys() <= required | (optional or set()), 'unknown envelope fields')


def strings(value: object, label: str, *, nonempty: bool = False) -> list[str]:
    require(isinstance(value, list), f'{label} must be a list')
    require(not nonempty or bool(value), f'{label} must not be empty')
    for item in value:
        text(item, label)
    require(len(set(value)) == len(value), f'{label} contains duplicates')
    return value


def _json(value: object, depth: int = 0) -> None:
    require(depth <= 32, 'JSON is too deeply nested')
    if isinstance(value, dict):
        for key, item in value.items():
            require(type(key) is str, 'JSON keys must be strings')
            _json(item, depth + 1)
    elif isinstance(value, list):
        for item in value:
            _json(item, depth + 1)
    else:
        require(value is None or type(value) in (str, int, bool, float), 'not JSON data')
        require(type(value) is not float or math.isfinite(value), 'non-finite JSON number')


def canonical(value: object) -> bytes:
    _json(value)
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'),
                      allow_nan=False).encode('utf-8')


def digest(value: object) -> str:
    """Bind semantic JSON content, not whitespace or dictionary insertion order."""
    return hashlib.sha256(canonical(value)).hexdigest()


def _identity(value: dict) -> None:
    require(type(value.get('schema_version')) is int and value['schema_version'] == VERSION,
            'unsupported skill contract version')
    for name in ('request_id', 'mission_id', 'skill', 'intent_digest'):
        text(value.get(name), name)
    require(re.fullmatch(r'[a-z0-9][a-z0-9_.-]*', value['skill']) is not None,
            'skill must be a portable identifier, not an execution command')
    require(re.fullmatch(r'[0-9a-f]{64}', value['intent_digest']) is not None, 'invalid intent digest')
    require(len(canonical(value)) <= MAX_BYTES, 'envelope too large; use artifact references')


def validate_request(request: dict) -> None:
    fields(request, REQUEST_FIELDS)
    _identity(request)
    text(request['purpose'], 'decision-changing purpose')
    require(isinstance(request['input'], dict), 'input must be an object')


def validate_result(request: dict, result: dict) -> None:
    validate_request(request)
    fields(result, RESULT_FIELDS, {'proposal'})
    _identity(result)
    require(all(result[k] == request[k] for k in IDENTITY), 'result does not match issued request')
    require(isinstance(result['payload'], dict), 'payload must be an object')
    actions = {'completed': {'review'}, 'needs_decision': {'ask_user', 'verify'},
               'blocked': {'ask_user', 'verify', 'stop'}}
    status = result['status']
    require(isinstance(status, str) and status in actions, 'unknown skill status')
    require(isinstance(result['next_action'], str) and result['next_action'] in actions[status],
            'next_action is a typed recommendation, not a command or permission')
    strings(result['unresolved'], 'unresolved', nonempty=status != 'completed')
    require(status != 'completed' or not result['unresolved'], 'completed with unresolved decisions')
    require(isinstance(result['evidence'], list), 'evidence must be a list')
    ids = []
    for item in result['evidence']:
        fields(item, {'id', 'claim', 'reference', 'kind', 'disposition'})
        for key in ('id', 'claim', 'reference'):
            text(item[key], key)
        require(item['kind'] in ('dialogue', 'documentation', 'code', 'execution'), 'unknown evidence kind')
        require(item['disposition'] in ('VERIFIED', 'UNVERIFIED', 'RULED_OUT'), 'unknown evidence disposition')
        ids.append(item['id'])
    require(len(set(ids)) == len(ids), 'duplicate evidence ID')
    if 'proposal' in result:
        proposal = result['proposal']
        fields(proposal, {'intent_patch', 'reason'})
        text(proposal['reason'], 'proposal reason')
        patch = proposal['intent_patch']
        require(isinstance(patch, dict) and bool(patch), 'intent patch must be a nonempty object')
        require(patch.keys() <= INTENT_FIELDS, 'proposal cannot alter identity, authority, workspace or budgets')
        require(bool(result['evidence']), 'an intent proposal needs traceable evidence')
        for key, value in patch.items():
            if key == 'goal':
                text(value, key)
            else:
                strings(value, key, nonempty=key == 'success_criteria')


def pending(state: dict) -> bool:
    return any(item['stage'] not in TERMINAL
               for item in state.get('extensions', {}).get('requests', {}).values())


def transition(state: dict, event: dict, validate_contract) -> None:
    """Mutate only the caller's transaction copy. Host checks identity/evidence outside this code."""
    require(state['cycle'] is None, 'extension decisions require an evaluated cycle boundary')
    require(state['status'] in {'ACTIVE', 'PAUSED'}, 'mission is not open for extension work')
    data = state.setdefault('extensions', {'requests': {}, 'intent_history': []})
    requests = data['requests']
    op = event['op']
    if op == 'skill_request':
        require(event['actor'] == 'L1', 'only L1 issues a skill request')
        request = event.get('request')
        validate_request(request)
        require(request['mission_id'] == state['contract']['mission_id'], 'request for another mission')
        require(request['intent_digest'] == digest(state['contract']), 'stale request intent')
        rid = request['request_id']
        require(rid not in requests, 'request ID already used')
        requests[rid] = dict(request=copy.deepcopy(request), stage='REQUESTED')
        return

    if op == 'skill_result':
        require(event['actor'] in {'host', 'L1'}, 'only the trusted receiver records skill output')
        result = event.get('result')
        require(isinstance(result, dict), 'result must be an object')
        rid = text(result.get('request_id'), 'request ID')
    else:
        rid = text(event.get('request_id'), 'request ID')
    require(rid in requests, 'no issued request for this result/decision')
    item = requests[rid]
    require(item['stage'] not in TERMINAL, 'request already resolved')

    if op == 'skill_cancel':
        require(event['actor'] == 'L1', 'only L1 cancels a request')
        text(event.get('basis'), 'cancellation/defer reason')
        item.update(stage='CANCELLED', cancellation=copy.deepcopy(event))
        return

    # A rejection may dispose of stale output, but never treats it as accepted evidence.
    rejecting = op == 'skill_review' and event.get('verdict') == 'reject'
    if not rejecting:
        require(item['request']['intent_digest'] == digest(state['contract']), 'stale intent; re-issue request')

    if op == 'skill_result':
        require(item['stage'] == 'REQUESTED', 'result is immutable; issue a new request')
        validate_result(item['request'], result)
        item.update(stage='RESULT', result=copy.deepcopy(result), result_digest=digest(result))
        return

    require('result' in item and event.get('result_digest') == item['result_digest'],
            'decision must name the exact result digest')
    if op == 'skill_review':
        require(event['actor'] == 'L1', 'L1 reviews received evidence, not the producer')
        require(event.get('verdict') in {'accept', 'reject'}, 'review must accept or reject')
        text(event.get('basis'), 'review basis')
        if rejecting:
            item.update(stage='REJECTED', review=copy.deepcopy(event))
            return
        require(item['stage'] == 'RESULT', 'review already recorded')
        require(item['result']['status'] == 'completed', 'resolve questions/blockers before accepting')
        checked = strings(event.get('checked_evidence'), 'checked evidence')
        require(set(checked) == {e['id'] for e in item['result']['evidence']},
                'record checks of every decisive evidence item')
        item.update(stage='REVIEWED' if 'proposal' in item['result'] else 'ACCEPTED',
                    review=copy.deepcopy(event))
    elif op == 'skill_approve':
        require(event['actor'] == 'human', 'mission intent changes require explicit human approval')
        require(item['stage'] == 'REVIEWED', 'review the exact proposal before approving')
        text(event.get('approval_ref'), 'human approval reference')
        text(event.get('basis'), 'approval basis')
        item.update(stage='APPROVED', approval=copy.deepcopy(event))
    elif op == 'skill_commit':
        require(event['actor'] == 'L1' and item['stage'] == 'APPROVED', 'only L1 commits an approved proposal')
        patch = item['result']['proposal']['intent_patch']
        previous = copy.deepcopy(state['contract'])
        require(any(previous.get(key) != value for key, value in patch.items()), 'no intent change to commit')
        revised = copy.deepcopy(previous)
        revised.update(copy.deepcopy(patch), approved_by='human', approval_ref=item['approval']['approval_ref'])
        validate_contract(revised)
        data['intent_history'].append(dict(request_id=rid, result_digest=item['result_digest'],
                                          previous_contract=previous, previous_digest=digest(previous),
                                          next_digest=digest(revised), review_event=item['review']['id'],
                                          approval_event=item['approval']['id'],
                                          approval_ref=item['approval']['approval_ref']))
        state['contract'] = revised
        item['stage'] = 'COMMITTED'
        # Cycles, worker identities, stalled count, execution limits and pause status are unchanged.
    else:
        raise ContractError(f'unknown skill operation: {op}')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    d = commands.add_parser('digest'); d.add_argument('--json', type=Path, required=True)
    v = commands.add_parser('validate')
    v.add_argument('--request', type=Path, required=True); v.add_argument('--result', type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == 'digest':
            print(digest(json.loads(args.json.read_text(encoding='utf-8'))))
        else:
            request = json.loads(args.request.read_text(encoding='utf-8'))
            result = json.loads(args.result.read_text(encoding='utf-8'))
            validate_result(request, result)
            print(json.dumps({'schema_valid': True, 'result_digest': digest(result)}))
        return 0
    except (ValueError, OSError, TypeError) as exc:
        print(f'BLOCKED: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
