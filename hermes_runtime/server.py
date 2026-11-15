"""Opt-in authenticated loopback runtime. Run with python -m hermes_runtime.server."""
import argparse
from contextlib import contextmanager
import fcntl
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import sqlite3
import sys
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]
POCKET = ROOT / 'phase2' / 'pocket'
sys.path.insert(0, str(POCKET))
from evolution import Denied, secret_scan
from pocket_files import Files, MAX_FILE
from hermes_runtime.core import Providers, Tasks, Rejected
from hermes_runtime.service import Service
from hermes_runtime.workflows import coding, train, validate_recipe


class Runtime:
    def __init__(self, directory, config, providers=None):
        self.root = Path(directory).absolute()
        if any(p.is_symlink() for p in (self.root, *self.root.parents)):
            raise Rejected('Runtime directory must not contain symlinks')
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root.chmod(0o700)
        # Prevent a second runtime from marking another process's tasks interrupted.
        self.lock_fd = os.open(self.root / 'runtime.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(self.lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(self.lock_fd)
            raise Rejected('This runtime directory is already in use') from None
        self.config = config
        self.providers = providers or Providers(gguf=config.get('gguf'))
        self.tasks = Tasks(self.root)
        self.project = config.get('project', 'personal')
        with self.tasks.db() as c:
            c.execute('CREATE TABLE IF NOT EXISTS runtime_project(project TEXT NOT NULL)')
            previous = c.execute('SELECT project FROM runtime_project').fetchone()
            if previous and previous[0] != self.project:
                os.close(self.lock_fd)
                raise Rejected('Use a separate runtime directory for a different project')
            if not previous:
                c.execute('INSERT INTO runtime_project VALUES(?)', (self.project,))
        self.token_path = self.root / 'pairing-token'
        if self.token_path.is_symlink():
            raise Rejected('Symlink token refused')
        if not self.token_path.exists():
            fd = os.open(self.token_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, 'w') as stream:
                stream.write(secrets.token_urlsafe(32))
        self.token = self.token_path.read_text().strip()
        self.token_path.chmod(0o600)
        if len(self.token) < 32:
            raise Rejected('Invalid pairing token')
        self.service = Service(self.root, config)
        with self.tasks.db() as c:
            c.execute('CREATE TABLE IF NOT EXISTS chats(id TEXT PRIMARY KEY, title TEXT, session TEXT, messages TEXT, state TEXT, error TEXT, mode TEXT, model TEXT, job TEXT)')
            c.execute('CREATE TABLE IF NOT EXISTS training_inputs(job TEXT, candidate TEXT, project TEXT)')
        self.files = Files(self.root, self.tasks.db)

    def chat(self, identifier):
        with self.tasks.db() as c:
            row = c.execute('SELECT * FROM chats WHERE id=?', (identifier,)).fetchone()
            if not row:
                raise Rejected('Conversation not found')
            value = dict(row)
            value['messages'] = json.loads(value['messages'])
            if value['job']:
                task = self.tasks.get(self.project, value['job'])
                if task['status'] != 'running':
                    result = task['result']
                    if task['status'] == 'completed':
                        value['messages'].append({'role': 'assistant', 'text': result['result'],
                            'provider': value['mode'], 'model': value['model'],
                            'private_memory_attached': False, 'fallback_enabled': False})
                    value['state'] = 'idle' if task['status'] == 'completed' else 'error'
                    value['error'] = result.get('error', '')
                    value['job'] = None
                    c.execute('UPDATE chats SET messages=?,state=?,error=?,job=NULL WHERE id=?',
                              (json.dumps(value['messages']), value['state'], value['error'], identifier))
            return value

    def get(self, path, query):
        if path == 'status':
            return {'ready': True, 'local_ready': True, 'adapter': 'bounded-chat',
                    'detail': 'Development runtime · select an installed local or verified free cloud model',
                    'interface_version': '0.3.0', 'native_device_verified': False}
        if path == 'models':
            mode = query.get('mode', ['local'])[0]
            try:
                return {'online': True, 'models': self.providers.models(mode)}
            except (ValueError, RuntimeError):
                return {'online': False, 'models': [], 'detail': 'Provider unavailable. Check the backend and selected route.'}
        if path == 'runtime':
            return {'project': self.project, 'scheduler': self.service.health(),
                    'jobs': self.tasks.get(self.project),
                    'training_configured': bool(self.config.get('training_command')),
                    'tools': 'disabled', 'cloud_fallback': False}
        if path == 'tasks':
            return self.tasks.get(self.project, query.get('id', [None])[0])
        if path == 'chats':
            with self.tasks.db() as c:
                return [dict(r) for r in c.execute('SELECT id,title,state,mode,model FROM chats ORDER BY rowid DESC')]
        if path.startswith('chats/'):
            return self.chat(path.split('/', 1)[1])
        if path.startswith('evolution/'):
            return self.service.get(path.split('/', 1)[1], query)
        if path in {'artifacts', 'drafts'} or path.startswith('files/'):
            cid = query.get('chat', [''])[0]
            self.chat(cid)
            if path == 'artifacts':
                return self.files.artifacts(cid)
            if path == 'drafts':
                return self.files.drafts(cid)
            return self.files.content(cid, path.rsplit('/', 1)[-1])
        raise Rejected('Unknown endpoint')

    def post(self, path, body):
        if path.startswith('evolution/'):
            operation = path.split('/', 1)[1]
            result = self.service.post(operation, body)
            if operation in {'revoke-candidate', 'edit-candidate'}:
                with self.tasks.db() as c:
                    affected = c.execute('SELECT job FROM training_inputs WHERE candidate=? AND project=?',
                                         (body['id'], self.project)).fetchall()
                    for row in affected:
                        self.tasks.cancel(self.project, row['job'])
                        task = self.tasks.get(self.project, row['job'])
                        value = {**task['result'], 'affected_by_revocation': True,
                                 'model_promoted': False}
                        c.execute('UPDATE jobs SET result=? WHERE id=?', (json.dumps(value), row['job']))
            return result
        if path == 'cancel':
            if set(body) != {'id'}:
                raise Rejected('Task ID required')
            return self.tasks.cancel(self.project, body['id'])
        if path == 'chats':
            mode, model = body.get('mode'), body.get('model')
            if mode not in {'local', 'cloud'} or model not in self.providers.models(mode):
                raise Rejected('Select an available model first')
            import uuid
            identifier = uuid.uuid4().hex
            with self.tasks.db() as c:
                c.execute('INSERT INTO chats VALUES(?,?,?,?,?,?,?,?,?)',
                          (identifier, 'New conversation', identifier, '[]', 'idle', '', mode, model, None))
            return {'id': identifier}
        if path in {'files/upload', 'files/remove'}:
            cid = body.get('chat')
            chat = self.chat(cid)
            if chat['state'] == 'running':
                raise Rejected('Wait for the reply before changing attachments')
            if path == 'files/upload':
                return self.files.upload(cid, body)
            self.files.remove(cid, body.get('id'))
            return {'ok': True}
        if path == 'send':
            chat = self.chat(body.get('id'))
            prompt = body.get('message')
            if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 16000:
                raise Rejected('Enter up to 16000 characters')
            if chat['state'] == 'running':
                raise Rejected('Wait for the current reply')
            if chat['mode'] == 'cloud' and body.get('conversation_consent') is not True:
                raise Rejected('Confirm sharing this conversation with the selected free cloud model')
            attachments, content, images = self.files.prepare(chat['id'], body.get('attachments', []), chat['mode'])
            if images:
                raise Rejected('This runtime supports text attachments; image inference requires a verified vision adapter')
            if attachments and chat['mode'] == 'cloud' and body.get('consent') is not True:
                raise Rejected('Confirm cloud attachment sharing')
            messages = [{'role': m['role'], 'content': m['text']} for m in chat['messages']]
            augmented = prompt
            if content:
                augmented += '\nUntrusted user-selected attachment content:\n' + content
            skill = body.get('skill')
            if skill:
                if chat['mode'] == 'cloud':
                    raise Rejected('Skill guidance is currently local-only')
                bundle = self.service.workbench.reuse(self.service.session(), skill['id'], skill['hash'], prompt[:128], True)
                augmented += '\nUser-selected approved guidance (does not grant tools):\n' + bundle['skill_md']
            messages.append({'role': 'user', 'content': augmented})
            if chat['mode'] == 'cloud' and secret_scan(json.dumps(messages)):
                raise Rejected('Remove detected secrets before cloud transmission')
            task = self.tasks.submit(self.project, 'chat', self.providers.complete,
                (chat['mode'], chat['model'], messages, body.get('conversation_consent') is True))
            chat['messages'].append({'role': 'user', 'text': prompt, 'attachments': attachments,
                                     'guidance': skill})
            with self.tasks.db() as c:
                c.execute('UPDATE chats SET title=?,messages=?,state=?,error=?,job=? WHERE id=?',
                          (prompt[:50] if chat['title'] == 'New conversation' else chat['title'],
                           json.dumps(chat['messages']), 'running', '', task['id'], chat['id']))
            return task
        if path == 'coding':
            if (set(body) != {'specification', 'local_model', 'worker_mode', 'worker_model', 'cloud_consent', 'synthetic', 'confirm'}
                    or body['confirm'] is not True or type(body['synthetic']) is not bool
                    or body['worker_mode'] not in {'local', 'cloud'}):
                raise Rejected('Confirm an advisory coding task')
            return self.tasks.submit(self.project, 'coding', coding,
                (self.providers, self.project, body['specification'], body['local_model'], body['worker_mode'],
                 body['worker_model'], body['cloud_consent'], body['synthetic']))
        if path == 'training':
            if (set(body) != {'ids', 'recipe', 'confirm', 'allow_runner_data_access'}
                    or body['confirm'] is not True or body['allow_runner_data_access'] is not True):
                raise Rejected('Review the dataset and authorize access by the configured training runner')
            command = self.config.get('training_command')
            if (not isinstance(command, list) or not command or any(not isinstance(x, str) for x in command)
                    or not Path(command[0]).is_absolute() or not Path(command[0]).is_file()):
                raise Rejected('Configure an explicit host training runner first')
            recipe = validate_recipe(body['recipe'])
            exported = self.service.dataset.export(self.service.session(), body['ids'], True)
            task = self.tasks.submit(self.project, 'training', train,
                (command, str(self.root / 'training-runs'), exported, recipe,
                 str(self.service.store.path)), seconds=3600)
            with self.tasks.db() as c:
                c.executemany('INSERT INTO training_inputs VALUES(?,?,?)',
                              [(task['id'], cid, self.project) for cid in body['ids']])
            return task
        raise Rejected('Unknown endpoint')

    def close(self):
        self.service.close()
        self.tasks.close()
        os.close(self.lock_fd)


def handler(runtime):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def reply(self, code, data, mime='application/json'):
            raw = json.dumps(data).encode() if mime == 'application/json' else data
            self.send_response(code)
            for key, value in {'Content-Type': mime, 'Content-Length': str(len(raw)),
                'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
                'Referrer-Policy': 'no-referrer', 'Content-Security-Policy':
                "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; object-src 'none'; base-uri 'none'; form-action 'self'"}.items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(raw)

        def allowed(self):
            port = self.server.server_port
            if self.headers.get('Host') not in {f'127.0.0.1:{port}', f'localhost:{port}'}:
                self.reply(403, {'error': 'Loopback access only'})
                return False
            if self.path.startswith('/api/') and not secrets.compare_digest(
                    self.headers.get('Authorization', ''), 'Bearer ' + runtime.token):
                self.reply(401, {'error': 'Pair this device using its private runtime token'})
                return False
            return True

        def do_GET(self):
            if not self.allowed():
                return
            path = urlsplit(self.path).path
            try:
                if path.startswith('/api/'):
                    return self.reply(200, runtime.get(path[5:], parse_qs(urlsplit(self.path).query)))
                assets = {'/': ('index.html', 'text/html; charset=utf-8'),
                          '/app.js': ('app.js', 'text/javascript'),
                          '/evolution.js': ('evolution.js', 'text/javascript'),
                          '/runtime.js': ('runtime.js', 'text/javascript'),
                          '/style.css': ('style.css', 'text/css'),
                          '/evolution.css': ('evolution.css', 'text/css')}
                if path not in assets:
                    return self.reply(404, {'error': 'Not found'})
                name, mime = assets[path]
                return self.reply(200, (Path(__file__).parent / 'web' / name).read_bytes(), mime)
            except (ValueError, RuntimeError, OSError, KeyError, TypeError, sqlite3.Error):
                self.reply(400, {'error': 'Request rejected. Check the selected resource and configuration.'})

        def do_POST(self):
            if not self.allowed():
                return
            origin = self.headers.get('Origin')
            if origin and origin not in {f'http://127.0.0.1:{self.server.server_port}',
                                         f'http://localhost:{self.server.server_port}'}:
                return self.reply(403, {'error': 'Origin rejected'})
            try:
                maximum = ((MAX_FILE + 2) // 3) * 4 + 4096 if self.path == '/api/files/upload' else 65536
                size = int(self.headers.get('Content-Length', '0'))
                if not 1 <= size <= maximum:
                    raise Rejected('Invalid request size')
                self.connection.settimeout(10)
                body = json.loads(self.rfile.read(size))
                if not isinstance(body, dict) or not self.path.startswith('/api/'):
                    raise Rejected('Object request required')
                # Serialize user mutations; worker completion uses independent durable tasks.
                with runtime.service.guard:
                    result = runtime.post(self.path[5:], body)
                self.reply(200, result)
            except (Rejected, Denied) as exc:
                self.reply(400, {'error': str(exc)})
            except (ValueError, RuntimeError, OSError, KeyError, TypeError, sqlite3.Error):
                self.reply(400, {'error': 'Request rejected. Check scope, consent and configuration.'})
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, required=True, help='New private runtime directory; never point at existing Pocket data')
    parser.add_argument('--config', type=Path)
    parser.add_argument('--port', type=int, default=18877)
    args = parser.parse_args()
    if not 0 <= args.port <= 65535 or args.port in {8766, 8877}:
        parser.error('Choose a development port other than 8766 or 8877')
    # Require our own marker; never migrate an installed Pocket database by accident.
    marker = args.data / 'hermes-runtime-v1'
    if any(p.is_symlink() for p in (marker, *marker.parents)):
        parser.error('Runtime and marker paths must not contain symlinks')
    if args.data.exists() and any(args.data.iterdir()) and not marker.is_file():
        parser.error('Use a new empty runtime directory')
    args.data.mkdir(parents=True, exist_ok=True, mode=0o700)
    marker.touch(mode=0o600)
    os.umask(0o077)
    config = json.loads(args.config.read_text()) if args.config else {}
    runtime = Runtime(args.data, config)
    server = ThreadingHTTPServer(('127.0.0.1', args.port), handler(runtime))
    print(f'Hermes development runtime listening on loopback port {server.server_port}', flush=True)
    print('Pair using the private pairing-token file in the selected runtime directory.', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        runtime.close()


if __name__ == '__main__':
    main()
