"""Pure run-record rules. Functions take a record (dict) and return a new one; refusals raise RecordError.

A record validated here is bookkeeping, not authentication: whoever can write the private directory can
forge it. Nothing in this module touches the file system.
"""
from __future__ import annotations

import copy
import hashlib
import re
import secrets
from datetime import datetime, timezone

STATUSES = ('DRAFT', 'ACTIVE', 'COMPLETE', 'STOPPED')
KINDS = ('migration', 'development')
STAGES = ('ready', 'go', 'review', 'done')
DECISIONS = ('CONTINUE', 'REPLAN', 'ESCALATE', 'COMPLETE')
ACTORS = ('human', 'L1', 'L2', 'host')
REQUIRED_SECTIONS = ('goal', 'completion criteria', 'constraints', 'priorities', 'non goals',
                     'delegated judgment', 'workspace', 'limits')
HOST = 'claude'


class RecordError(ValueError):
    """A refused transition. `details` is printed with the BLOCKED message."""

    def __init__(self, message: str, **details):
        super().__init__(message)
        self.details = details


def require(condition: bool, message: str, **details) -> None:
    if not condition:
        raise RecordError(message, **details)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='microseconds')


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def new_run(workspace: str) -> dict:
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + secrets.token_hex(3)
    return dict(run_id=run_id, workspace=workspace, status='DRAFT', proposal_digest_shown=None, approvals=[],
                limits=None, spent_usd=0, stalled_cycles=0, host=HOST,
                session=dict(id=None, started=None, reason=None), cycles=[], stopped_reason=None, stopped_at=None)


# ── proposal ───────────────────────────────────────────────────────────────

def _heading(line: str) -> str | None:
    m = re.match(r'^#{2,6}\s+(.+?)\s*$', line)
    if not m:
        return None
    return re.sub(r'\s+', ' ', re.sub(r'[-_:]', ' ', m.group(1).strip().lower())).strip()


def sections(text: str) -> dict:
    """Map normalized `## heading` → body text. Later duplicates win."""
    out, current = {}, None
    for line in text.splitlines():
        name = _heading(line)
        if name is not None:
            current = name
            out[current] = ''
        elif current is not None:
            out[current] += line + '\n'
    return out


def _find(found: dict, name: str) -> str | None:
    for key, body in found.items():
        if key == name or key.startswith(name + ' '):
            return body
    return None


def parse_limits(body: str) -> dict:
    """Lenient: a line naming each limit followed by its value."""
    def grab(pattern, label):
        for line in body.splitlines():
            m = re.search(pattern, line, re.I)
            if m:
                return m.group(1)
        raise RecordError(f'limits section lacks "{label}"')
    cycles = grab(r'max\s+cycles\b\D*?(\d+)', 'max cycles: <int>')
    stalled = grab(r'max\s+stalled\s+cycles\b\D*?(\d+)', 'max stalled cycles: <int>')
    budget = grab(r'budget\b[^\d\n]*?(no cap|\d+(?:\.\d+)?)', 'budget usd: <number>|no cap')
    usd = None if budget.lower() == 'no cap' else (int(budget) if budget.isdigit() else float(budget))
    return dict(max_cycles=int(cycles), max_stalled_cycles=int(stalled), budget_usd=usd)


def parse_proposal(text: str) -> dict:
    """Return {sections, limits}; refuse when a required headed section is missing or empty."""
    found = sections(text)
    missing = [n for n in REQUIRED_SECTIONS if not (_find(found, n) or '').strip()]
    require(not missing, 'proposal is missing required sections: ' + ', '.join(missing).replace('non goals', 'non-goals'))
    return dict(sections=found, limits=parse_limits(_find(found, 'limits')))


# ── transitions ─────────────────────────────────────────────────────────────

def record_shown(run: dict, proposal_digest: str) -> dict:
    run = copy.deepcopy(run)
    run['proposal_digest_shown'] = proposal_digest
    return run


def redraft(run: dict) -> dict:
    require(run['status'] == 'DRAFT', f'run is {run["status"]}; draft only replaces a DRAFT proposal')
    run = copy.deepcopy(run)
    run['proposal_digest_shown'] = None
    return run


def approve(run: dict, current_digest: str, proposal_text: str) -> tuple[dict, str]:
    """Return (run, action) with action ∈ {activated, amended, unchanged}. Digest rules of the spec."""
    require(run['status'] != 'COMPLETE', 'run is COMPLETE; start a new proposal with draft')
    shown = run['proposal_digest_shown']
    require(shown is not None, 'proposal was never shown; show it and record shown first',
            current_digest=current_digest)
    require(shown == current_digest, 'proposal changed since it was shown; approval applies only to what was shown',
            shown_digest=shown, current_digest=current_digest)
    last = run['approvals'][-1]['digest'] if run['approvals'] else None
    if run['status'] != 'DRAFT' and last == current_digest:
        return copy.deepcopy(run), 'unchanged'
    limits = parse_proposal(proposal_text)['limits']
    run = copy.deepcopy(run)
    action = 'activated' if run['status'] == 'DRAFT' else 'amended'
    run['approvals'].append(dict(time=now(), digest=current_digest, applied=action == 'activated'))
    run['limits'] = limits
    run['status'] = 'ACTIVE'
    run['stopped_reason'] = None
    run['stopped_at'] = None
    return run, action


def open_cycle(run: dict) -> dict | None:
    if run['cycles'] and run['cycles'][-1]['evaluation'] is None:
        return run['cycles'][-1]
    return None


def limit_exceeded(run: dict) -> str | None:
    lim = run['limits']
    if len(run['cycles']) >= lim['max_cycles']:
        return 'cycles'
    if run['stalled_cycles'] >= lim['max_stalled_cycles']:
        return 'stalled'
    if lim['budget_usd'] is not None and run['spent_usd'] > lim['budget_usd']:
        return 'budget'
    return None


def apply_amendments(run: dict, cycle_id: str | None) -> list:
    """Mark unapplied amendments applied; return the amend_applied events to append. Mutates `run`."""
    events = []
    for approval in run['approvals']:
        if not approval['applied']:
            approval['applied'] = True
            events.append(dict(actor='L1', kind='amend_applied', cycle_id=cycle_id, data=dict(digest=approval['digest'])))
    return events


def cycle_start(run: dict, kind: str, goal: str, checkpoint: str) -> tuple[dict, list]:
    """Open a cycle; return (run, extra events) with amend_applied for amendments made between cycles."""
    require(run['status'] == 'ACTIVE', f'run is {run["status"]}, not ACTIVE')
    require(kind in KINDS, f'kind must be one of {", ".join(KINDS)}')
    require(bool(goal.strip()), 'cycle goal is empty')
    require(bool(checkpoint.strip()), 'checkpoint is empty')
    require(open_cycle(run) is None, f'cycle {open_cycle(run)["id"] if open_cycle(run) else ""} is still open; evaluate it first')
    which = limit_exceeded(run)
    require(which is None, f'limit already exceeded: {which}')
    run = copy.deepcopy(run)
    cycle_id = f'c{len(run["cycles"]) + 1}'
    run['cycles'].append(dict(id=cycle_id, goal=goal, kind=kind, started=now(), session_id=None,
                              stage='ready', checkpoint_before=checkpoint, checkpoint_after=None,
                              ready_digest=None, evaluation=None))
    return run, apply_amendments(run, cycle_id)


def cycle_stage(run: dict, stage: str, ready_digest: str | None = None, checkpoint: str | None = None) -> dict:
    require(stage in STAGES, f'stage must be one of {", ".join(STAGES)}')
    require(open_cycle(run) is not None, 'no open cycle')
    if ready_digest is not None:
        require(re.fullmatch(r'[0-9a-f]{64}', ready_digest) is not None, 'ready digest must be 64 hex characters')
    run = copy.deepcopy(run)
    cycle = open_cycle(run)
    if ready_digest is not None:
        cycle['ready_digest'] = ready_digest
    require(stage != 'go' or cycle['ready_digest'] is not None, 'go requires a recorded ready_digest')
    cycle['stage'] = stage
    if checkpoint is not None:
        cycle['checkpoint_after'] = checkpoint
    return run


def evaluate(run: dict, decision: str, basis: str) -> tuple[dict, list]:
    """Close the open cycle; return (run, extra events) for amend_applied and limit stops."""
    require(run['status'] == 'ACTIVE', f'run is {run["status"]}, not ACTIVE')
    require(decision in DECISIONS, f'decision must be one of {", ".join(DECISIONS)}')
    require(open_cycle(run) is not None, 'no open cycle')
    require(decision != 'COMPLETE' or bool(basis.strip()), 'COMPLETE requires a non-empty basis (evidence per criterion)')
    run = copy.deepcopy(run)
    cycle = open_cycle(run)
    cycle['stage'] = 'done'
    cycle['evaluation'] = decision
    extra = apply_amendments(run, cycle['id'])
    if decision not in ('CONTINUE', 'COMPLETE'):
        run['stalled_cycles'] += 1
    if decision == 'COMPLETE':
        run['status'] = 'COMPLETE'
    else:
        which = limit_exceeded(run)
        if which is not None:
            run['status'] = 'STOPPED'
            run['stopped_reason'] = f'limit:{which}'
            extra.append(dict(actor='L1', kind='stop', cycle_id=cycle['id'], data=dict(reason=run['stopped_reason'])))
    return run, extra


def stop(run: dict, reason: str) -> dict:
    require(run['status'] == 'ACTIVE', f'run is {run["status"]}, not ACTIVE')
    require(reason == 'abort' or (reason.startswith('limit:') and len(reason) > 6), 'reason must be abort or limit:<which>')
    run = copy.deepcopy(run)
    cycle = open_cycle(run)
    run['status'] = 'STOPPED'
    run['stopped_reason'] = reason
    run['stopped_at'] = dict(cycle_id=cycle['id'], stage=cycle['stage'],
                             checkpoint=cycle['checkpoint_after'] or cycle['checkpoint_before']) if cycle else None
    return run


def add_spent(run: dict, usd: float) -> dict:
    """Add one turn's cost. Callers (session commands) must add each turn exactly once."""
    require(isinstance(usd, (int, float)) and usd >= 0, 'cost must be a non-negative number')
    run = copy.deepcopy(run)
    run['spent_usd'] = run['spent_usd'] + usd
    return run


def summary(run: dict, proposal_digest: str | None, event_count: int) -> dict:
    cycle = open_cycle(run)
    return dict(status=run['status'], run_id=run['run_id'], proposal_digest_shown=run['proposal_digest_shown'],
                proposal_digest=proposal_digest, limits=run['limits'], spent_usd=run['spent_usd'],
                stalled_cycles=run['stalled_cycles'], session=run['session'], stopped_reason=run['stopped_reason'],
                stopped_at=run['stopped_at'],
                cycle=dict(id=cycle['id'], stage=cycle['stage'], kind=cycle['kind']) if cycle else None,
                counts=dict(cycles=len(run['cycles']), approvals=len(run['approvals']), events=event_count))
