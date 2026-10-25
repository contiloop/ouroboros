#!/usr/bin/env python3
"""Deterministic JSON-RPC fixture, NOT Codex or a model. Never a production backend."""
import json
import os
from pathlib import Path
import sys
p = Path(os.environ['OUROBOROS_FIXTURE_STATE'])
state = json.loads(p.read_text()) if p.exists() else {'id':'fixture-thread','sessionId':'fixture-thread','turns':[]}
pending = {}
children = {}
def emit(v): print(json.dumps(v),flush=True)
def save(): p.write_text(json.dumps(state))
def complete(t,notice=True,status='completed',text='fixture result'):
    t.update(status=status,items=[{'id':t['id']+'-reply','type':'agentMessage','text':text}]); save()
    if notice: emit({'method':'turn/completed','params':{'threadId':state['id'],'turn':t}})
for line in sys.stdin:
    m = json.loads(line)
    if 'method' not in m:
        t = pending.pop(str(m['id']),None)
        if t and str(m['id']).startswith('child-request-'):
            child = children['fixture-child']
            child['turns'][0]['status'] = 'completed'
            state['child_response'] = m; save()
            emit({'method':'turn/completed','params':{'threadId':child['id'],'turn':child['turns'][0]}})
            emit({'method':'item/completed','params':{'threadId':state['id'],'turnId':t['id'],
                  'item':{'type':'subAgentActivity','kind':'completed','agentThreadId':child['id']}}})
        elif t: complete(t,text='fixture accepted response: '+json.dumps(m))
        continue
    method,params,rid = m['method'],m.get('params',{}),m.get('id')
    if method == 'initialized': continue
    r = {}
    if method == 'initialize': r = {'userAgent':'FIXTURE-NOT-CODEX'}
    elif method == 'skills/list':
        catalog = p.with_suffix('.skills.json')
        if catalog.exists():
            skills = json.loads(catalog.read_text())
        else:
            skills = []
            for name in ('ready','go','migration'):
                entry = p.parent/'fixture-dryforge'/name/'SKILL.md'
                entry.parent.mkdir(parents=True,exist_ok=True)
                entry.write_text('FIXTURE SKILL, NOT A REAL PROCEDURE')
                skills.append({'name':'dryforge:'+name,'path':str(entry),'enabled':True})
        r = {'data':[{'cwd':cwd,'skills':skills,'errors':[]} for cwd in params['cwds']]}
    elif method == 'thread/start': save(); r = {'thread':state}
    elif method == 'thread/resume': r = {'thread':{'id':'wrong'} if os.environ.get('FIXTURE_WRONG_ID') else state}
    elif method == 'thread/read': r = {'thread':children.get(params.get('threadId'),state)}
    elif method == 'turn/start':
        t = {'id':'turn-'+str(len(state['turns'])+1),'status':'inProgress','items':[],
             'input':params['input']}
        state['turns'].append(t); save()
        emit({'id':rid,'result':{'turn':t}})
        text = params['input'][0]['text']
        if 'FIXTURE_DISCONNECT' in text: os._exit(9)
        if 'FIXTURE_HANG' in text: continue
        if 'FIXTURE_CHILD_AFTER_PARENT' in text:
            child = {'id':'fixture-child','sessionId':state['sessionId'],
                     'turns':[{'id':'child-turn','status':'inProgress','items':[]}]}
            children[child['id']] = child
            emit({'method':'item/completed','params':{'threadId':state['id'],'turnId':t['id'],
                  'item':{'type':'subAgentActivity','kind':'started','agentThreadId':child['id']}}})
            complete(t,text='Parent returned while its child still needs an answer.')
            key = 'child-request-'+t['id']; pending[key] = t
            emit({'id':key,'method':'item/commandExecution/requestApproval','params':{
                 'threadId':child['id'],'turnId':'child-turn','itemId':'child-item',
                 'cwd':params['cwd'],'command':'git add tests/__init__.py'}})
            continue
        if any(x in text for x in ('FIXTURE_PERMISSION', 'FIXTURE_QUESTION', 'FIXTURE_GIT_ADD')):
            key = 'request-'+t['id']; pending[key] = t
            body = {'threadId':state['id'],'turnId':t['id'],'itemId':'fixture-item'}
            if 'FIXTURE_QUESTION' in text:
                method = 'item/tool/requestUserInput'; body['questions'] = [{'id':'q1','question':'Fixture question?'}]
            else:
                method = 'item/commandExecution/requestApproval'; body['command'] = 'fixture command (not executed)'
                if 'FIXTURE_GIT_ADD' in text:
                    body.update(command='git add tests/__init__.py', cwd=params['cwd'])
            emit({'id':key,'method':method,'params':body}); continue
        complete(t,notice='FIXTURE_DROP_NOTICE' not in text,status='failed' if 'FIXTURE_FAILURE' in text else 'completed'); continue
    else:
        emit({'id':rid,'error':{'code':-32601,'message':method}}); continue
    emit({'id':rid,'result':r})
