"""Bounded local worker utilities and disabled JCode integration.
Not an OS sandbox. Real JCode execution is deliberately unavailable in Phase 1.
"""
import json
import os
from pathlib import Path
import resource
import selectors
import signal
import subprocess
import time
import uuid
from evolution import Denied, digest, packed, secret_scan

SAFE_ENV_KEYS={'HOME','PATH','PREFIX','TMPDIR','LANG','TERM','SSL_CERT_FILE','SSL_CERT_DIR','ANDROID_DATA','ANDROID_ROOT','LD_LIBRARY_PATH','USER','UID'}
def jcode_environment(environ):
    env={k:v for k,v in environ.items() if k in SAFE_ENV_KEYS}
    env.update(JCODE_MEMORY_ENABLED='false',JCODE_MEMORY_SIDECAR_ENABLED='false',JCODE_PERSIST_MEMORY_INJECTIONS='false',JCODE_TOOL_PROFILE='none',JCODE_TOOLS='',JCODE_DISABLE_BASE_TOOLS='true',JCODE_SWARM_ENABLED='false',JCODE_AUTO_POKE='false',JCODE_CHECK_UPDATES='false',JCODE_CROSS_PROVIDER_FAILOVER='off',JCODE_SAME_PROVIDER_ACCOUNT_FAILOVER='false')
    for name in ['TURN_START','TURN_END','SESSION_START','SESSION_END','PRE_TOOL','POST_TOOL','PRE_TOOL_TRANSFORM','POST_TOOL_FEEDBACK']: env['JCODE_HOOK_'+name]=''
    return env

def sanitized(text):
    text=''.join(c for c in text if c in '\n\t' or (ord(c)>=32 and ord(c)!=127))
    return '[REDACTED UNSAFE OUTPUT]' if secret_scan(text) else text[:8000]

def bounded_fixture(argv,cwd,allowed,wall=2,cpu=2,max_output=8192,cancel=None,env=None,rss_limit_mib=None,min_available_mib=None,available=None):
    """Host test utility: argv[0] must match an exact registered test worker.
    Not exposed as a user/API command and never used to run draft instructions.
    """
    if not argv or Path(argv[0]).resolve()!=Path(allowed).resolve(): raise Denied('Unregistered fixture executable')
    if not 0<wall<=120 or not 0<cpu<=120 or not 0<max_output<=98304: raise Denied('Invalid worker budget')
    def limits(): resource.setrlimit(resource.RLIMIT_CPU,(cpu,cpu)); os.nice(10)
    p=subprocess.Popen(argv,cwd=cwd,env=env or {'PATH':os.environ['PATH']},stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True,preexec_fn=limits)
    start=time.monotonic(); out=bytearray(); err=bytearray(); reason=None; peak_rss=0; sel=selectors.DefaultSelector()
    for stream,key in ((p.stdout,'out'),(p.stderr,'err')): os.set_blocking(stream.fileno(),False); sel.register(stream,selectors.EVENT_READ,key)
    try:
        while sel.get_map():
            try:
                values=Path(f'/proc/{p.pid}/status').read_text().splitlines()
                rss=next((int(x.split()[1])/1024 for x in values if x.startswith('VmRSS:')),0)
                peak_rss=max(peak_rss,rss)
                if rss_limit_mib is not None and rss>rss_limit_mib: reason='rss_budget'
            except OSError: pass
            if min_available_mib is not None and available is not None and available()<min_available_mib: reason='available_memory_budget'
            if cancel and cancel(): reason='cancelled'
            if time.monotonic()-start>wall: reason='wall_budget'
            if len(out)+len(err)>=max_output: reason='output_budget'
            if reason: break
            for key,_ in sel.select(.02):
                chunk=os.read(key.fileobj.fileno(),min(4096,max_output-len(out)-len(err)))
                if not chunk: sel.unregister(key.fileobj)
                else: (out if key.data=='out' else err).extend(chunk)
        if not reason:
            try: p.wait(timeout=max(.01,wall-(time.monotonic()-start)))
            except subprocess.TimeoutExpired: reason='wall_budget'
    finally:
        # Always terminate descendants in this owned group, even if the parent exited.
        try: os.killpg(p.pid,signal.SIGKILL)
        except ProcessLookupError: pass
        p.wait(timeout=3); sel.close(); p.stdout.close(); p.stderr.close()
    return {'status':reason or ('returned' if p.returncode==0 else 'failed'),'exit_code':p.returncode,'stdout':sanitized(out.decode(errors='replace')),'stderr':sanitized(err.decode(errors='replace')),'bytes':len(out)+len(err),'elapsed':time.monotonic()-start,'owned_pid':p.pid,'peak_rss_MiB':peak_rss}

class JCodeBroker:
    def __init__(self,store): self.store=store
    def submit(self,s,packet):
        s.check(True)
        required={'kind','specification','synthetic','provider','wall_seconds','max_output_bytes'}
        if not isinstance(packet,dict) or set(packet)!=required: raise Denied('Strict task schema required')
        if packet['kind'] not in {'plan','review','propose_patch'} or packet['synthetic'] is not True or packet['provider']!='antigravity': raise Denied('Only optional synthetic Antigravity tasks allowed')
        text=packet['specification']
        if not isinstance(text,str) or not text.strip() or len(text)>8000 or secret_scan(text) or any(x in text.lower() for x in ('/.hermes','/.jcode','state.db','chats.sqlite','credential','private key','raw database','http://','https://')): raise Denied('Unsafe task packet')
        if not isinstance(packet['wall_seconds'],int) or not 1<=packet['wall_seconds']<=90 or not isinstance(packet['max_output_bytes'],int) or not 1<=packet['max_output_bytes']<=98304: raise Denied('Invalid budgets')
        id=uuid.uuid4().hex
        result={'id':id,'request_hash':digest(packet),'project':s.project,'provider':'antigravity','status':'disabled_pending_private_reauthentication_and_review','wall_seconds':packet['wall_seconds'],'max_output_bytes':packet['max_output_bytes'],'result_hash':None,'tools':'none','autonomous_execution':False,'os_sandbox':False,'credential_copy':False,'provider_fallback':False}
        with self.store.db() as c: c.execute('INSERT INTO tasks VALUES(?,?,?)',(id,s.project,packed(result))); self.store.audit(s,'jcode_task_blocked',result,c)
        return result
    @staticmethod
    def parse_result(raw):
        if not isinstance(raw,str) or len(raw.encode())>98304 or any(ord(c)<32 and c not in '\n\t\r' for c in raw) or secret_scan(raw): raise Denied('Unsafe worker output')
        if '<tool' in raw.lower() or 'tool_call' in raw.lower(): raise Denied('Tool markup rejected')
        try: value=json.loads(raw)
        except ValueError: raise Denied('Invalid worker JSON')
        if not isinstance(value,dict) or set(value)!={'summary','risks','proposed_changes'} or not isinstance(value['summary'],str) or not all(isinstance(value[k],list) and all(isinstance(x,str) for x in value[k]) for k in ('risks','proposed_changes')): raise Denied('Unexpected worker schema')
        return value
