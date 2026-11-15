"""Read-only device preflight; never scans credentials, history or model directories."""
import json
import os
from pathlib import Path
import platform
import shutil


def inspect():
    memory = {}
    path = Path('/proc/meminfo')
    if path.is_file():
        for line in path.read_text().splitlines():
            if line.startswith(('MemTotal:', 'MemAvailable:')):
                key, value, *_ = line.split()
                memory[key.rstrip(':') + '_kib'] = int(value)
    return {'platform': platform.system(), 'machine': platform.machine(),
            'python': platform.python_version(), 'cpu_count': os.cpu_count(),
            'memory': memory,
            'executables_available': {name: shutil.which(name) is not None
                                      for name in ('hermes', 'ollama', 'llama-cli', 'node', 'java', 'gradle')},
            'local_model_discovery': 'not_performed', 'models_loaded': False,
            'native_android_checks': 'not_performed'}


if __name__ == '__main__':
    print(json.dumps(inspect(), indent=2))
