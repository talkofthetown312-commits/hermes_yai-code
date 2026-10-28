#!/usr/bin/env python3
"""Fresh synthetic development preview; never attaches to the existing phone preview."""
from pathlib import Path
import argparse, json, os, sys
from bootstrap_synthetic import bootstrap
ROOT=Path(__file__).resolve().parents[1]
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=18877);a=parser.parse_args()
    if a.port in (8766,8877) or (a.port != 0 and not 1024<=a.port<=65535): parser.error('Use port 0 for an ephemeral port or a separate non-production port; 8766 and 8877 are forbidden')
    bootstrap();stage=ROOT/'phase2'; runtime=stage/'handoff-runtime';runtime.mkdir(mode=0o700,exist_ok=True)
    assert not runtime.is_symlink()
    os.umask(0o077);path=os.environ.get('PATH','');os.environ.clear()
    os.environ.update(PATH=path,HOME=str(runtime/'home'),HERMES_HOME=str(runtime/'home/hermes'),HERMES_POCKET_DATA=str(runtime/'data'),HERMES_POCKET_PORT=str(a.port),PYTHONDONTWRITEBYTECODE='1')
    sys.dont_write_bytecode=True;sys.path.insert(0,str(stage/'pocket'))
    import bridge
    bridge.CAPABILITY={'ready':False,'local_ready':False,'detail':'Synthetic development handoff; models disabled.'}
    bridge.local_models=lambda:{'online':False,'models':[],'detail':'Model discovery disabled.'}
    class Handler(bridge.Handler):
        def do_POST(self):
            if not self.path.startswith('/api/evolution/'):
                if not self.allowed():return
                return self.reply(403,{'error':'Only synthetic Evolution workbench changes allowed.'})
            return super().do_POST()
    with bridge.ThreadingHTTPServer(('127.0.0.1',a.port),Handler) as server:
        bridge.PORT=server.server_port
        print('Fresh synthetic preview: http://127.0.0.1:%s/'%server.server_port,flush=True)
        print('Pairing is generated privately in phase2/handoff-runtime/data. Never use a production token. Ctrl-C stops only this foreground process.',flush=True)
        try:server.serve_forever()
        except KeyboardInterrupt:pass
if __name__=='__main__':main()
