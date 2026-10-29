#!/usr/bin/env python3
"""Run copied offline regressions in disposable, stage-owned directories only."""
from pathlib import Path
import argparse,os,sys,tempfile,unittest,json
root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--stage',type=Path,default=Path(__file__).resolve().parent)
r=parser.parse_args().stage.resolve()
if r not in {root/'phase1/implementation',root/'phase2'}:
    parser.error('Only the two extracted synthetic stages are permitted')
os.umask(0o077)
p=os.environ.get('PATH',''); os.environ.clear()
(r/'qa-temp').mkdir(mode=0o700,exist_ok=True)
(r/'runtime-home').mkdir(mode=0o700,exist_ok=True)
os.environ.update(PATH=p,HOME=str(r/'runtime-home'),HERMES_HOME=str(r/'runtime-home/hermes'),TMPDIR=str(r/'qa-temp'),HERMES_POCKET_PORT='0')
tempfile.tempdir=str(r/'qa-temp');sys.dont_write_bytecode=True
sys.path[:0]=[str(r/'pocket'),str(r/'pocket/tests')]
import test_bridge,test_files,test_adapter
suite=unittest.TestSuite()
for m in (test_bridge,test_files,test_adapter):suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(m))
result=unittest.TextTestRunner(verbosity=2).run(suite)
report={'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'real_model_calls':0,'actual_android_rendering':False,'fake_agent_only':True}
(r/'REGRESSION_RESULTS.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report));raise SystemExit(0 if result.wasSuccessful() else 1)
