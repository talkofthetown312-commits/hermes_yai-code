#!/usr/bin/env python3
"""Open the verified Phase 3 synthetic origin without printing its pairing fragment."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import urllib.request
from serve import MARKER, ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir', type=Path,
                        default=Path.home() / 'hermes-yai-phase3-staging')
    options = parser.parse_args()
    directory = options.state_dir.absolute()
    try:
        if (not directory.name.startswith('hermes-yai-phase3-') or
                any(path.is_symlink() for path in [directory, *directory.parents])):
            raise ValueError('Unsafe staging directory')
        metadata = json.loads((directory / 'server.json').read_text())
        if (metadata['format'] != MARKER or metadata['synthetic_only'] is not True
                or metadata['source'] != str(ROOT) or type(metadata['port']) is not int
                or not 1024 <= metadata['port'] <= 65535 or metadata['port'] in (8766, 8877)):
            raise ValueError('Unexpected staging metadata')
        command = (Path('/proc') / str(int(metadata['pid'])) / 'cmdline').read_bytes().split(b'\0')
        if str(ROOT / 'phase3/serve.py').encode() not in command:
            raise ValueError('Staging process identity mismatch')
        key_file = directory / 'app/data/pairing-token'
        if key_file.is_symlink():
            raise ValueError('Pairing path alias refused')
        key = key_file.read_text().strip()
        url = 'http://127.0.0.1:' + str(metadata['port']) + '/'
        request = urllib.request.Request(url + 'api/integration/dashboard',
                                         headers={'Authorization': 'Bearer ' + key})
        with urllib.request.urlopen(request, timeout=5) as response:
            state = json.load(response)
        if not (state['synthetic_only'] is True and state['project'] == 'phase3-synthetic'
                and state['providers'] == 'disabled' and state['training'] == 'disabled'):
            raise ValueError('Not a synthetic server')
        opener = shutil.which('termux-open-url')
        if not opener:
            raise ValueError('Android URL opener unavailable')
        result = subprocess.run([opener, url + '#pair=' + key], capture_output=True, timeout=15)
        print('Android staging-open request ' + ('accepted' if result.returncode == 0 else 'failed') +
              '. Pairing fragment withheld; actual rendering still needs native verification.')
        return result.returncode
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired):
        print('Staging open refused or unavailable. No pairing value displayed.')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
