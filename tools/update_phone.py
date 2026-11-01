#!/usr/bin/env python3
"""Install the reviewed timeout-fix source ZIP into an existing phone workspace.

Verifies the complete runtime before importing it. Preserves data, pairing and
configuration; retains the previous source release for rollback. Never connects
to a provider or reads Hermes production files.
"""
import argparse
import fcntl
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

EXPECTED = '7dfd4a0921c8884d3aa53f03b3707cd6ea1615f86a1f3920a2ea7f95d164d739'
FILES = {'hermes_platform/' + name for name in (
    '__init__.py', 'contracts.py', 'storage.py', 'memory.py', 'models.py',
    'engine.py', 'server.py', 'package.py')}
FILES.update('hermes_platform/web/' + name for name in ('index.html', 'app.js', 'style.css'))
FILES.update(('evolution_addons/hybrid.py', 'evolution_addons/free_router.py'))


def verified_files(archive_path):
    if archive_path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError('Source ZIP too large')
    files = {}
    with zipfile.ZipFile(archive_path) as archive:
        for member in archive.infolist():
            name = member.filename.partition('/')[2]
            if name not in FILES:
                continue
            if name in files or member.file_size > 262144:
                raise ValueError('Invalid or duplicate runtime member')
            files[name] = archive.read(member)
    digest = hashlib.sha256()
    for name in sorted(files):
        digest.update(name.encode() + b'\0' + files[name] + b'\0')
    if set(files) != FILES or digest.hexdigest() != EXPECTED:
        raise ValueError('Source verification failed; no update performed')
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source_zip', type=Path)
    parser.add_argument('--root', type=Path, default=Path.home().resolve() / 'hermes-evolution-platform')
    parser.add_argument('--start', action='store_true', help='Start only this platform in the foreground after updating')
    args = parser.parse_args()
    if sys.version_info < (3, 11):
        parser.error('Python 3.11 or newer is required')
    files = verified_files(args.source_zip)
    os.umask(0o077)
    with tempfile.TemporaryDirectory(prefix='hermes-update-') as temporary:
        source = Path(temporary).resolve()
        for name, raw in files.items():
            target = source / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        sys.path.insert(0, str(source))
        from hermes_platform.package import build, install
        from hermes_platform.storage import no_alias, owned_file
        root = no_alias(args.root)
        marker = root / 'release-marker'
        owned_file(marker)
        if marker.read_text() != 'hermes-platform-releases-v1':
            parser.error('Existing isolated platform installation required')
        owned_file(root / 'android-local.json')
        lock = root / 'data/server.lock'
        owned_file(lock)
        fd = os.open(lock, os.O_RDWR | os.O_NOFOLLOW)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                parser.error('Platform still running. Stop only its port-18878 foreground session with Ctrl-C, then retry.')
            # Smoke imports before switching the managed release pointer.
            subprocess.run([sys.executable, '-B', '-c', 'import hermes_platform.server'], cwd=source, check=True)
            package = source / 'platform.tar.gz'
            install(package, build(package), root)
        finally:
            os.close(fd)
    print('Update verified and installed. Task history, pairing token and configuration preserved.', flush=True)
    print('Previous source release retained for rollback.', flush=True)
    if args.start:
        os.chdir((root / 'current').resolve())
        os.execv(sys.executable, [sys.executable, '-B', '-m', 'hermes_platform.server',
                 '--data', str(root / 'data'), '--config', str(root / 'android-local.json'), '--port', '18878'])


if __name__ == '__main__':
    main()
