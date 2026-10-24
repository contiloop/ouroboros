"""Native host transports. No keystroke injection, implicit approval or guessed session IDs."""
from __future__ import annotations
import asyncio
import contextlib
import dataclasses
import json
import os
from pathlib import Path
from .store import BridgeError, require

ROLE = '''You are Ouroboros L2, a persistent cycle worker. L1 owns mission intent and the next cycle.
Execute exactly one assigned ready-go cycle. Preserve real decision provenance. A yielded turn is
not approval, and a completed turn is not mission success. AskUserQuestion is relayed to the
caller where supported. Otherwise yield the exact question; the next answer uses the same session.
Never mutate the controller mailbox or run worker_runtime.py yourself. L3 task/reviewer agents
remain governed by the existing go rules. Do not reuse an implementer as its independent reviewer.
Load authorized procedure files and references; loading files is not a native slash invocation.
'''


def observable(value):
    """Keep tool/agent evidence, omit raw model thinking/signatures recursively."""
    if dataclasses.is_dataclass(value): value = dataclasses.asdict(value)
    if isinstance(value, dict):
        if value.get('type') in ('reasoning', 'thinking', 'redacted_thinking'):
            return {'type': value['type'], 'omitted': True}
        return {k: observable(v) for k, v in value.items() if k not in ('thinking', 'signature', 'encrypted_content')}
    if isinstance(value, list): return [observable(v) for v in value]
    return value


class ClaudeAdapter:
    def __init__(self, config, sid, emit, bind, relay):
        self.config, self.sid, self.emit, self.bind, self.relay = config, sid, emit, bind, relay
        self.client = None
        self.bootstrap = True
        self.probe = False

    async def connect(self):
        try:
            import claude_agent_sdk as sdk
        except ImportError as exc:
            raise BridgeError('Install the optional claude-agent-sdk in the selected Python environment first') from exc
        self.sdk = sdk

        async def hook(data, tool_id, context):
            self.emit('claude.hook', observable(dict(data, observed_tool_use_id=tool_id)))
            if data.get('hook_event_name') == 'PreToolUse' and self.bootstrap:
                return {'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'deny',
                                               'permissionDecisionReason': 'Bootstrap has no tool authority'}}
            if data.get('hook_event_name') == 'PreToolUse' and self.probe and data.get('tool_name') not in ('Read','Glob','Grep','Agent','Task','AskUserQuestion','TaskOutput','TaskGet','TaskList'):
                return {'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'deny',
                                               'permissionDecisionReason': 'Read-only capability probe'}}
            return {'continue_': True}  # observation, not permissionDecision=allow

        async def permission(name, inputs, context):
            if self.bootstrap:
                return sdk.PermissionResultDeny(message='No tools during bootstrap')
            kind = 'question' if name == 'AskUserQuestion' else 'permission'
            r = await self.relay(kind, {'tool': name, 'input': inputs, 'tool_use_id': getattr(context,'tool_use_id',None)})
            if r['action'] == 'deny':
                return sdk.PermissionResultDeny(message=r['basis'])
            if kind == 'question':
                require(set(r['answers']) == {q['question'] for q in inputs.get('questions',[])}, 'answer keys do not match Claude questions')
                return sdk.PermissionResultAllow(updated_input={**inputs,'answers':r['answers']})
            return sdk.PermissionResultAllow(updated_input=inputs)  # exact call, no rule updates

        options = dict(cwd=self.config['workspace'], resume=self.sid, fork_session=False,
                       permission_mode='default', can_use_tool=permission,
                       system_prompt={'type':'preset','preset':'claude_code','append':ROLE},
                       setting_sources=self.config.get('settings',[]), max_turns=self.config['max_model_turns'],
                       hooks={name:[sdk.HookMatcher(hooks=[hook])] for name in
                              ('PreToolUse','PostToolUse','PostToolUseFailure','SubagentStart','SubagentStop')})
        if self.config.get('model'): options['model'] = self.config['model']
        if self.config.get('budget_usd'): options['max_budget_usd'] = self.config['budget_usd']
        self.client = sdk.ClaudeSDKClient(options=sdk.ClaudeAgentOptions(**options))
        await self.client.connect()
        result = await self.run('Connection bootstrap only. Do not use tools. Reply CONNECTED.', probe=True)
        require(result['ok'], 'Claude bootstrap did not succeed')
        self.bootstrap = False

    def identity(self, sid):
        require(isinstance(sid,str) and bool(sid),'Claude supplied no session ID')
        require(self.sid in (None,sid),'Claude replaced the recorded session')
        self.bind(sid); self.sid = sid

    async def run(self, prompt, skill=None, probe=False):
        self.probe = probe
        await self.client.query(prompt)
        result = None
        async for msg in self.client.receive_response():
            if isinstance(msg,self.sdk.SystemMessage) and msg.subtype == 'init': self.identity(msg.data.get('session_id'))
            if isinstance(msg,self.sdk.ResultMessage):
                self.identity(msg.session_id)
                result = {'ok': not msg.is_error and msg.subtype == 'success','session_id':msg.session_id,
                          'text':msg.result,'subtype':msg.subtype,'usage':msg.usage,'cost_usd':msg.total_cost_usd}
            self.emit('claude.'+type(msg).__name__,observable(msg))
        require(result is not None,'Claude stream ended without a result; do not replay blindly')
        return result

    async def close(self):
        if self.client: await self.client.disconnect()


class Rpc:
    """One reader, correlated replies and concurrent pending callbacks. Newline JSON stdio."""
    def __init__(self, process, handler):
        self.process, self.handler = process, handler
        self.pending, self.callbacks = {}, {}
        self.events = asyncio.Queue()
        self.serial = 0
        self.write_lock = asyncio.Lock()
        self.reader = asyncio.create_task(self.read())

    async def write(self, value):
        async with self.write_lock:
            require(self.process.returncode is None,'app-server exited')
            self.process.stdin.write((json.dumps(value,ensure_ascii=False)+'\n').encode())
            await self.process.stdin.drain()

    async def call(self, method, params, timeout=30):
        self.serial += 1; rid = self.serial
        future = asyncio.get_running_loop().create_future(); self.pending[rid] = future
        try:
            await self.write({'id':rid,'method':method,'params':params})
            return await asyncio.wait_for(future,timeout)
        finally:
            self.pending.pop(rid,None)

    async def respond(self, msg):
        try:
            result = await self.handler(msg)
            await self.write({'id':msg['id'],'result':result})
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            with contextlib.suppress(Exception):
                await self.write({'id':msg['id'],'error':{'code':-32601,'message':str(exc)}})
            await self.events.put({'method':'bridge/error','params':{'error':str(exc)}})

    async def read(self):
        failure = 'app-server disconnected'
        try:
            while raw := await self.process.stdout.readline():
                msg = json.loads(raw)
                require(isinstance(msg,dict),'malformed RPC message')
                if 'method' in msg and 'id' in msg:
                    p = msg.get('params',{}); key = (p.get('threadId'),str(msg['id']))
                    require(key not in self.callbacks,'duplicate live RPC request')
                    task = asyncio.create_task(self.respond(msg))
                    self.callbacks[key] = (task,p.get('turnId'))
                    task.add_done_callback(lambda done,key=key:self.callbacks.pop(key,None))
                elif 'id' in msg:
                    f = self.pending.get(msg['id'])
                    if f and not f.done():
                        if 'error' in msg: f.set_exception(BridgeError('RPC error: '+json.dumps(msg['error'])))
                        else: f.set_result(msg.get('result'))
                elif 'method' in msg:
                    p = msg.get('params',{})
                    if msg['method'] == 'serverRequest/resolved':
                        item = self.callbacks.get((p.get('threadId'),str(p.get('requestId'))))
                        if item: item[0].cancel()
                    if msg['method'] == 'turn/completed':
                        for (thread,_),(task,turn) in list(self.callbacks.items()):
                            if turn == p.get('turn',{}).get('id') and thread == p.get('threadId'): task.cancel()
                    await self.events.put(msg)
        except Exception as exc:
            failure = str(exc)
        finally:
            for f in self.pending.values():
                if not f.done(): f.set_exception(BridgeError(failure))
            await self.events.put({'method':'bridge/disconnected','params':{'error':failure}})

    async def close(self):
        tasks = [x[0] for x in self.callbacks.values()]
        for t in tasks: t.cancel()
        await asyncio.gather(*tasks,return_exceptions=True)
        if self.process.returncode is None:
            self.process.terminate()
            try: await asyncio.wait_for(self.process.wait(),5)
            except asyncio.TimeoutError:
                self.process.kill(); await self.process.wait()
        await self.reader


class CodexAdapter:
    def __init__(self,config,sid,emit,bind,relay,*,command=None):
        self.config,self.sid,self.emit,self.bind,self.relay = config,sid,emit,bind,relay
        self.command = command or ['codex','app-server','--listen','stdio://']
        self.rpc = None; self.turn_id = None; self.root_id = None; self.stderr = None

    async def connect(self):
        p = Path(self.config['runtime_root'])/(self.config['worker']+'.codex.stderr.log')
        require(not p.is_symlink(),'unsafe stderr log path')
        self.stderr = p.open('ab'); os.chmod(p,0o600)
        proc = await asyncio.create_subprocess_exec(*self.command,cwd=self.config['workspace'],
               stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=self.stderr,limit=16*1024*1024)
        self.rpc = Rpc(proc,self.request)
        info = await self.rpc.call('initialize',{'clientInfo':{'name':'ouroboros_runtime','version':'0.1.0'}})
        self.emit('codex.initialized',info or {})
        await self.rpc.write({'method':'initialized','params':{}})
        params = {'cwd':self.config['workspace'],'approvalPolicy':'on-request','sandbox':'workspace-write'}
        if self.config.get('model'): params['model'] = self.config['model']
        if self.sid: params['threadId'] = self.sid
        r = await self.rpc.call('thread/resume' if self.sid else 'thread/start',params)
        sid = r['thread']['id']
        require(isinstance(sid,str) and sid and self.sid in (None,sid),'Codex replaced or omitted the recorded thread')
        self.sid = sid; self.bind(sid); self.root_id = r['thread'].get('sessionId')
        self.emit('codex.thread_bound',{'thread_id':sid,'root_id':self.root_id})

    async def request(self,msg):
        p,method = msg.get('params',{}),msg['method']
        target = p.get('threadId')
        require(self.sid and target,'missing request thread')
        if target != self.sid:
            t = (await self.rpc.call('thread/read',{'threadId':target}))['thread']
            require(t.get('id') == target and self.root_id and t.get('sessionId') == self.root_id,'request from another session tree')
        else:
            require(not p.get('turnId') or self.turn_id in (None,p['turnId']),'request from a stale turn')
        payload = {'method':method,'rpc_id':msg['id'],'params':p}
        if method == 'item/tool/requestUserInput':
            # May be an app side-effect approval, so structured inputs are human-only by default.
            r = await self.relay('permission',payload)
            if r['action'] == 'deny': return {'answers':{}}
            answers = r.get('answers',{})
            require(set(answers) == {q['id'] for q in p.get('questions',[])},'answer keys do not match Codex question IDs')
            return {'answers':{k:{'answers':v if isinstance(v,list) else [v]} for k,v in answers.items()}}
        if method == 'item/fileChange/requestApproval':
            # Request callbacks may omit paths. Re-read the exact host item, never infer
            # scope from the reason string or model-provided prose.
            try:
                thread = (await self.rpc.call('thread/read',{'threadId':target,'includeTurns':True}))['thread']
                require(thread.get('id') == target,'file-change read-back thread mismatch')
                for turn in thread.get('turns',[]):
                    if turn.get('id') != p.get('turnId'): continue
                    for item in turn.get('items',[]):
                        if item.get('id') == p.get('itemId') and item.get('type') == 'fileChange' and item.get('status') == 'inProgress':
                            payload['observed_changes'] = item.get('changes')
            except (BridgeError,KeyError,TypeError):
                pass  # Human route remains available; L1 cannot infer missing scope.
        if method in ('item/commandExecution/requestApproval','item/fileChange/requestApproval'):
            r = await self.relay('permission',payload)
            return {'decision':'accept' if r['action'] == 'allow' else 'decline'}
        if method == 'item/permissions/requestApproval':
            self.emit('codex.permission_declined',payload)
            return {'permissions':{},'scope':'turn'}
        if method == 'mcpServer/elicitation/request':
            self.emit('codex.elicitation_declined',payload)
            return {'action':'decline','content':None}
        raise BridgeError('unsupported server request: '+method)

    async def read_turn(self):
        t = (await self.rpc.call('thread/read',{'threadId':self.sid,'includeTurns':True}))['thread']
        require(t.get('id') == self.sid,'thread/read returned a different thread')
        return next((x for x in t.get('turns',[]) if x['id'] == self.turn_id),None)

    async def run(self,prompt,skill=None,probe=False):
        text = ROLE+'\n\n'+prompt
        if skill: text = '$'+skill['name']+'\n'+text
        inputs = [{'type':'text','text':text}]
        if skill: inputs.append({'type':'skill',**skill})
        policy = {'type':'readOnly','networkAccess':False} if probe else {
            'type':'workspaceWrite','writableRoots':[self.config['workspace']],'networkAccess':False}
        r = await self.rpc.call('turn/start',{'threadId':self.sid,'input':inputs,
            'cwd':self.config['workspace'],'approvalPolicy':'on-request','sandboxPolicy':policy})
        self.turn_id = r['turn']['id']
        self.emit('codex.turn_bound',{'thread_id':self.sid,'turn_id':self.turn_id,'skill_input':skill})
        try:
            while True:
                observed = None
                try:
                    msg = await asyncio.wait_for(self.rpc.events.get(),2)
                except asyncio.TimeoutError:
                    observed = await self.read_turn()
                else:
                    method,p = msg['method'],msg.get('params',{})
                    if method.startswith('bridge/'): raise BridgeError(p.get('error',method))
                    if 'reasoning' not in method: self.emit('codex.event',observable(msg))
                    if method == 'turn/completed' and p.get('turn',{}).get('id') == self.turn_id:
                        require(p.get('threadId') in (None,self.sid),'completion from another thread')
                        observed = await self.read_turn()  # notification is a wakeup, not authority
                if observed and observed.get('status') in ('completed','failed','interrupted'):
                    return {'ok':observed['status'] == 'completed','session_id':self.sid,
                            'turn_id':self.turn_id,'status':observed['status'],
                            'text':'\n'.join(x.get('text','') for x in observed.get('items',[]) if x.get('type') == 'agentMessage'),
                            'error':observed.get('error')}
        finally:
            self.turn_id = None

    async def close(self):
        if self.rpc: await self.rpc.close()
        if self.stderr: self.stderr.close()
