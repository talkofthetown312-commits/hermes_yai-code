#!/usr/bin/env python3
"""Test-owned loopback preview: synthetic only, no original credentials or services."""
from pathlib import Path
import os, sys, json, time
ROOT = Path(__file__).resolve().parent
os.umask(0o077)
home = ROOT/'runtime-home'
home.mkdir(mode=0o700,exist_ok=True)
path = os.environ.get('PATH','')
os.environ.clear()
os.environ.update(PATH=path, HOME=str(home), HERMES_HOME=str(home/'hermes'), HERMES_POCKET_DATA=str(ROOT/'data'), HERMES_POCKET_PORT='8877', PYTHONDONTWRITEBYTECODE='1')
sys.dont_write_bytecode = True
sys.path.insert(0,str(ROOT/'pocket'))
import bridge
bridge.CAPABILITY = {'ready':False,'local_ready':False,'detail':'PHONE STAGING ONLY: synthetic workbench; chat, inference and training disabled.'}
bridge.local_models = lambda: {'online':False,'models':[],'detail':'Disabled for synthetic phone preview; no live model service contacted.'}
class PreviewHandler(bridge.Handler):
    def do_POST(self):
        if not self.path.startswith('/api/evolution/'):
            if not self.allowed(): return
            return self.reply(403,{'error':'Only the synthetic Evolution workbench may mutate staging data. Chat and uploads disabled.'})
        return super().do_POST()
server = bridge.ThreadingHTTPServer(('127.0.0.1',8877),PreviewHandler)
bridge.PORT = server.server_port
meta = {'pid':os.getpid(),'port':server.server_port,'bind':'127.0.0.1','url':f'http://127.0.0.1:{server.server_port}/','started_at':time.time(),'root':str(ROOT),'synthetic_only':True,'production_changes':[]}
(ROOT/'RUNNING.json').write_text(json.dumps(meta,indent=2))
print('PHONE STAGING ONLY ready: '+meta['url'],flush=True)
print('Pairing remains private; no original credentials imported.',flush=True)
try:
    server.serve_forever()
finally:
    server.server_close()
