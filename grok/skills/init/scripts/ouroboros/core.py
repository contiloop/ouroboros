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
KINDS = ('migration', 'development', 'beta')
STAGES = ('ready', 'go', 'review', 'done')
DECISIONS = ('CONTINUE', 'REPLAN', 'ESCALATE', 'COMPLETE')
ACTORS = ('human', 'L1', 'L2', 'host')
PROPOSAL_FILES = ('scenario.md', 'validation.md', 'spec.md', 'delegation.md')
VALIDATION_FIELDS = ('behavior', 'environment', 'evidence', 'cost')
DEFAULT_MODELS = dict(l2='default', l3='default')
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


def set_digest(parts) -> str:
    """The combined digest of the proposal set: SHA-256 over `<name>\\n<byte length>\\n<bytes>` for each file in the
    fixed order scenario, validation, spec, delegation. `parts` is a dict or a list of (name, bytes); all four
    files must be present."""
    by_name = dict(parts)
    missing = [n for n in PROPOSAL_FILES if by_name.get(n) is None]
    require(not missing, 'proposal set is incomplete: ' + ', '.join(missing))
    h = hashlib.sha256()
    for name in PROPOSAL_FILES:
        data = by_name[name]
        h.update(f'{name}\n{len(data)}\n'.encode())
        h.update(data)
    return h.hexdigest()


def models(run: dict) -> dict:
    """The run's {l2, l3} model names; a record without the field behaves as `default`."""
    found = run.get('models') or {}
    return {key: found.get(key) or 'default' for key in DEFAULT_MODELS}


def new_run(workspace: str) -> dict:
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + secrets.token_hex(3)
    return dict(run_id=run_id, workspace=workspace, status='DRAFT', proposal_digest_shown=None, approvals=[],
                limits=None, models=dict(DEFAULT_MODELS), spent_usd=0, stalled_cycles=0, beta_cycles=0, host=HOST,
                session=dict(id=None, started=None, reason=None, cost_total_usd=0), cycles=[], stopped_reason=None, stopped_at=None)


# ── proposal set ─────────────────────────────────────────────────────────────
# Four markdown files with `##` sections. Each parser returns the structure it found and raises RecordError,
# prefixed with the file name, on the first missing or invalid item. `check_set` runs all four and the
# cross-file rule (an efficient check for every slow/hard item).

def _norm(text: str) -> str:
    return re.sub(r'\s+', ' ', re.sub(r'[-_:]', ' ', text.strip().lower())).strip()


def _heading(line: str, level: int) -> str | None:
    """The title of a heading line of exactly `level` hashes, else None."""
    m = re.match(r'^(#{1,6})\s+(.+?)\s*#*\s*$', line)
    return m.group(2) if m and len(m.group(1)) == level else None


def sections(text: str, level: int = 2) -> dict:
    """Map normalized heading → body for headings of exactly `level` hashes; deeper headings stay in the body.
    Later duplicates win."""
    out, current = {}, None
    for line in text.splitlines():
        name = _heading(line, level)
        if name is not None:
            current = _norm(name)
            out[current] = ''
        elif current is not None:
            out[current] += line + '\n'
    return out


def _blocks(body: str, level: int = 3) -> list:
    """Ordered (title, body) pairs of the `###` blocks inside a section body, titles verbatim."""
    out = []
    for line in body.splitlines():
        name = _heading(line, level)
        if name is not None:
            out.append([name.strip(), ''])
        elif out:
            out[-1][1] += line + '\n'
    return [tuple(b) for b in out]


def _section(found: dict, name: str, file: str) -> str:
    key = _norm(name)
    for k, body in found.items():
        if k == key:
            return body
    raise RecordError(f'{file}: no `## {name}` section')


def _nonempty_section(found: dict, name: str, file: str) -> str:
    body = _section(found, name, file).strip()
    require(bool(body), f'{file}: `## {name}` is empty')
    return body


_BULLET = r'^\s*(?:[-*+]|\d+[.)])\s+'


def _bullets(body: str) -> list:
    """The text of each list item (`-`, `*`, `+` or `1.`), without the marker."""
    return [re.sub(_BULLET, '', line).strip() for line in body.splitlines() if re.match(_BULLET, line)]


def _unwrap(value: str) -> str:
    """Strip surrounding emphasis and backticks from a short value."""
    return value.strip().strip('*_`').strip()


def parse_scenario(text: str) -> dict:
    """{scenarios: [{title, steps: [{text, label}]}], workflow: [{label, line}]}."""
    file = 'scenario.md'
    found = sections(text)
    body = _section(found, 'Scenarios', file)
    blocks = _blocks(body)
    require(bool(blocks), f'{file}: `## Scenarios` has no `### <title>` scenario')
    scenarios = []
    for title, block in blocks:
        steps = []
        for n, item in enumerate(_bullets(block), 1):
            m = re.match(r'^(.*?)\s*(?:[-\u2013\u2014]+)\s*step\s*:\s*(.+?)\s*$', item, re.I)
            require(m is not None and m.group(2).strip('`').strip() != '',
                    f"{file}: step {n} of '{title}' has no `step:` label")
            steps.append(dict(text=m.group(1).strip(), label=m.group(2).strip('`').strip()))
        require(bool(steps), f"{file}: scenario '{title}' has no steps")
        scenarios.append(dict(title=title, steps=steps))
    workflow = []
    body = _section(found, 'Workflow', file)
    for item in _bullets(body):
        m = re.match(r'^(.+?)\s*:\s*(.+)$', item)
        require(m is not None and _unwrap(m.group(1)) != '',
                f"{file}: `## Workflow` bullet '{item}' is not `- <label>: <one line>`")
        workflow.append(dict(label=_unwrap(m.group(1)), line=m.group(2).strip()))
    require(bool(workflow), f'{file}: `## Workflow` is empty')
    known = {_norm(w['label']) for w in workflow}
    for scenario in scenarios:
        for step in scenario['steps']:
            require(_norm(step['label']) in known,
                    f"{file}: step label '{step['label']}' (scenario '{scenario['title']}') is not in `## Workflow`")
    return dict(scenarios=scenarios, workflow=workflow)


def _item_fields(block: str) -> tuple[dict, list]:
    """Field values of one validation item (`**Behavior:** …`, `Behavior: …`, `- Behavior: …`; continuation lines
    until the next field) and its `covers:` labels."""
    fields, covers, current = {}, [], None
    for line in block.splitlines():
        m = re.match(r'^\s*(?:[-*+]\s+)?[*_]*(behavior|environment|evidence|cost|covers)[*_]*\s*:[*_]*\s*(.*)$', line, re.I)
        if m:
            current = m.group(1).lower()
            value = m.group(2).strip()
            if current == 'covers':
                covers = [c.strip().strip('`') for c in value.split(',') if c.strip()]
                current = None
            else:
                fields[current] = value
        elif current is not None and line.strip():
            fields[current] = (fields[current] + ' ' + line.strip()).strip()
    return fields, covers


def parse_validation(text: str) -> dict:
    """{items: [{id, title, fields: {behavior, environment, evidence, cost}, cost: fast|slow/hard, covers}]}."""
    file = 'validation.md'
    found = sections(text)
    blocks = _blocks(_section(found, 'Items', file))
    require(bool(blocks), f'{file}: `## Items` has no `### V<n> <title>` item')
    items, seen = [], set()
    for title, block in blocks:
        m = re.match(r'^(V\d+)\s+(.+)$', title)
        require(m is not None, f"{file}: item heading '{title}' is not `### V<n> <title>`")
        item_id = m.group(1)
        require(item_id not in seen, f'{file}: item {item_id} appears twice')
        seen.add(item_id)
        fields, covers = _item_fields(block)
        for name in VALIDATION_FIELDS:
            require(bool(fields.get(name)), f"{file}: {item_id} '{m.group(2)}' has no {name.capitalize()}")
        cost = fields['cost'].lower()
        if cost.startswith('fast'):
            cost = 'fast'
        elif re.match(r'^(slow|hard)', cost):
            cost = 'slow/hard'
        else:
            raise RecordError(f'{file}: {item_id} Cost must be `fast` or `slow/hard`, not {fields["cost"]!r}')
        items.append(dict(id=item_id, title=m.group(2), fields=fields, cost=cost, covers=covers))
    return dict(items=items)


def parse_spec(text: str) -> dict:
    """{users, ui_references, outline: [bullets], efficient_checks: {V<n>: text}}."""
    file = 'spec.md'
    found = sections(text)
    users = _nonempty_section(found, 'Users', file)
    ui = _nonempty_section(found, 'UI references', file)
    outline = _bullets(_section(found, 'Outline', file))
    require(bool(outline), f'{file}: `## Outline` has no bullet (one per block)')
    checks_body = _nonempty_section(found, 'Efficient checks', file)
    checks = {}
    for line in checks_body.splitlines():
        m = re.match(r'^\s*(?:[-*+]\s+|\d+[.)]\s+)?[*_`]*(V\d+)[*_`]*\s*:\s*(.+?)\s*$', line)
        if m:
            checks[m.group(1)] = m.group(2)
    return dict(users=users, ui_references=ui, outline=outline, efficient_checks=checks)


def parse_limits(body: str, file: str = 'delegation.md') -> dict:
    """Lenient: a line naming each limit followed by its value."""
    def grab(pattern, label):
        for line in body.splitlines():
            m = re.search(pattern, line, re.I)
            if m:
                return m.group(1)
        raise RecordError(f'{file}: limits section lacks "{label}"')
    cycles = grab(r'max\s+cycles\b\D*?(\d+)', 'max cycles: <int>')
    stalled = grab(r'max\s+stalled\s+cycles\b\D*?(\d+)', 'max stalled cycles: <int>')
    budget = grab(r'budget\b[^\d\n]*?(no cap|\d+(?:\.\d+)?)', 'budget usd: <number>|no cap')
    usd = None if budget.lower() == 'no cap' else (int(budget) if budget.isdigit() else float(budget))
    return dict(max_cycles=int(cycles), max_stalled_cycles=int(stalled), budget_usd=usd)


def parse_delegation(text: str) -> dict:
    """{delegated_judgment, models: {l2, l3}, limits, workspace}."""
    file = 'delegation.md'
    found = sections(text)
    judgment = _nonempty_section(found, 'Delegated judgment', file)
    models_body = _section(found, 'Models', file)
    found_models = {}
    for key in ('L2', 'L3'):
        for line in models_body.splitlines():
            m = re.match(r'^\s*(?:[-*+]\s+)?[*_`]*' + key + r'[*_`]*\s*:\s*(.*)$', line, re.I)
            if m:
                value = _unwrap(m.group(1))
                require(value != '', f'{file}: `## Models` names no model for {key} (write `{key}: default`)')
                found_models[key.lower()] = 'default' if value.lower() == 'default' else value
                break
        require(key.lower() in found_models, f'{file}: `## Models` lacks `{key}: <model or default>`')
    limits = parse_limits(_section(found, 'Limits', file), file)
    workspace = _unwrap(_nonempty_section(found, 'Workspace', file).splitlines()[0])
    workspace = re.sub(_BULLET, '', workspace).strip().strip('`')
    require(workspace.startswith('/'), f'{file}: `## Workspace` is not an absolute path: {workspace!r}')
    return dict(delegated_judgment=judgment, models=found_models, limits=limits, workspace=workspace)


PARSERS = {'scenario.md': parse_scenario, 'validation.md': parse_validation, 'spec.md': parse_spec,
           'delegation.md': parse_delegation}


def check_set(texts: dict) -> dict:
    """Run the completeness rules of the four files; return {limits, models} from delegation.md. Refuses with the
    file name and the first missing or invalid item."""
    for name in PROPOSAL_FILES:
        require(name in texts and texts[name] is not None, f'{name}: file missing from the proposal set')
    parsed = {name: PARSERS[name](texts[name]) for name in PROPOSAL_FILES}
    checks = parsed['spec.md']['efficient_checks']
    for item in parsed['validation.md']['items']:
        require(item['cost'] != 'slow/hard' or item['id'] in checks,
                f"spec.md: `## Efficient checks` has no `{item['id']}: <check>` entry for the slow/hard item {item['id']}")
    return dict(limits=parsed['delegation.md']['limits'], models=parsed['delegation.md']['models'])


# ── transitions ─────────────────────────────────────────────────────────────

def record_shown(run: dict, proposal_digest: str) -> dict:
    run = copy.deepcopy(run)
    run['proposal_digest_shown'] = proposal_digest
    return run


def redraft(run: dict) -> dict:
    """Replace the proposal of a DRAFT, ACTIVE or STOPPED run: the shown digest is cleared, so the revision
    must be shown again before approve. A COMPLETE run is archived by the caller first."""
    require(run['status'] != 'COMPLETE', 'run is COMPLETE; archive it and draft a new proposal')
    run = copy.deepcopy(run)
    run['proposal_digest_shown'] = None
    return run


def approve(run: dict, current_digest: str, texts: dict) -> tuple[dict, str]:
    """Return (run, action) with action ∈ {activated, resumed, amended, unchanged}. `texts` is the proposal set
    (file name → text); its completeness is checked before any activation, amendment or resume. Digest rules:
    DRAFT → activated; ACTIVE with the last approved digest → unchanged; STOPPED with the last approved
    digest → resumed (ACTIVE again, same authority); a newer shown digest on ACTIVE or STOPPED → amended."""
    require(run['status'] != 'COMPLETE', 'run is COMPLETE; start a new proposal with draft')
    shown = run['proposal_digest_shown']
    require(shown is not None, 'proposal was never shown; show it and record shown first',
            current_digest=current_digest)
    require(shown == current_digest, 'proposal changed since it was shown; approval applies only to what was shown',
            shown_digest=shown, current_digest=current_digest)
    last = run['approvals'][-1]['digest'] if run['approvals'] else None
    if run['status'] == 'ACTIVE' and last == current_digest:
        return copy.deepcopy(run), 'unchanged'
    checked = check_set(texts)
    run = copy.deepcopy(run)
    if run['status'] == 'DRAFT':
        action = 'activated'
    elif run['status'] == 'STOPPED' and last == current_digest:
        action = 'resumed'
    else:
        action = 'amended'
    run['approvals'].append(dict(time=now(), digest=current_digest, applied=action != 'amended'))
    run['limits'] = checked['limits']
    run['models'] = checked['models']
    run['status'] = 'ACTIVE'
    run['stopped_reason'] = None
    run['stopped_at'] = None
    return run, action


def open_cycle(run: dict) -> dict | None:
    if run['cycles'] and run['cycles'][-1]['evaluation'] is None:
        return run['cycles'][-1]
    return None


def development_cycles(run: dict, *, mid_cycle: bool = False) -> int:
    """Cycles that count toward `max cycles`: every non-beta cycle; with `mid_cycle` the open one counts only once
    it is closed."""
    opened = sum(1 for c in run['cycles'] if c['kind'] != 'beta')
    current = open_cycle(run)
    return opened - (1 if mid_cycle and current is not None and current['kind'] != 'beta' else 0)


def limit_exceeded(run: dict, *, mid_cycle: bool = False, count_cycles: bool = True) -> str | None:
    """Which limit the run has reached, or None. Between cycles every opened development cycle counts; with
    `mid_cycle` (checked before a worker turn) the open cycle is the one being run and counts only once it is
    closed. Beta cycles never count; `count_cycles=False` skips the cycles limit (opening a beta cycle)."""
    lim = run['limits']
    if count_cycles and development_cycles(run, mid_cycle=mid_cycle) >= lim['max_cycles']:
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
    which = limit_exceeded(run, count_cycles=kind != 'beta')
    require(which is None, f'limit already exceeded: {which}')
    run = copy.deepcopy(run)
    if kind == 'beta':
        run['beta_cycles'] = int(run.get('beta_cycles', 0)) + 1
    cycle_id = f'c{len(run["cycles"]) + 1}'
    run['cycles'].append(dict(id=cycle_id, goal=goal, kind=kind, started=now(), session_id=run['session']['id'],
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
    """Close the open cycle; return (run, extra events) for amend_applied and limit stops. On a beta cycle ESCALATE
    (a verification only the human can make) is not stalled; REPLAN is. The cycles limit stops the run only when
    the decision asks for more development (REPLAN, or ESCALATE on a development cycle): after CONTINUE at the
    last allowed cycle the run stays ACTIVE so the beta test can run; a development cycle-start is refused."""
    require(run['status'] == 'ACTIVE', f'run is {run["status"]}, not ACTIVE')
    require(decision in DECISIONS, f'decision must be one of {", ".join(DECISIONS)}')
    require(open_cycle(run) is not None, 'no open cycle')
    require(decision != 'COMPLETE' or bool(basis.strip()), 'COMPLETE requires a non-empty basis (evidence per criterion)')
    run = copy.deepcopy(run)
    cycle = open_cycle(run)
    cycle['stage'] = 'done'
    cycle['evaluation'] = decision
    extra = apply_amendments(run, cycle['id'])
    # REPLAN, and ESCALATE on a development cycle, ask for more development: they count as stalled and are the
    # only decisions the cycles limit stops.
    more_development = decision == 'REPLAN' or (decision == 'ESCALATE' and cycle['kind'] != 'beta')
    if more_development:
        run['stalled_cycles'] += 1
    if decision == 'COMPLETE':
        run['status'] = 'COMPLETE'
    else:
        which = limit_exceeded(run, count_cycles=more_development)
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


def summary(run: dict, proposal_digest: str | None, event_count: int, legacy: bool = False) -> dict:
    cycle = open_cycle(run)
    turn = run.get('turn')
    return dict(status=run['status'], run_id=run['run_id'], legacy=legacy, proposal_digest_shown=run['proposal_digest_shown'],
                proposal_digest=proposal_digest, limits=run['limits'], models=models(run), spent_usd=run['spent_usd'],
                stalled_cycles=run['stalled_cycles'], beta_cycles=int(run.get('beta_cycles', 0)), session=run['session'],
                stopped_reason=run['stopped_reason'], stopped_at=run['stopped_at'],
                cycle=dict(id=cycle['id'], stage=cycle['stage'], kind=cycle['kind']) if cycle else None,
                turn=dict(n=turn['n'], state=turn['state'], kind=turn['kind'], question=turn.get('question')) if turn else None,
                counts=dict(cycles=len(run['cycles']), approvals=len(run['approvals']), events=event_count))
