"""Loopback-only authenticated API and Android-compatible dashboard."""
import argparse
import fcntl
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import signal
import sys
import threading
from urllib.parse import urlsplit

from .contracts import MODEL_ROLES, PolicyError, ROLES, strict_json
from .engine import Engine
from .memory import MemoryAdapter
from .models import Router
from .storage import Store, no_alias, owned_file, prepare

ASSETS = Path(__file__).parent / 'web'


def default_config():
    route = {'provider': 'ollama', 'model': 'qwen2.5-coder:7b',
             'endpoint': 'http://127.0.0.1:11434', 'key_env': None}
    return {'routes': {role: dict(route) for role in MODEL_ROLES}, 'seconds': 60, 'memory_sources': {}}


def load_config(path):
    if path is None:
        return default_config()
    path = no_alias(path)
    if path.stat().st_size > 32768:
        raise PolicyError('Configuration too large')
    config = strict_json(path.read_bytes())
    if not isinstance(config, dict) or set(config) != {'routes', 'seconds', 'memory_sources'}:
        raise PolicyError('Invalid platform configuration')
    return config


def handler(engine, token):
    class Handler(BaseHTTPRequestHandler):
        server_version = 'HermesEvolution'

        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def log_message(self, *args):
            pass  # Request URLs, headers and task data never enter access logs.

        def reply(self, status, value, mime='application/json'):
            raw = value if isinstance(value, bytes) else json.dumps(value).encode()
            self.send_response(status)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            self.end_headers()
            self.wfile.write(raw)

        def boundary(self, auth=True):
            port = self.server.server_port
            hosts = {f'127.0.0.1:{port}', f'localhost:{port}'}
            if self.headers.get('Host') not in hosts:
                self.reply(403, {'error': 'Host rejected'})
                return False
            origin = self.headers.get('Origin')
            if origin and origin not in {'http://' + h for h in hosts}:
                self.reply(403, {'error': 'Origin rejected'})
                return False
            if auth and not secrets.compare_digest(self.headers.get('Authorization', '').encode(), ('Bearer ' + token).encode()):
                self.reply(401, {'error': 'Pairing required'})
                return False
            return True

        def do_GET(self):
            assets = {'/': ('index.html', 'text/html; charset=utf-8'),
                      '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
                      '/style.css': ('style.css', 'text/css; charset=utf-8')}
            if not self.boundary(self.path not in assets):
                return
            if self.path in assets:
                name, mime = assets[self.path]
                return self.reply(200, (ASSETS / name).read_bytes(), mime)
            if self.path == '/api/state':
                routes = {role: {'provider': route['provider'], 'model': route['model']}
                          for role, route in engine.router.routes.items()}
                return self.reply(200, {'tasks': engine.store.listing(), 'roles': ROLES,
                                       'routes': routes, 'memory_sources': list(engine.memory.sources),
                                       'scheduler_alive': bool(engine.thread and engine.thread.is_alive())})
            if self.path.startswith('/api/tasks/'):
                identifier = self.path.removeprefix('/api/tasks/')
                try:
                    return self.reply(200, engine.store.get(identifier))
                except KeyError:
                    return self.reply(404, {'error': 'Task not found'})
            return self.reply(404, {'error': 'Unknown endpoint'})

        def do_POST(self):
            if not self.boundary():
                return
            try:
                if self.headers.get('Transfer-Encoding') or self.headers.get_content_type() != 'application/json':
                    raise PolicyError('JSON body required')
                sizes = self.headers.get_all('Content-Length', [])
                if len(sizes) != 1 or not sizes[0].isdigit() or not 0 < int(sizes[0]) <= 32768:
                    raise PolicyError('Invalid request size')
                raw = self.rfile.read(int(sizes[0]))
                if len(raw) != int(sizes[0]):
                    raise PolicyError('Incomplete request')
                body = strict_json(raw)
                if self.path == '/api/tasks':
                    return self.reply(201, engine.create(body))
                if self.path.startswith('/api/tasks/') and self.path.endswith('/decision'):
                    identifier = self.path[len('/api/tasks/'):-len('/decision')]
                    if not isinstance(body, dict) or set(body) != {'revision', 'action', 'result_hash'}:
                        raise PolicyError('Exact decision fields required')
                    return self.reply(200, engine.store.decision(identifier, **body))
                return self.reply(404, {'error': 'Unknown endpoint'})
            except KeyError:
                return self.reply(404, {'error': 'Task not found'})
            except (ValueError, TypeError):
                return self.reply(409, {'error': 'Request rejected; verify fields, permissions and current revision'})
            except Exception:
                return self.reply(503, {'error': 'Operation unavailable'})

    return Handler


def main():
    if sys.version_info < (3, 11):
        raise SystemExit('Hermes platform requires Python 3.11 or newer')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', required=True, type=Path, help='New isolated owner-only platform directory')
    parser.add_argument('--config', type=Path, help='Explicit platform config; no Hermes config discovery')
    parser.add_argument('--port', type=int, default=18878)
    args = parser.parse_args()
    if args.port in {8766, 8877} or (args.port != 0 and not 1024 <= args.port <= 65535):
        parser.error('Choose a separate non-production port or 0')
    os.umask(0o077)
    root = prepare(args.data)
    lock_path = root / 'server.lock'
    no_alias(lock_path)
    lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    owned_file(lock_path)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(lock_fd)
        parser.error('This platform directory already has a running server')
    config = load_config(args.config)
    engine = Engine(Store(root), Router(config['routes'], config['seconds']), MemoryAdapter(config['memory_sources']))
    token = (root / 'pairing-token').read_text()
    if len(token) < 32 or not token.isascii() or any(c.isspace() for c in token):
        raise PolicyError('Invalid platform pairing token')
    with ThreadingHTTPServer(('127.0.0.1', args.port), handler(engine, token)) as server:
        server.daemon_threads = True
        engine.start()
        def stop(*unused):
            threading.Thread(target=server.shutdown, daemon=True).start()
        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        print(json.dumps({'status': 'ready', 'port': server.server_port, 'mode': 'local-platform'}), flush=True)
        try:
            server.serve_forever()
        finally:
            engine.close()
            os.close(lock_fd)


if __name__ == '__main__':
    main()
