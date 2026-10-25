"""Native host transports. No keystroke injection, implicit approval or guessed session IDs."""
from __future__ import annotations
import asyncio
import contextlib
import dataclasses
import json
import os
from pathlib import Path
from .store import BridgeError, require

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
        self.commands = set()

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
                       system_prompt={'type':'preset','preset':'claude_code'},
                       setting_sources=self.config.get('settings',[]), max_turns=self.config['max_model_turns'],
                       hooks={name:[sdk.HookMatcher(hooks=[hook])] for name in
                              ('PreToolUse','PostToolUse','PostToolUseFailure','SubagentStart','SubagentStop')})
        if self.config.get('model'): options['model'] = self.config['model']
        if self.config.get('budget_usd'): options['max_budget_usd'] = self.config['budget_usd']
        if self.config.get('dryforge_plugin'):
            root = Path(self.config['dryforge_plugin'])
            manifest = root/'.claude-plugin/plugin.json'
            require(manifest.is_file() and json.loads(manifest.read_text()).get('name') == 'dryforge',
                    '--dryforge-plugin must identify an installed Claude Code Dryforge plugin')
            options['plugins'] = [{'type':'local','path':str(root)}]
        self.client = sdk.ClaudeSDKClient(options=sdk.ClaudeAgentOptions(**options))
        await self.client.connect()
        result = await self.run('Connection bootstrap only. Do not use tools. Reply CONNECTED.', probe=True)
        require(result['ok'], 'Claude bootstrap did not succeed')
        self.bootstrap = False

    def identity(self, sid):
        require(isinstance(sid,str) and bool(sid),'Claude supplied no session ID')
        require(self.sid in (None,sid),'Claude replaced the recorded session')
        self.bind(sid); self.sid = sid

    async def resolve_skill(self, name):
        require(name in self.commands,
                f'Claude Code skill /{name} is unavailable in this session; load the installed Dryforge '
                'plugin with --dryforge-plugin or explicitly selected --load-settings sources')
        return {'name':name}

    async def run(self, prompt, skill=None, probe=False):
        self.probe = probe
        if skill: prompt = '/'+skill['name']+' '+prompt
        await self.client.query(prompt)
        result = None
        async for msg in self.client.receive_response():
            if isinstance(msg,self.sdk.SystemMessage) and msg.subtype == 'init':
                self.identity(msg.data.get('session_id'))
                self.commands = set(msg.data.get('slash_commands',[]))
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
    def __init__(self, process, handler, observe=None):
        self.process, self.handler = process, handler
        self.observe = observe
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
                    if self.observe:
                        self.observe(msg)
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
        self.children = set()

    def observe(self, msg):
        """Host lifecycle observations outlive the parent's model turn."""
        method, p = msg['method'], msg.get('params', {})
        item = p.get('item', {})
        if (method in ('item/started', 'item/completed') and item.get('type') == 'subAgentActivity'
                and p.get('threadId') in {self.sid, *self.children}):
            child = item.get('agentThreadId')
            if child and child != self.sid:
                if item.get('kind') in ('started', 'interacted'):
                    self.children.add(child)
                elif item.get('kind') == 'completed':
                    self.children.discard(child)
        if method == 'turn/completed' and p.get('threadId') != self.sid:
            self.children.discard(p.get('threadId'))

    async def reconcile_children(self):
        """Recover missed completion notifications using actual child turn state."""
        for child in tuple(self.children):
            thread = (await self.rpc.call('thread/read', {'threadId':child,'includeTurns':True}))['thread']
            require(thread.get('id') == child and thread.get('sessionId') == self.root_id,
                    'child reconciliation returned another session tree')
            turns = thread.get('turns', [])
            if (turns and turns[-1].get('status') in ('completed','failed','interrupted')
                    and not any(t == child for t, _ in self.rpc.callbacks)):
                self.children.discard(child)

    async def connect(self):
        p = Path(self.config['runtime_root'])/(self.config['worker']+'.codex.stderr.log')
        require(not p.is_symlink(),'unsafe stderr log path')
        self.stderr = p.open('ab'); os.chmod(p,0o600)
        proc = await asyncio.create_subprocess_exec(*self.command,cwd=self.config['workspace'],
               stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=self.stderr,limit=16*1024*1024)
        self.rpc = Rpc(proc,self.request,self.observe)
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
            self.children.add(target)
        else:
            require(not p.get('turnId') or self.turn_id in (None,p['turnId']),'request from a stale turn')
        payload = {'method':method,'rpc_id':msg['id'],'params':p}
        if method == 'item/tool/requestUserInput':
            # Native clarification is the same interface for every caller. MCP
            # elicitation and execution permissions have distinct host methods.
            r = await self.relay('question',payload)
            if r['action'] == 'deny': return {'answers':{}}
            require(r['action'] == 'answer', 'question requires an answer response')
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

    async def resolve_skill(self, name):
        result = await self.rpc.call('skills/list',{'cwds':[self.config['workspace']],'forceReload':True})
        matches = [s for row in result.get('data',[]) if row.get('cwd') == self.config['workspace']
                   for s in row.get('skills',[]) if s.get('name') == name and s.get('enabled') is True]
        require(len(matches) == 1,
                f'Codex skill ${name} must resolve to one enabled installed skill; found {len(matches)}')
        path = matches[0].get('path')
        require(isinstance(path,str) and Path(path).is_absolute() and Path(path).is_file(),
                f'Codex skill ${name} has no readable installed file')
        return {'name':name,'path':path}

    async def run(self,prompt,skill=None,probe=False):
        text = prompt
        if skill: text = '$'+skill['name']+'\n'+text
        inputs = [{'type':'text','text':text}]
        if skill: inputs.append({'type':'skill',**skill})
        policy = {'type':'readOnly','networkAccess':False} if probe else {
            'type':'workspaceWrite','writableRoots':[self.config['workspace']],'networkAccess':False}
        r = await self.rpc.call('turn/start',{'threadId':self.sid,'input':inputs,
            'cwd':self.config['workspace'],'approvalPolicy':'on-request','sandboxPolicy':policy})
        self.turn_id = r['turn']['id']
        self.emit('codex.turn_bound',{'thread_id':self.sid,'turn_id':self.turn_id,'skill_input':skill})
        completed = None
        try:
            while True:
                observed = None
                try:
                    msg = await asyncio.wait_for(self.rpc.events.get(),2)
                except asyncio.TimeoutError:
                    if completed:
                        await self.reconcile_children()
                    else:
                        observed = await self.read_turn()
                else:
                    method,p = msg['method'],msg.get('params',{})
                    if method.startswith('bridge/'): raise BridgeError(p.get('error',method))
                    if 'reasoning' not in method: self.emit('codex.event',observable(msg))
                    if method == 'turn/completed' and p.get('turn',{}).get('id') == self.turn_id:
                        require(p.get('threadId') in (None,self.sid),'completion from another thread')
                        observed = await self.read_turn()  # notification is a wakeup, not authority
                if observed and observed.get('status') in ('completed','failed','interrupted'):
                    completed = {'ok':observed['status'] == 'completed','session_id':self.sid,
                            'turn_id':self.turn_id,'status':observed['status'],
                            'text':'\n'.join(x.get('text','') for x in observed.get('items',[]) if x.get('type') == 'agentMessage'),
                            'error':observed.get('error')}
                    self.emit('codex.parent_turn_completed', {'turn_id':self.turn_id,
                              'pending_children':sorted(self.children)})
                # Do not settle the controller message while its children still
                # own live RPCs or can issue subsequent requests. The parent's
                # model turn may finish normally; the transport drains children
                # under the existing turn/lifetime budget, without a new prompt.
                if completed and not self.children and not self.rpc.callbacks and self.rpc.events.empty():
                    return dict(completed, children_quiescent=True)
        finally:
            self.turn_id = None

    async def close(self):
        if self.rpc: await self.rpc.close()
        if self.stderr: self.stderr.close()
