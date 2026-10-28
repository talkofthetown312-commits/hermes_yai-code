#!/usr/bin/env python3
"""Start dedicated tmux services, authenticate readiness, optionally open paired UI.
The token stays in private storage, the local tmux pane and a browser fragment.
"""
import argparse
import json
import pathlib
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent
DATA = pathlib.Path.home()/'.hermes-pocket'
URL = 'http://127.0.0.1:8766/'


def running(port):
    try:
        with socket.create_connection(('127.0.0.1',port),timeout=1):
            return True
    except OSError:
        return False


def start_session(name, command):
    # Deliberately refuse to replace an existing pane or kill another service.
    exists = subprocess.run(['tmux','has-session','-t','='+name],capture_output=True).returncode == 0
    if exists:
        # A dedicated pane may still be importing Hermes; readiness below waits
        # for it instead of replacing it or treating normal startup as failure.
        return
    import shlex
    subprocess.run(['tmux','new-session','-d','-s',name,'exec '+shlex.join(command)],check=True)


def status():
    token=(DATA/'pairing-token').read_text().strip()
    req=urllib.request.Request(URL+'api/status',headers={'Authorization':'Bearer '+token})
    with urllib.request.urlopen(req,timeout=2) as r:
        state=json.load(r)
    return state,token


def main():
    raise RuntimeError('Legacy live-service launcher disabled in the isolated copy; use staged test harness only')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--open',action='store_true',help='Open browser and pair with private token fragment')
    args=parser.parse_args()
    if not shutil.which('tmux'):
        raise RuntimeError('tmux is required; no packages were installed automatically.')
    if not running(11434) and shutil.which('ollama'):
        start_session('hermes-pocket-ollama',[shutil.which('ollama'),'serve'])
    if not running(8766):
        start_session('hermes-pocket',[shutil.which('python') or 'python',str(ROOT/'bridge.py')])
    deadline=time.monotonic()+60
    state=None
    while time.monotonic()<deadline:
        try:
            state,token=status()
            break
        except urllib.error.HTTPError as e:
            e.close()
            raise RuntimeError('The service on port 8766 rejected Pocket authentication; left untouched.') from None
        except (OSError,ValueError):
            time.sleep(0.4)
    if not state or not state.get('ready'):
        raise RuntimeError('Bridge not ready; inspect tmux session hermes-pocket. No service was replaced.')
    print('Ready: '+URL)
    print('Hermes adapter: '+state.get('adapter','unknown'))
    print("Pairing token is shown only in the local pane: tmux attach -t '=hermes-pocket'")
    if args.open:
        opener=shutil.which('termux-open-url')
        if not opener:
            raise RuntimeError('termux-open-url is unavailable. Open the URL and pair manually.')
        result=subprocess.run([opener,URL+'#pair='+token],capture_output=True,timeout=15)
        if result.returncode:
            raise RuntimeError('Android could not open the browser; pair manually from the local tmux pane.')
        print('Opened locally paired browser link; token is never sent in an HTTP URL.')


if __name__=='__main__':
    try:
        main()
    except Exception as e:
        print('Start failed: '+str(e))
        raise SystemExit(1)
