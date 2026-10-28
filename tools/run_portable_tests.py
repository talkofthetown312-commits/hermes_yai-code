#!/usr/bin/env python3
"""Explicit portable subset; never fabricates private baselines or model evidence.
Run in a NEW extracted working copy, not original source/staging/production trees.
"""
from pathlib import Path
import ast, json, os, subprocess, sys, types, unittest
from bootstrap_synthetic import bootstrap
ROOT=Path(__file__).resolve().parents[1]
def main():
    os.umask(0o077)
    bootstrap()
    path=os.environ.get('PATH',''); tmp=ROOT/'portable-test-runtime';tmp.mkdir(exist_ok=True,mode=0o700)
    os.environ.clear();os.environ.update(PATH=path,HOME=str(tmp/'home'),HERMES_HOME=str(tmp/'home/hermes'),TMPDIR=str(tmp),PYTHONDONTWRITEBYTECODE='1')
    sys.dont_write_bytecode=True
    stage=ROOT/'phase1/implementation';sys.path.insert(0,str(stage/'pocket'))
    source=stage/'run_acceptance.py'; tree=ast.parse(source.read_text(),str(source))
    # These four top-level initializers refer to intentionally excluded private
    # preservation manifests/payload/model. No selected test uses those names.
    private_names={'M','GUARD','BASE','MODEL'}
    tree.body=[n for n in tree.body if not (isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id in private_names for t in n.targets))]
    module=types.ModuleType('run_acceptance');module.__file__=str(source);sys.modules['run_acceptance']=module
    exec(compile(ast.fix_missing_locations(tree),str(source),'exec'),module.__dict__)
    selected=['P04','P06','P08']+['R%02d'%i for i in range(1,9)]+['S%02d'%i for i in range(1,8)]+['J02','J03','J04','J05','J06','J08']+['D%02d'%i for i in range(1,9)]+['L01','M01','M03','M04','M05','M06']
    results=[]
    for name in selected:
        try: getattr(module,name)();results.append({'test':name,'status':'PASS'})
        except Exception as e:results.append({'test':name,'status':'FAIL','error_type':type(e).__name__})
    edges=types.ModuleType('portable_edges');edges.__file__=str(stage/'test_edges.py')
    exec(compile((stage/'test_edges.py').read_text(),edges.__file__,'exec'),edges.__dict__)
    result=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromModule(edges))
    sys.path.pop(0)
    # Each suite runs in a child interpreter so bridge imports cannot cross phases.
    regressions=[]
    for rel in ['phase1/implementation','phase2']:
        s=ROOT/rel
        # Archived runners assume their runtime HOME already exists on the phone.
        # A fresh source extraction intentionally contains no runtime directories.
        (s/'runtime-home/hermes').mkdir(parents=True,exist_ok=True,mode=0o700)
        # Fake workers resolve sys.executable when created; never rewrite source.
        script=ROOT/'phase2/run_regressions.py'
        report=s/'REGRESSION_RESULTS.json'
        report.unlink(missing_ok=True)  # Never report stale archived results after a crash.
        p=subprocess.run([sys.executable,str(script),'--stage',str(s)],cwd=s,env=dict(os.environ),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=120)
        regressions.append({'phase':rel,'exit_code':p.returncode,'results':json.loads(report.read_text()) if report.exists() else None})
        if p.returncode: print(p.stderr[-3000:])
    export=subprocess.run(['node',str(ROOT/'phase2/test_export_adapter.cjs')],cwd=ROOT/'phase2',env=dict(os.environ),capture_output=True,text=True,timeout=30)
    if export.returncode: print(export.stderr[-3000:])
    addon_report=ROOT/'ADDON_TEST_RESULTS.json'
    addon_report.unlink(missing_ok=True)
    addon=subprocess.run([sys.executable,str(ROOT/'tools/run_addon_tests.py')],cwd=ROOT,env=dict(os.environ),capture_output=True,text=True,timeout=60)
    if addon.returncode: print(addon.stderr[-6000:])
    addons=json.loads(addon_report.read_text()) if addon_report.exists() else None
    out={'addon_tests':addons,'addon_exit_code':addon.returncode,'portable_acceptance':results,'portable_acceptance_passed':sum(x['status']=='PASS' for x in results),'edge_tests':result.testsRun,'edge_failures':len(result.failures),'edge_errors':len(result.errors),'offline_regressions':regressions,'mocked_export_exit_code':export.returncode,'original_64_entry_acceptance_rerun':False,'private_model_preservation_and_live_jcode_checks':'NOT_RUN','actual_android_rendering':'NOT_VERIFIED','model_calls':0,'training':False}
    (ROOT/'PORTABLE_TEST_RESULTS.json').write_text(json.dumps(out,indent=2)+'\n')
    print(json.dumps(out,indent=2))
    return 0 if all(x['status']=='PASS' for x in results) and result.wasSuccessful() and all(x['exit_code']==0 for x in regressions) and export.returncode==0 and addon.returncode==0 and addons is not None else 1
if __name__=='__main__': raise SystemExit(main())
