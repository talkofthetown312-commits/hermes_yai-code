#!/usr/bin/env python3
"""Stop ONLY the recorded test-owned preview after verifying exact process identity."""
from pathlib import Path
import json,os,signal,socket,time
r=Path(__file__).resolve().parent
m=json.loads((r/'RUNNING.json').read_text())
assert m['root']==str(r) and m['port']==8877 and m['bind']=='127.0.0.1'
pid=m['pid']; expected=str(r/'serve_preview.py')
try:
    argv=Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')
except FileNotFoundError:
    print('Recorded preview process already stopped. No signal sent.');raise SystemExit(0)
if expected.encode() not in argv:
    raise SystemExit('Process identity changed; refusing to signal anything.')
os.kill(pid,signal.SIGTERM)
deadline=time.monotonic()+5
while time.monotonic()<deadline:
    try:
        with socket.create_connection(('127.0.0.1',8877),timeout=.3): pass
    except OSError:
        print('Only the test-owned preview was stopped; port 8877 is closed. Production untouched.');break
    time.sleep(.1)
else: raise SystemExit('Preview port still responds. No other process was signalled.')
