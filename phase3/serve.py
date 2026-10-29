#!/usr/bin/env python3
"""Explicit synthetic-only Phase 3 staging. Never runs the installed Pocket bridge."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]
ASSETS = Path(__file__).resolve().parent / 'web'
MARKER = 'hermes-yai-phase3-synthetic-v1'


def prepare(directory):
    directory = Path(os.path.abspath(directory))
    if (not directory.name.startswith('hermes-yai-phase3-') or directory == ROOT
            or directory.is_relative_to(ROOT) or ROOT.is_relative_to(directory)):
        raise ValueError('Use a dedicated private hermes-yai-phase3-* directory outside source')
    if any(path.is_symlink() for path in [directory, *directory.parents]):
        raise ValueError('Symlink runtime paths are not supported')
    owner = directory / 'phase3-owner.json'
    if directory.exists():
        if not directory.is_dir() or owner.is_symlink() or not owner.is_file():
            raise ValueError('Existing unowned directory refused')
        if json.loads(owner.read_text()) != {'format': MARKER, 'synthetic_only': True}:
            raise ValueError('Runtime ownership mismatch')
        for path in directory.rglob('*'):
            if (path.is_symlink() or not (path.is_dir() or path.is_file())
                    or (path.is_file() and path.stat().st_nlink != 1)):
                raise ValueError('Aliased or special runtime contents refused')
    else:
        directory.mkdir(mode=0o700, parents=True)
        owner.write_text(json.dumps({'format': MARKER, 'synthetic_only': True}))
        owner.chmod(0o600)
    directory.chmod(0o700)
    if directory.stat().st_mode & 0o077:
        raise ValueError('Private filesystem permissions required; shared storage refused')
    lock = (directory / 'server.lock').open('w')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        lock.close()
        raise
    try:
        stage = _populate(directory)
    except BaseException:
        lock.close()
        raise
    return directory, stage, lock


def _populate(directory):
    stage = directory / 'app'
    pocket = stage / 'pocket'
    (pocket / 'web').mkdir(parents=True, mode=0o700, exist_ok=True)
    baseline = ROOT / 'phase2'
    for source in (baseline / 'pocket').glob('*.py'):
        if source.is_symlink():
            raise ValueError('Source symlink refused')
        shutil.copyfile(source, pocket / source.name)
    for source in (baseline / 'pocket/web').iterdir():
        if source.is_file() and not source.is_symlink():
            shutil.copyfile(source, pocket / 'web' / source.name)
    from pairing import harden_pairing_javascript
    application = pocket / 'web/app.js'
    application.write_text(harden_pairing_javascript(application.read_text()))
    for name in ('schema-fixtures.json', 'synthetic-reference.md'):
        shutil.copyfile(baseline / name, stage / name)
    reference = stage / 'synthetic-reference.md'
    (stage / 'skill-catalog.json').write_text(json.dumps([{
        'id': 'synthetic-guidance-reference', 'path': str(reference),
        'sha256': hashlib.sha256(reference.read_bytes()).hexdigest()}]))
    for name in ('home/hermes', 'tmp'):
        (directory / name).mkdir(parents=True, mode=0o700, exist_ok=True)
    return stage


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir', type=Path,
                        default=Path.home() / 'hermes-yai-phase3-staging')
    parser.add_argument('--port', type=int, default=8893)
    options = parser.parse_args()
    if options.port in (8766, 8877) or (options.port != 0 and not 1024 <= options.port <= 65535):
        parser.error('Use a separate unprivileged port; existing Pocket/preview ports refused')
    os.umask(0o077)
    directory, stage, lock = prepare(options.state_dir)
    path = os.environ.get('PATH', '')
    os.environ.clear()
    os.environ.update(PATH=path, HOME=str(directory / 'home'),
                      HERMES_HOME=str(directory / 'home/hermes'),
                      TMPDIR=str(directory / 'tmp'),
                      HERMES_POCKET_DATA=str(stage / 'data'),
                      HERMES_POCKET_PORT=str(options.port), PYTHONDONTWRITEBYTECODE='1')
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(stage / 'pocket'))
    import bridge
    from integration import IntegrationService
    bridge.EVOLUTION = IntegrationService(bridge.DATA, stage)
    bridge.CAPABILITY = {'ready': False, 'local_ready': False,
                         'adapter': 'phone-staging-no-agent',
                         'detail': 'Phase 3 synthetic staging. Models, providers and training disabled.'}
    bridge.local_models = lambda: {'online': False, 'models': [], 'detail': 'Disabled in staging.'}

    class Handler(bridge.Handler):
        def setup(self):
            super().setup()
            self.connection.settimeout(15)

        def do_GET(self):
            if not self.allowed():
                return
            path = urlsplit(self.path).path
            if path == '/':
                page = (stage / 'pocket/web/index.html').read_text()
                page = page.replace('</head>', '<link rel="stylesheet" href="/integration.css"></head>')
                page = page.replace('</body>', '<script src="/integration.js"></script></body>')
                page = page.replace('http://127.0.0.1:8877/', 'this isolated Phase 3 address')
                return self.reply(200, page.encode(), 'text/html; charset=utf-8')
            if path in ('/integration.js', '/integration.css'):
                mime = 'text/javascript' if path.endswith('.js') else 'text/css'
                return self.reply(200, (ASSETS / path[1:]).read_bytes(), mime)
            if path == '/api/integration/dashboard':
                try:
                    return self.reply(200, bridge.EVOLUTION.dashboard())
                except (ValueError, OSError, bridge.sqlite3.Error):
                    return self.reply(503, {'error': 'Dashboard unavailable; retry without changing state'})
            return super().do_GET()

        def do_POST(self):
            if not self.allowed():
                return
            origin = self.headers.get('Origin')
            if origin and origin not in (f'http://127.0.0.1:{bridge.PORT}', f'http://localhost:{bridge.PORT}'):
                return self.reply(403, {'error': 'Origin rejected'})
            if self.path == '/api/integration/preferences':
                try:
                    size = int(self.headers.get('Content-Length', '0'))
                    if not 1 <= size <= 1024:
                        raise ValueError('Size rejected')
                    body = json.loads(self.rfile.read(size))
                    return self.reply(200, bridge.EVOLUTION.set_preferences(body))
                except (ValueError, TypeError, KeyError, bridge.sqlite3.Error):
                    return self.reply(409, {'error': 'Navigation revision rejected; refresh'})
            if self.path == '/api/send':
                return self.reply(409, {'error': 'Agent execution is disabled in Phase 3 staging'})
            if self.path.startswith('/api/evolution/') or self.path in (
                    '/api/chats', '/api/files/upload', '/api/files/remove'):
                return super().do_POST()
            return self.reply(403, {'error': 'Only isolated staging operations allowed'})

    with bridge.ThreadingHTTPServer(('127.0.0.1', options.port), Handler) as server:
        bridge.PORT = server.server_port
        (directory / 'server.json').write_text(json.dumps({
            'pid': os.getpid(), 'port': bridge.PORT, 'synthetic_only': True,
            'source': str(ROOT), 'format': MARKER}))
        print(f'Phase 3 staging ready: http://127.0.0.1:{bridge.PORT}/', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            lock.close()


if __name__ == '__main__':
    main()
