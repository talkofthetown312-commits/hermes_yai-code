"""Build verified source packages and manage isolated Termux release pointers.

No process start/stop, phone connection or production installation is performed.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import tarfile
import tempfile

from .contracts import PolicyError, strict_json
from .storage import no_alias, owned_file, private_file

SOURCE = Path(__file__).resolve().parents[1]
RUNTIME = ['__init__.py', 'contracts.py', 'storage.py', 'memory.py', 'models.py', 'engine.py', 'server.py', 'package.py']
FILES = (['hermes_platform/' + name for name in RUNTIME]
         + ['hermes_platform/web/' + name for name in ('index.html', 'app.js', 'style.css')]
         + ['evolution_addons/hybrid.py', 'evolution_addons/free_router.py'])


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def build(destination):
    destination = no_alias(destination)
    files = {name: (SOURCE / name).read_bytes() for name in FILES}
    files['manifest.json'] = json.dumps({name: digest(raw) for name, raw in files.items()}, sort_keys=True).encode()
    # Exclusive output creation avoids overwriting an existing artifact.
    with destination.open('xb') as handle, tarfile.open(fileobj=handle, mode='w:gz') as archive:
        for name, raw in sorted(files.items()):
            info = tarfile.TarInfo(name); info.size = len(raw); info.mode = 0o600; info.mtime = 0
            archive.addfile(info, io.BytesIO(raw))
    return digest(destination.read_bytes())


def package_contents(archive_path, expected):
    archive_path = no_alias(archive_path)
    if archive_path.stat().st_size > 4 * 1024 * 1024:
        raise PolicyError('Package too large')
    raw = archive_path.read_bytes()
    if digest(raw) != expected:
        raise PolicyError('Package checksum mismatch')
    files = {}
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as archive:
        total = 0
        for member in archive:
            if not member.isfile() or member.name not in set(FILES) | {'manifest.json'} or member.name in files:
                raise PolicyError('Unexpected package member')
            total += member.size
            if total > 2 * 1024 * 1024:
                raise PolicyError('Expanded package too large')
            files[member.name] = archive.extractfile(member).read()
    if set(files) != set(FILES) | {'manifest.json'}:
        raise PolicyError('Incomplete package')
    manifest = strict_json(files.pop('manifest.json'))
    if manifest != {name: digest(raw) for name, raw in files.items()}:
        raise PolicyError('Package manifest mismatch')
    return files


def release_root(root):
    root = no_alias(root)
    if any(p.name in {'.hermes', '.jcode'} for p in (root, *root.parents)):
        raise PolicyError('Use a separate release directory')
    if root.exists() and any(root.iterdir()):
        marker = root / 'release-marker'; owned_file(marker)
        if marker.read_text() != 'hermes-platform-releases-v1':
            raise PolicyError('Foreign release directory')
    else:
        root.mkdir(parents=True, mode=0o700, exist_ok=True)
        private_file(root / 'release-marker', 'hermes-platform-releases-v1')
    if root.stat().st_uid != os.getuid() or root.stat().st_mode & 0o077:
        raise PolicyError('Release root must be owner-only')
    no_alias(root / 'releases').mkdir(mode=0o700, exist_ok=True)
    return root


def pointer(root, name):
    path = root / name
    if not path.exists() and not path.is_symlink():
        return None
    if not path.is_symlink():
        raise PolicyError('Release pointer must be a managed symlink')
    target = os.readlink(path)
    parts = PurePosixPath(target).parts
    if len(parts) != 2 or parts[0] != 'releases' or len(parts[1]) != 64 or any(c not in '0123456789abcdef' for c in parts[1]):
        raise PolicyError('Invalid release pointer')
    if not no_alias(root / target).is_dir():
        raise PolicyError('Release pointer target missing')
    return target


def set_pointer(root, name, target):
    temporary = root / (name + '-next')
    # Refuse unexpected preexisting state instead of deleting arbitrary paths.
    temporary.symlink_to(target)
    os.replace(temporary, root / name)


def install(archive, checksum, root):
    files = package_contents(archive, checksum)
    root = release_root(root)
    current = pointer(root, 'current'); pointer(root, 'previous')
    target = 'releases/' + checksum
    destination = no_alias(root / target)
    if destination.exists():
        no_alias(destination)
        if any(no_alias(destination / name).read_bytes() != raw for name, raw in files.items()):
            raise PolicyError('Existing release content changed')
    else:
        scratch = Path(tempfile.mkdtemp(prefix='install-', dir=root))
        try:
            for name, raw in files.items():
                path = scratch / name; path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw); path.chmod(0o600)
            scratch.rename(destination)
        finally:
            if scratch.exists():
                shutil.rmtree(scratch)
    if current != target:
        if current:
            set_pointer(root, 'previous', current)
        set_pointer(root, 'current', target)
    return target


def rollback(root):
    root = release_root(root)
    current, previous = pointer(root, 'current'), pointer(root, 'previous')
    if not previous or not current:
        raise PolicyError('No previous release available')
    set_pointer(root, 'current', previous)
    set_pointer(root, 'previous', current)
    return previous


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='action', required=True)
    create = commands.add_parser('build'); create.add_argument('--output', type=Path, required=True)
    deploy = commands.add_parser('install'); deploy.add_argument('--archive', type=Path, required=True)
    deploy.add_argument('--sha256', required=True); deploy.add_argument('--root', type=Path, required=True)
    revert = commands.add_parser('rollback'); revert.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    if args.action == 'build':
        print(json.dumps({'sha256': build(args.output), 'archive': str(args.output)}))
    elif args.action == 'install':
        print(json.dumps({'release': install(args.archive, args.sha256, args.root), 'started': False}))
    else:
        print(json.dumps({'release': rollback(args.root), 'started': False}))


if __name__ == '__main__':
    main()
