#!/usr/bin/env python3
"""Privately open only this preview; never print or log the pairing value."""
from pathlib import Path
import json, subprocess, shutil, urllib.request
r=Path(__file__).resolve().parent
m=json.loads((r/'RUNNING.json').read_text())
assert m['bind']=='127.0.0.1' and m['port']!=8766
key=(r/'data/pairing-token').read_text().strip()
req=urllib.request.Request(m['url']+'api/evolution/state',headers={'Authorization':'Bearer '+key})
with urllib.request.urlopen(req,timeout=5) as response:
    state=json.load(response)
assert state['synthetic_only'] is True and state['project']=='phase2-synthetic'
opener=shutil.which('termux-open-url')
if not opener: raise SystemExit('Android URL opener unavailable')
result=subprocess.run([opener,m['url']+'#pair='+key],capture_output=True,timeout=15)
print('Android staging-open request '+('accepted' if result.returncode==0 else 'failed')+'. Pairing value not displayed.')
raise SystemExit(result.returncode)
