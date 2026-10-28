#!/usr/bin/env python3
"""Local Hermes bridge. Optional Pillow/pypdf parse selected attachments; no Hermes config edits."""
import json, os, secrets, sqlite3, subprocess, threading, time, uuid
from contextlib import contextmanager
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs
from pocket_files import Files, MAX_FILE
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent
# STAGING GUARD: refusing absent/live/aliased data is intentional until Gate C.
if not os.environ.get('HERMES_POCKET_DATA'):
    raise RuntimeError('Staged HERMES_POCKET_DATA is required; live defaults disabled')
DATA = Path(os.environ['HERMES_POCKET_DATA'])
if DATA.is_symlink() or not DATA.resolve().is_relative_to(ROOT.parent) or DATA.resolve() == ROOT.parent:
    raise RuntimeError('Data must be a new directory inside the private implementation tree')
DATA.mkdir(mode=0o700, parents=True, exist_ok=True)
os.chmod(DATA, 0o700)
TOKEN_FILE = DATA/'pairing-token'
if not TOKEN_FILE.exists():
    fd = os.open(TOKEN_FILE, os.O_CREAT|os.O_EXCL|os.O_WRONLY, 0o600)
    with os.fdopen(fd, 'w') as f: f.write(secrets.token_urlsafe(32))
TOKEN = TOKEN_FILE.read_text().strip()
HERMES = os.environ.get('HERMES_BIN', str(ROOT/'disabled-hermes'))
if not Path(HERMES).resolve().is_relative_to(ROOT.parent):
    raise RuntimeError('Only stage-owned synthetic Hermes fixture executables are permitted')
PORT = int(os.environ.get('HERMES_POCKET_PORT', '0'))
if PORT == 8766: raise RuntimeError('Live Pocket port is forbidden in staging')
LOCK = threading.Lock()
RUNNING = set()

@contextmanager
def db():
    c = sqlite3.connect(DATA/'chats.sqlite3', timeout=10)
    c.row_factory = sqlite3.Row
    try:
        with c:
            yield c
    finally:
        c.close()

with db() as c:
    c.execute('CREATE TABLE IF NOT EXISTS chats (id TEXT PRIMARY KEY, title TEXT, session TEXT, messages TEXT, state TEXT, error TEXT)')
    columns = [r[1] for r in c.execute('PRAGMA table_info(chats)')]
    for column in ('mode','model'):
        if column not in columns: c.execute(f'ALTER TABLE chats ADD COLUMN {column} TEXT')
    c.execute("UPDATE chats SET state='error', error='Bridge restarted during a reply. Check Hermes before retrying.' WHERE state='running'")

FILES = Files(DATA, db)
from evolution_api import EvolutionService
EVOLUTION = EvolutionService(DATA, ROOT.parent)

def probe():
    try:
        r = subprocess.run([HERMES, 'chat', '--help'], capture_output=True, text=True, timeout=20)
        help_text = r.stdout+r.stderr
        supported = r.returncode == 0 and all(x in help_text for x in ('--format', 'stream-json', '--resume'))
        return {'ready': supported, 'local_ready': supported and all(x in help_text for x in ('--provider','--base-url','--api-key','--model')), 'detail': 'Hermes interface detected' if supported else 'This Hermes version needs an adapter check. Send the output of hermes chat --help; no upgrade has been made.'}
    except (OSError, subprocess.TimeoutExpired):
        return {'ready': False, 'detail': 'Hermes executable unavailable. Check HERMES_BIN and your Termux installation.'}

CAPABILITY = None
ADAPTER = ROOT/'hermes_adapter.py'
HERMES_PYTHON = str(Path(HERMES).parent/'python3')
CLI_PROBE = probe

def probe():
    native = CLI_PROBE()
    if native.get('ready'):
        native['adapter'] = 'native-stream-json'
        return native
    if not ADAPTER.is_file() or not Path(HERMES_PYTHON).is_file():
        return native
    try:
        r = subprocess.run([HERMES_PYTHON, str(ADAPTER), '--probe'], capture_output=True, text=True, timeout=30)
        status = json.loads(r.stdout.strip().splitlines()[-1])
        if r.returncode == 0 and status.get('ready'):
            return status
    except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
        pass
    return native

def local_models():
    try:
        with urlopen('http://127.0.0.1:11434/api/tags', timeout=3) as r:
            models = json.load(r).get('models',[])
        return {'online':True,'models':[m['name'] for m in models if isinstance(m.get('name'),str)]}
    except Exception:
        return {'online':False,'models':[], 'detail':'Ollama is not running. In a separate Termux session run: ollama serve'}

def read_chat(cid):
    with db() as c: row = c.execute('SELECT * FROM chats WHERE id=?', (cid,)).fetchone()
    if row is None: return None
    out = dict(row); out['messages'] = json.loads(out['messages']); return out

def save(cid, messages, session, state, error=''):
    with db() as c:
        c.execute('UPDATE chats SET messages=?, session=?, state=?, error=? WHERE id=?', (json.dumps(messages),session,state,error,cid))

def run_turn(cid, prompt, smoke=False, attachment_text='', images=None):
    chat = read_chat(cid); messages = chat['messages']; sid = chat['session']
    sdk = CAPABILITY.get('adapter') == 'installed-hermes-sdk'
    args = [HERMES_PYTHON, str(ADAPTER)] if sdk else [HERMES, 'chat', '-q', prompt, '--format', 'stream-json']
    if not sdk:
        if chat['mode'] == 'local':
            args += ['--provider','custom','--base-url','http://127.0.0.1:11434/v1','--api-key','ollama','--model',chat['model']]
        if sid: args += ['--resume', sid]
    messages.append({'role':'assistant', 'text':'', 'activity':'Starting Hermes…'})
    save(cid, messages, sid, 'running')
    proc = None; errors = []; completed = False
    try:
        proc = subprocess.Popen(args, stdin=subprocess.PIPE if sdk else subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1, cwd=str(Path.home()))
        if sdk:
            json.dump({'mode':chat['mode'], 'model':chat['model'], 'resume':sid, 'prompt':prompt, 'smoke':smoke, 'attachment_text':attachment_text, 'images':images or [], 'workspace':str(FILES.workspace(cid))},proc.stdin)
            proc.stdin.close()
        def drain():
            for line in proc.stderr:
                errors.append(line)
                if len(errors)>30: errors.pop(0)
        t = threading.Thread(target=drain, daemon=True); t.start()
        for line in proc.stdout:
            try: event = json.loads(line)
            except json.JSONDecodeError: continue
            if not isinstance(event, dict): continue
            kind = event.get('type')
            if event.get('session_id'): sid = str(event['session_id'])
            for field in ('provider', 'model', 'private_memory_attached', 'fallback_enabled'):
                if field in event: messages[-1][field] = event[field]
            if kind == 'text':
                messages[-1]['text'] += str(event.get('text',''))
                messages[-1]['activity'] = 'Writing…'
            elif kind in ('tool_start', 'tool_complete'):
                tools = messages[-1].setdefault('tools', [])
                tid = str(event.get('id', 'unknown'))[:120]
                tool = next((x for x in tools if x['id'] == tid), None)
                if tool is None and len(tools) < 60:
                    tool = {'id':tid, 'name':str(event.get('name', 'tool'))[:120]}
                    tools.append(tool)
                if tool is not None:
                    tool.update({'status':'running' if kind=='tool_start' else 'completed'})
                    for field in ('arguments','output'):
                        if field in event: tool[field] = str(event[field])[:12000]
                messages[-1]['activity'] = ('Using ' if kind=='tool_start' else 'Finished ')+str(event.get('name', 'tool'))[:120]
                if kind=='tool_start': messages[-1].setdefault('tool_names', []).append(str(event.get('name','tool'))[:120])
            elif kind == 'tool_use':
                tool_name = str(event.get('name','tool'))
                messages[-1]['activity'] = 'Using '+tool_name
                messages[-1].setdefault('tool_names', []).append(tool_name)
            elif kind == 'tool_result': messages[-1]['activity'] = 'Working…'
            elif kind == 'result':
                if event.get('text') is not None: messages[-1]['text'] = str(event['text'])
                if event.get('error') or event.get('exit_code', 0):
                    raise RuntimeError(str(event.get('error') or 'Hermes reported an incomplete turn.'))
                completed = True
            save(cid, messages, sid, 'running')
        code = proc.wait(timeout=10); t.join(timeout=2)
        if code or not completed:
            raise RuntimeError('Hermes did not complete this turn. Check the Hermes terminal for credentials or approval prompts. Exit: '+str(code))
        if not sid:
            raise RuntimeError('No Hermes session ID returned. Continuation disabled to avoid losing context.')
        messages[-1]['activity'] = ''
        for tool in messages[-1].get('tools', []):
            if tool['status']=='running': tool['status']='incomplete'
        save(cid, messages, sid, 'idle')
    except Exception as exc:
        if proc and proc.poll() is None: proc.terminate()
        messages[-1]['activity'] = ''
        for tool in messages[-1].get('tools', []):
            if tool['status']=='running': tool['status']='incomplete'
        save(cid, messages, sid, 'error', str(exc))
    finally:
        if proc:
            if proc.poll() is None:
                try: proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill(); proc.wait()
            proc.stdout.close()
            if 't' in locals(): t.join(timeout=2)
            proc.stderr.close()
            if errors:
                diagnostic = DATA/'last-hermes-diagnostic.log'
                fd = os.open(diagnostic, os.O_CREAT|os.O_TRUNC|os.O_WRONLY, 0o600)
                with os.fdopen(fd, 'w') as f: f.write(''.join(errors))
        with LOCK: RUNNING.discard(cid)

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_): pass
    def reply(self, code, data, mime='application/json'):
        raw = json.dumps(data).encode() if mime=='application/json' else data
        self.send_response(code); self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; object-src 'none'; base-uri 'none'; form-action 'self'")
        self.end_headers(); self.wfile.write(raw)
    def allowed(self):
        host = self.headers.get('Host','')
        if host not in (f'127.0.0.1:{PORT}',f'localhost:{PORT}'):
            self.reply(403, {'error':'Local access only'}); return False
        if self.path.startswith('/api/') and not secrets.compare_digest(self.headers.get('Authorization',''), 'Bearer '+TOKEN):
            self.reply(401, {'error':'Pair this device using the token shown in Termux.'}); return False
        return True
    def do_GET(self):
        if not self.allowed(): return
        path = urlsplit(self.path).path
        if path == '/api/status': return self.reply(200, {**CAPABILITY,'interface_version':'0.2.0'})
        if path.startswith('/api/evolution/'):
            try: return self.reply(200, EVOLUTION.get(path.removeprefix('/api/evolution/'),parse_qs(urlsplit(self.path).query)))
            except (ValueError,OSError,KeyError,TypeError,sqlite3.Error): return self.reply(400,{'error':'Evolution request rejected or source unavailable'})
        if path == '/api/models': return self.reply(200, local_models())
        if path.startswith('/api/files/') or path in ('/api/artifacts','/api/drafts'):
            cid=parse_qs(urlsplit(self.path).query).get('chat',[''])[0]
            if not read_chat(cid): return self.reply(404, {'error':'Conversation not found'})
            try:
                if path=='/api/artifacts': result=FILES.artifacts(cid)
                elif path=='/api/drafts': result=FILES.drafts(cid)
                else: result=FILES.content(cid,path.rsplit('/',1)[-1])
                return self.reply(200,result)
            except (ValueError,OSError) as exc: return self.reply(400,{'error':str(exc)})
        if path == '/api/chats':
            with db() as c: rows = c.execute('SELECT id,title,state,mode,model FROM chats ORDER BY rowid DESC').fetchall()
            return self.reply(200, [dict(r) for r in rows])
        if path.startswith('/api/chats/'):
            chat = read_chat(path.rsplit('/',1)[-1])
            return self.reply(200 if chat else 404, chat or {'error':'Conversation not found'})
        assets = {'/':('index.html','text/html; charset=utf-8'),'/app.js':('app.js','text/javascript'),'/style.css':('style.css','text/css')}
        assets.update({'/evolution.js':('evolution.js','text/javascript'),'/evolution.css':('evolution.css','text/css')})
        if path in assets:
            name,mime = assets[path]; return self.reply(200,(ROOT/'web'/name).read_bytes(),mime)
        self.reply(404, {'error':'Not found'})
    def do_POST(self):
        if not self.allowed(): return
        origin = self.headers.get('Origin')
        if origin and origin not in (f'http://127.0.0.1:{PORT}',f'http://localhost:{PORT}'):
            return self.reply(403, {'error':'Origin rejected'})
        try:
            size = int(self.headers.get('Content-Length','0'))
            maximum=((MAX_FILE+2)//3)*4+4096 if self.path=='/api/files/upload' else 65536
            if size < 1 or size > maximum: raise ValueError()
            body = json.loads(self.rfile.read(size))
            if not isinstance(body,dict): raise ValueError()
        except (ValueError, json.JSONDecodeError): return self.reply(400, {'error':'Invalid request'})
        if self.path.startswith('/api/evolution/'):
            try: return self.reply(200, EVOLUTION.post(self.path.removeprefix('/api/evolution/'),body))
            except (ValueError,OSError,KeyError,TypeError,sqlite3.Error): return self.reply(400,{'error':'Evolution request rejected; review scope, version and consent'})
        if self.path in ('/api/files/upload','/api/files/remove'):
            cid=body.get('chat')
            if not isinstance(cid,str) or not read_chat(cid): return self.reply(404,{'error':'Conversation not found'})
            try:
                with LOCK:
                    if self.path.endswith('/upload'): return self.reply(201,FILES.upload(cid,body))
                    FILES.remove(cid,body.get('id'))
                return self.reply(200,{'ok':True})
            except (ValueError,OSError) as exc: return self.reply(400,{'error':str(exc)})
        if self.path == '/api/chats':
            mode = body.get('mode','cloud'); model = body.get('model','')
            if mode not in ('cloud','local'): return self.reply(400, {'error':'Invalid mode'})
            if not isinstance(model,str) or len(model)>256: return self.reply(400, {'error':'Invalid model'})
            if mode == 'local':
                if not CAPABILITY.get('local_ready'): return self.reply(409, {'error':'Local provider flags need verification on this Hermes version.'})
                if model not in local_models()['models']: return self.reply(409, {'error':'Start Ollama and select an installed model first.'})
            cid = uuid.uuid4().hex
            with db() as c: c.execute('INSERT INTO chats VALUES(?,?,?,?,?,?,?,?)',(cid,'New conversation',None,'[]','idle','',mode,model))
            return self.reply(201, {'id':cid})
        if self.path == '/api/send':
            if not CAPABILITY['ready']: return self.reply(409, {'error':CAPABILITY['detail']})
            cid = body.get('id'); prompt = body.get('message')
            if not isinstance(cid,str) or not isinstance(prompt,str) or not prompt.strip() or len(prompt)>16000:
                return self.reply(400, {'error':'Enter a message of up to 16000 characters.'})
            with LOCK:
                chat = read_chat(cid)
                if not chat: return self.reply(404, {'error':'Conversation not found'})
                if RUNNING: return self.reply(409, {'error':'Wait for the current Hermes reply to finish.'})
                if chat['messages'] and not chat['session']:
                    return self.reply(409, {'error':'No verified session ID for this chat. Start a new conversation.'})
                try:
                    attachments,attachment_text,images=FILES.prepare(cid,body.get('attachments',[]),chat['mode'])
                except (ValueError,OSError) as exc: return self.reply(400,{'error':str(exc)})
                if attachments and chat['mode']=='cloud' and body.get('consent') is not True:
                    return self.reply(400,{'error':'Confirm Cloud attachment sharing before sending.'})
                if attachments and CAPABILITY.get('adapter')!='installed-hermes-sdk':
                    return self.reply(409,{'error':'Attachments require the installed SDK adapter.'})
                RUNNING.add(cid)
                chat['messages'].append({'role':'user','text':prompt, 'attachments':attachments})
                save(cid,chat['messages'],chat['session'],'running')
                with db() as c: c.execute('UPDATE chats SET title=? WHERE id=? AND title=?',(prompt[:50],cid,'New conversation'))
                threading.Thread(target=run_turn,args=(cid,prompt,body.get('smoke') is True,attachment_text,images),daemon=True).start()
            return self.reply(202, {'ok':True})
        self.reply(404, {'error':'Not found'})

if __name__ == '__main__':
    CAPABILITY = {'ready':False,'local_ready':False,'detail':'ISOLATED EVOLUTION STAGING: workbench and synthetic fixtures only. No live agent execution.'}
    print('Hermes Pocket — isolated Evolution staging', flush=True)
    print(CAPABILITY['detail'], flush=True)
    server = ThreadingHTTPServer(('127.0.0.1',PORT),Handler)
    PORT = server.server_port
    print(f'Open http://127.0.0.1:{PORT}/ (private staging only)', flush=True)
    print('Pairing secret kept private in the staged data directory; never logged.', flush=True)
    server.serve_forever()
