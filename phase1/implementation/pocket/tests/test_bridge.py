import importlib.util, json, os, pathlib, sys, tempfile, threading, time, unittest
import urllib.request, urllib.error

class BridgeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        os.environ['HERMES_POCKET_DATA'] = cls.temp.name
        fake = pathlib.Path(cls.temp.name)/'fake-hermes'
        fake.write_text('#!' + sys.executable + '\n' + '''import sys,json,time
a=sys.argv[1:]
if '--help' in a:
 print('--format stream-json --resume --provider --base-url --api-key --model');sys.exit()
prompt=a[a.index('-q')+1]
sid=a[a.index('--resume')+1] if '--resume' in a else 'test-session-'+str(time.time_ns())
print(json.dumps({'type':'system','subtype':'init','session_id':sid}),flush=True)
time.sleep(.12)
print(json.dumps({'type':'text','text':'Simulated reply'}),flush=True)
print(json.dumps({'type':'tool_use','name':'test_tool'}),flush=True)
print(json.dumps({'type':'result','session_id':sid,'exit_code':0,'text':json.dumps({'prompt':prompt,'args':a})}),flush=True)
''')
        fake.chmod(0o700); os.environ['HERMES_BIN']=str(fake)
        path=pathlib.Path(__file__).resolve().parents[1]/'bridge.py'
        spec=importlib.util.spec_from_file_location('bridge',path)
        cls.b=importlib.util.module_from_spec(spec);spec.loader.exec_module(cls.b)
        cls.b.CAPABILITY=cls.b.probe()
        cls.b.local_models=lambda:{'online':True,'models':['test-model']}
        cls.server=cls.b.ThreadingHTTPServer(('127.0.0.1',0),cls.b.Handler)
        cls.b.PORT=cls.server.server_port
        threading.Thread(target=cls.server.serve_forever,daemon=True).start()
        cls.url=f'http://127.0.0.1:{cls.b.PORT}'
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.temp.cleanup()
    def req(self,path,body=None,token=True,origin=None):
        headers={'Authorization':'Bearer '+self.b.TOKEN if token else '','Content-Type':'application/json'}
        if origin:headers['Origin']=origin
        req=urllib.request.Request(self.url+'/api/'+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
        try:
            with urllib.request.urlopen(req,timeout=5) as r:return json.load(r)
        except urllib.error.HTTPError as e:
            e.close()
            raise
    def wait_chat(self,cid):
        for _ in range(100):
            chat=self.req('chats/'+cid)
            if chat['state']!='running':return chat
            time.sleep(.03)
        self.fail('Turn timed out')
    def test_auth_and_origin(self):
        with self.assertRaises(urllib.error.HTTPError) as e:self.req('status',token=False)
        self.assertEqual(e.exception.code,401)
        with self.assertRaises(urllib.error.HTTPError) as e:self.req('chats',{},origin='https://untrusted.example')
        self.assertEqual(e.exception.code,403)
    def test_cloud_resume_literal_prompt_and_busy(self):
        cid=self.req('chats',{'mode':'cloud'})['id']
        prompt='Literal $(touch /tmp/never-run-this) `echo hi` <script>alert(1)</script>'
        self.req('send',{'id':cid,'message':prompt})
        with self.assertRaises(urllib.error.HTTPError) as e:self.req('send',{'id':cid,'message':'duplicate'})
        self.assertEqual(e.exception.code,409)
        chat=self.wait_chat(cid);self.assertEqual(chat['state'],'idle')
        result=json.loads(chat['messages'][-1]['text'])
        self.assertEqual(result['prompt'],prompt);self.assertNotIn('--provider',result['args'])
        sid=chat['session'];self.req('send',{'id':cid,'message':'second'})
        chat=self.wait_chat(cid);result=json.loads(chat['messages'][-1]['text'])
        self.assertEqual(chat['session'],sid);self.assertIn('--resume',result['args'])
    def test_local_provider_and_unknown_model(self):
        with self.assertRaises(urllib.error.HTTPError):self.req('chats',{'mode':'local','model':'unknown'})
        cid=self.req('chats',{'mode':'local','model':'test-model'})['id']
        self.req('send',{'id':cid,'message':'hello'})
        chat=self.wait_chat(cid);self.assertEqual(chat['state'],'idle')
        args=json.loads(chat['messages'][-1]['text'])['args']
        self.assertEqual(args[args.index('--provider')+1],'custom')
        self.assertEqual(args[args.index('--base-url')+1],'http://127.0.0.1:11434/v1')
        self.assertEqual(args[args.index('--model')+1],'test-model')
    def test_unsupported_version_blocks_chat(self):
        original=self.b.CAPABILITY
        try:
            self.b.CAPABILITY={'ready':False,'detail':'Adapter needed'}
            cid=self.req('chats',{'mode':'cloud'})['id']
            with self.assertRaises(urllib.error.HTTPError) as e:self.req('send',{'id':cid,'message':'hello'})
            self.assertEqual(e.exception.code,409)
        finally:self.b.CAPABILITY=original

if __name__=='__main__':unittest.main()
