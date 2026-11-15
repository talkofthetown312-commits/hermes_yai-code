"""Durable tasks, bounded workers, and backend-only inference transports."""
from contextlib import contextmanager
import json
import multiprocessing
import hashlib
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import sqlite3
import threading
import time
import urllib.error
import urllib.request
import uuid

from evolution_addons.free_router import select_free_models


class Rejected(ValueError):
    pass


def json_request(url, body=None, key=None, timeout=15, limit=1048576):
    headers = {'Content-Type': 'application/json'}
    if key:
        headers['Authorization'] = 'Bearer ' + key
    req = urllib.request.Request(url, headers=headers,
                                 data=None if body is None else json.dumps(body).encode())
    # Ignore inherited proxies; never forward backend credentials to a proxy.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                         NoRedirect())
    try:
        with opener.open(req, timeout=timeout) as response:
            raw = response.read(limit + 1)
            if len(raw) > limit:
                raise Rejected('Provider output exceeds limit')
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        raise Rejected('Provider HTTP error ' + str(exc.code) + '; no fallback attempted') from None
    except (OSError, ValueError) as exc:
        if isinstance(exc, Rejected):
            raise
        raise Rejected('Provider unavailable or returned invalid data') from None


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise Rejected('Provider redirect refused')


class Providers:
    def __init__(self, local='http://127.0.0.1:11434', gguf=None):
        if local != 'http://127.0.0.1:11434':
            raise Rejected('Only the installed loopback Ollama endpoint is supported')
        self.local = local
        self.catalog = []
        self.observed = 0
        self.lock = threading.Lock()
        self.gguf = gguf
        if gguf is not None and (not isinstance(gguf, dict) or set(gguf) != {'path', 'sha256', 'executable'}
                or any(not isinstance(v, str) for v in gguf.values())
                or len(gguf['sha256']) != 64 or any(c not in '0123456789abcdef' for c in gguf['sha256'])
                or any(not Path(gguf[k]).is_absolute() for k in ('path', 'executable'))):
            raise Rejected('GGUF configuration requires absolute model/executable paths and exact SHA-256')

    def __getstate__(self):
        return {k: v for k, v in self.__dict__.items() if k != 'lock'}

    def __setstate__(self, state):
        self.__dict__.update(state)
        self.lock = threading.Lock()

    def models(self, mode):
        if mode == 'local':
            try:
                response = json_request(self.local + '/api/tags')
                models = [m['name'] for m in response.get('models', [])
                          if isinstance(m, dict) and isinstance(m.get('name'), str)][:200]
            except Rejected:
                if self.gguf is None:
                    raise
                models = []
            if self.gguf is not None:
                models.append('gguf:' + self.gguf['sha256'][:12])
            return models
        if mode != 'cloud':
            raise Rejected('Unknown provider')
        if not os.environ.get('OPENROUTER_API_KEY'):
            raise Rejected('Set OPENROUTER_API_KEY privately in the backend environment')
        response = json_request('https://openrouter.ai/api/v1/models',
                                key=os.environ['OPENROUTER_API_KEY'])
        catalog = response.get('data')
        models = select_free_models(catalog, require_tools=False)
        with self.lock:
            self.catalog, self.observed = catalog, time.time()
        return models

    def complete(self, mode, model, messages, cloud_consent=False):
        if not isinstance(model, str) or not model or len(model) > 256:
            raise Rejected('Select a model first')
        if (not isinstance(messages, list) or not messages or len(messages) > 100
                or len(json.dumps(messages).encode()) > 65536
                or any(set(m) != {'role', 'content'} or m['role'] not in {'user', 'assistant'}
                       or not isinstance(m['content'], str) for m in messages)):
            raise Rejected('Conversation exceeds the supported context budget; start a new chat')
        if mode == 'local':
            if self.gguf and model == 'gguf:' + self.gguf['sha256'][:12]:
                return self._gguf(messages)
            if model not in self.models('local'):
                raise Rejected('Selected local model is not installed')
            response = json_request(self.local + '/api/chat', {
                'model': model, 'messages': messages, 'stream': False,
                'options': {'num_ctx': 2048, 'num_predict': 512}}, timeout=85)
            result = response.get('message', {}).get('content')
        elif mode == 'cloud':
            if cloud_consent is not True:
                raise Rejected('Explicit cloud conversation consent required')
            # Always refresh in this worker: no client-provided catalog or stale prices.
            if model not in self.models('cloud'):
                raise Rejected('Selected model is no longer verified free')
            response = json_request('https://openrouter.ai/api/v1/chat/completions', {
                'model': model, 'messages': messages, 'max_tokens': 512,
                'provider': {'allow_fallbacks': False, 'max_price': {
                    'prompt': 0, 'completion': 0, 'request': 0, 'image': 0}}},
                key=os.environ['OPENROUTER_API_KEY'], timeout=85)
            try:
                result = response['choices'][0]['message']['content']
            except (KeyError, IndexError, TypeError):
                raise Rejected('Provider returned no answer') from None
        else:
            raise Rejected('Unknown provider')
        if not isinstance(result, str) or not result.strip() or len(result.encode()) > 32768:
            raise Rejected('Provider returned empty or oversized text')
        return result

    def _gguf(self, messages):
        """Explicit, offline, short CPU inference against one approved GGUF."""
        from hermes_runtime.device import inspect
        config = self.gguf
        model, executable = Path(config['path']), Path(config['executable'])
        for path in (model, executable):
            if not path.is_file() or any(p.is_symlink() for p in (path, *path.parents)):
                raise Rejected('Selected GGUF or llama-cli is unavailable or symlinked')
        def available():
            return inspect()['memory'].get('MemAvailable_kib', 0)
        if available() < 2560 * 1024:
            raise Rejected('GGUF preflight needs at least 2560 MiB available memory')
        h = hashlib.sha256()
        with model.open('rb') as stream:
            if stream.read(4) != b'GGUF':
                raise Rejected('Selected file is not GGUF')
            stream.seek(0)
            for chunk in iter(lambda: stream.read(1048576), b''):
                h.update(chunk)
        if h.hexdigest() != config['sha256']:
            raise Rejected('Selected GGUF hash changed; model was not loaded')
        prompt = 'Continue this user/assistant conversation. Use no tools.\n' + json.dumps(messages, ensure_ascii=False)
        if len(prompt.encode()) > 1800:
            raise Rejected('Short GGUF mode context is full; start a new conversation')
        env = {'PATH': os.environ.get('PATH', ''), 'HOME': str(model.parent), 'NO_COLOR': '1'}
        args = [str(executable), '--offline', '--single-turn', '--no-display-prompt', '--no-warmup',
                '-m', str(model), '-p', prompt, '-n', '64', '-c', '512', '-t', '2', '-b', '64', '-ub', '32']
        with tempfile.TemporaryFile() as output:
            process = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=output,
                                       stderr=subprocess.DEVNULL, env=env)
            started = time.monotonic()
            try:
                while process.poll() is None:
                    rss = Path(f'/proc/{process.pid}/status')
                    usage = 0
                    if rss.exists():
                        for line in rss.read_text().splitlines():
                            if line.startswith('VmRSS:'):
                                usage = int(line.split()[1])
                    if (time.monotonic() - started > 80 or available() < 768 * 1024
                            or usage > 1600 * 1024 or output.tell() > 65536):
                        raise Rejected('GGUF resource budget exceeded; inference stopped')
                    time.sleep(.1)
                if process.returncode:
                    raise Rejected('llama-cli failed; verify this installed version before retrying')
                output.seek(0)
                result = output.read(32769).decode('utf-8', errors='replace').strip()
                if not result or len(result.encode()) > 32768:
                    raise Rejected('GGUF returned empty or oversized output')
                return result
            finally:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=5)


def _child(pipe, callback, args, cpu_budget):
    os.setsid()
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_budget, cpu_budget))
        value = callback(*args)
        raw = json.dumps({'result': value}, allow_nan=False).encode()
        if len(raw) > 196608:
            raise Rejected('Task output exceeds limit')
        pipe.send_bytes(raw)
    except BaseException as exc:
        # Never serialize raw provider/subprocess exceptions or credentials.
        message = str(exc) if isinstance(exc, Rejected) else 'Task failed; check host configuration'
        pipe.send_bytes(json.dumps({'error': message[:400]}).encode())
    finally:
        pipe.close()


class Tasks:
    """Versioned private task DB; abrupt restarts never report in-flight success."""
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.path = self.root / 'runtime.sqlite3'
        if self.path.is_symlink():
            raise Rejected('Symlink database refused')
        self.lock = threading.Lock()
        self.active = {}
        with self.db() as c:
            c.execute('CREATE TABLE IF NOT EXISTS runtime_meta(version INTEGER)')
            c.execute('INSERT INTO runtime_meta SELECT 1 WHERE NOT EXISTS(SELECT 1 FROM runtime_meta)')
            if c.execute('SELECT version FROM runtime_meta').fetchone()[0] != 1:
                raise Rejected('Unsupported runtime schema; restore with matching code')
            c.execute('CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, project TEXT, kind TEXT, status TEXT, result TEXT, created REAL, ended REAL)')
            c.execute("UPDATE jobs SET status='interrupted', result=?, ended=? WHERE status='running'",
                      (json.dumps({'error': 'Runtime stopped during this task'}), time.time()))
        self.path.chmod(0o600)

    @contextmanager
    def db(self):
        c = sqlite3.connect(self.path, timeout=10)
        c.row_factory = sqlite3.Row
        try:
            with c:
                yield c
        finally:
            c.close()

    def get(self, project, identifier=None):
        with self.db() as c:
            rows = c.execute('SELECT * FROM jobs WHERE project=? ORDER BY created DESC LIMIT 100',
                             (project,)).fetchall() if identifier is None else c.execute(
                                 'SELECT * FROM jobs WHERE project=? AND id=?', (project, identifier)).fetchall()
        values = [{**dict(r), 'result': json.loads(r['result'])} for r in rows]
        if identifier is not None:
            if not values:
                raise Rejected('Task unavailable')
            return values[0]
        return values

    def submit(self, project, kind, callback, args=(), seconds=90):
        with self.lock:
            if self.active:
                raise Rejected('Wait for or cancel the current task')
            identifier = uuid.uuid4().hex
            cancel = threading.Event()
            self.active[identifier] = cancel
            with self.db() as c:
                c.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?)',
                          (identifier, project, kind, 'running', '{}', time.time(), None))
        threading.Thread(target=self._run, args=(identifier, callback, args, seconds, cancel), daemon=True).start()
        return {'id': identifier, 'status': 'running'}

    def _run(self, identifier, callback, args, seconds, cancel):
        ctx = multiprocessing.get_context('spawn')
        reader, writer = ctx.Pipe(duplex=False)
        cpu_budget = 3500 if seconds > 90 else 60
        process = ctx.Process(target=_child, args=(writer, callback, args, cpu_budget))
        status, result = 'failed', {'error': 'Task worker failed'}
        started = time.monotonic()
        try:
            process.start()
            writer.close()
            while True:
                if cancel.is_set():
                    status, result = 'cancelled', {'error': 'Cancelled by owner'}
                    break
                if time.monotonic() - started >= seconds:
                    status, result = 'timed_out', {'error': 'Task deadline exceeded'}
                    break
                if reader.poll(.05):
                    result = json.loads(reader.recv_bytes(196608))
                    status = 'failed' if 'error' in result else 'completed'
                    break
                if not process.is_alive():
                    break
        except (OSError, ValueError, EOFError):
            pass
        finally:
            if process.pid:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    if process.is_alive():
                        process.kill()
                process.join(timeout=5)
            reader.close()
            writer.close()
            with self.db() as c:
                old = json.loads(c.execute('SELECT result FROM jobs WHERE id=?', (identifier,)).fetchone()[0])
                if old.get('affected_by_revocation'):
                    result.update(affected_by_revocation=True, model_promoted=False)
                    status = 'cancelled'
                c.execute('UPDATE jobs SET status=?,result=?,ended=? WHERE id=?',
                          (status, json.dumps(result), time.time(), identifier))
            with self.lock:
                self.active.pop(identifier, None)

    def cancel(self, project, identifier):
        value = self.get(project, identifier)
        with self.lock:
            if identifier in self.active:
                self.active[identifier].set()
        return value

    def close(self):
        with self.lock:
            events = list(self.active.values())
        for event in events:
            event.set()
        deadline = time.monotonic() + 8
        while self.active and time.monotonic() < deadline:
            time.sleep(.05)
