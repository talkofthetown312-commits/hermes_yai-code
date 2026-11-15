"""Back up a stopped development runtime; never copies registered private sources."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import shutil


def backup(source, destination):
    source, destination = Path(source).absolute(), Path(destination).absolute()
    if (destination.exists() or destination.is_relative_to(source)
            or any(p.is_symlink() for p in (source, *source.parents, *destination.parents))):
        raise ValueError('Use a new separate private backup directory without symlinks')
    fd = os.open(source / 'runtime.lock', os.O_RDWR | os.O_NOFOLLOW)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        destination.mkdir(mode=0o700, parents=True)
        files = []
        for relative in ('runtime.sqlite3', 'evolution/evolution.sqlite3', 'schedule.json', 'hermes-runtime-v1'):
            path = source / relative
            if not path.exists():
                continue
            if path.is_symlink() or path.parent.is_symlink():
                raise ValueError('Symlink runtime file refused')
            target = destination / relative
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            if relative.endswith('.sqlite3'):
                with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as old:
                    with sqlite3.connect(target) as new:
                        old.backup(new)
                        if new.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                            raise ValueError('Backup integrity check failed')
            else:
                target.write_bytes(path.read_bytes())
            target.chmod(0o600)
            files.append({'file': relative, 'sha256': hashlib.sha256(target.read_bytes()).hexdigest()})
        for directory in ('workspaces', 'training-runs'):
            for path in sorted((source / directory).rglob('*')):
                if path.is_symlink():
                    raise ValueError('Symlink runtime artifact refused')
                target = destination / path.relative_to(source)
                if path.is_dir():
                    target.mkdir(mode=0o700, parents=True, exist_ok=True)
                elif path.is_file():
                    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                    shutil.copyfile(path, target)
                    target.chmod(0o600)
                    h = hashlib.sha256()
                    with target.open('rb') as stream:
                        for chunk in iter(lambda: stream.read(1048576), b''):
                            h.update(chunk)
                    files.append({'file': str(path.relative_to(source)), 'sha256': h.hexdigest()})
                else:
                    raise ValueError('Nonregular runtime artifact refused')
        manifest = destination / 'backup-manifest.json'
        manifest.write_text(json.dumps({'files': files, 'source_stopped': True,
            'excludes': ['pairing token', 'registered source files'],
            'restore': 'Use a new runtime directory; never overwrite a live database.'}, indent=2))
        manifest.chmod(0o600)
        return files
    except BlockingIOError:
        raise ValueError('Stop this development runtime before backing it up') from None
    finally:
        os.close(fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    backup(args.data, args.output)
    print('Stopped runtime workflow backup completed; registered private sources and attachment files were not copied.')


if __name__ == '__main__':
    main()
