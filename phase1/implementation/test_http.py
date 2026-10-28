#!/usr/bin/env python3
"""Real isolated HTTP integration + offline existing regressions + simulated-DOM clicks.
Not an Android WebView/rendering/picker/install test; never imports the live bridge.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
STAGE=Path(__file__).resolve().parent
POCKET=STAGE/'pocket'
os.umask(0o077)
(STAGE/'test-tmp').mkdir(mode=0o700,exist_ok=True)
os.environ['TMPDIR']=str(STAGE/'test-tmp'); tempfile.tempdir=os.environ['TMPDIR']
os.environ['HERMES_POCKET_PORT']='0'
sys.path[:0]=[str(POCKET),str(POCKET/'tests')]
import test_bridge
import test_files
import test_adapter

def main():
    suite=unittest.TestSuite()
    for module in (test_bridge,test_files,test_adapter): suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(module))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    report={'legacy_regression_count':result.testsRun,'legacy_failures':len(result.failures),'legacy_errors':len(result.errors),'real_model_calls':0}
    if not result.wasSuccessful():
        (STAGE/'HTTP_QA.json').write_text(json.dumps(report,indent=2)); raise SystemExit(1)
    br=test_bridge.BridgeTest
    br.setUpClass()
    api=br('test_auth_and_origin')
    checks=[]
    def check(name,value):
        if not value: raise AssertionError(name)
        checks.append(name)
    try:
        state=api.req('evolution/state'); check('23 unapproved legacy references',len(state['skills']['legacy'])==23)
        check('synthetic only project',state['project']=='phase1-synthetic' and state['synthetic_only'])
        check('default deny retrieval',api.req('evolution/search?q=widget')['count']==0)
        for path,body,kwargs,expected in [('evolution/state',None,{'token':False},401),('evolution/grant',{'source':'hermes','records':['1'],'confirm':True},{'origin':'https://untrusted.invalid'},403),('evolution/grant',{'source':'hermes','records':['1'],'confirm':True,'principal':'admin'},{},400),('evolution/teach',{'body':{},'project':'forged'},{},400),('evolution/grant',{'source':'../../state.db','records':['1'],'confirm':True},{},400),('evolution/jcode',{'packet':{'provider':'openrouter'}},{},400)]:
            try: api.req(path,body,**kwargs)
            except urllib.error.HTTPError as e: check(path+' denied '+str(expected),e.code==expected)
            else: raise AssertionError('Unexpected HTTP authorization success')
        req=urllib.request.Request(br.url+'/api/evolution/state',headers={'Host':'untrusted.invalid','Authorization':'Bearer '+br.b.TOKEN})
        try: urllib.request.urlopen(req,timeout=5)
        except urllib.error.HTTPError as e: check('host denied',e.code==403); e.close()
        else: raise AssertionError('Host accepted')
        with urllib.request.urlopen(br.url+'/',timeout=5) as r:
            raw=r.read().decode(); check('UI served', 'evolution-toggle' in raw and '/evolution.js' in raw); check('CSP header',"script-src 'self'" in r.headers['Content-Security-Policy'])
        env={**os.environ,'FIXTURE_URL':br.url,'FIXTURE_PAIRING':br.b.TOKEN}
        node=subprocess.run(['node',str(STAGE/'test_ui.cjs')],env=env,capture_output=True,text=True,timeout=40)
        if node.returncode != 0: raise AssertionError('DOM workflow: '+node.stderr+node.stdout)
        check('simulated DOM workflow result',True)
        ui=json.loads(node.stdout); report['simulated_dom']=ui
        check('UI is not native claim',ui['actual_phone_rendering'] is False)
        report.update(http_checks=checks,status='PASS',native_phone='NOT_TESTED',all_test_owned_servers_closed=True)
    finally: br.tearDownClass()
    (STAGE/'HTTP_QA.json').write_text(json.dumps(report,indent=2)); print(json.dumps(report,indent=2))
if __name__=='__main__': main()
