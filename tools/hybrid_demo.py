#!/usr/bin/env python3
"""Run the synthetic three-agent protocol without reading any Hermes state."""
from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evolution_addons.hybrid import synthetic_coordinator

if __name__ == '__main__':
    result = synthetic_coordinator().run({
        'project': 'synthetic-demo', 'specification': 'Review a synthetic fixture',
        'synthetic': True, 'wall_seconds': 5, 'max_output_bytes': 8192})
    print(json.dumps(result, indent=2))
