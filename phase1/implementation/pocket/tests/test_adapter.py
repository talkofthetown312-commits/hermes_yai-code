"""Offline regression tests for the SDK adapter wiring (not model simulations claimed as live tests)."""
import importlib.util
import io
import json
import pathlib
import sys
import types
import unittest
from unittest.mock import patch


class FakeAgent:
    def __init__(self, cli):
        self.session_id = cli.kwargs.get('resume') or 'sdk-test-session'
        self.provider = 'custom' if cli.kwargs.get('provider') == 'custom' else 'existing-cloud'
        self.base_url = 'https://wrong.invalid/v1' if cli.wrong_route else cli.kwargs.get('base_url')
        self.model = cli.kwargs.get('model','existing-cloud-model')
        self._fallback_chain = cli._fallback_model
        self.compression_enabled = True
        self.tools = ['original-tool']
        self.called = False
    def run_conversation(self, user_message, conversation_history):
        self.called = True
        self.history = conversation_history
        self.input = user_message
        self.tool_progress_callback('tool.started',function_name='terminal')
        self.tool_start_callback('tool-1','terminal',{'command':'printf hello'})
        self.stream_delta_callback('Hello')
        self.tool_complete_callback('tool-1','terminal',{'command':'printf hello'},{'output':'hello','exit_code':0})
        self.tool_progress_callback('tool.completed',function_name='terminal')
        return {'final_response':'Hello', 'failed':False}


class FakeCLI:
    wrong_route=False
    latest=None
    def __init__(self, **kwargs):
        type(self).latest=self
        self.kwargs=kwargs
        self._fallback_model=['existing-cloud-fallback']
        self.conversation_history=[{'role':'user','content':'restored only from this session'}]
        self._session_db=types.SimpleNamespace(close=lambda:None)
    def _init_agent(self):
        self.agent=FakeAgent(self)
        return True


class AdapterTest(unittest.TestCase):
    def setUp(self):
        path=pathlib.Path(__file__).resolve().parents[1]/'hermes_adapter.py'
        spec=importlib.util.spec_from_file_location('pocket_adapter_test',path)
        self.adapter=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.adapter)
        self.adapter.WIRE=io.StringIO()
        self.approval=[]
        module=types.ModuleType('tools.terminal_tool')
        module.set_approval_callback=lambda cb:self.approval.append(cb)
        self.modules=patch.dict(sys.modules,{'cli':types.SimpleNamespace(HermesCLI=FakeCLI),'tools.terminal_tool':module})
        self.modules.start()
        FakeCLI.wrong_route=False
    def tearDown(self):
        self.modules.stop()
    def events(self):
        return [json.loads(line) for line in self.adapter.WIRE.getvalue().splitlines()]
    def test_cloud_preserves_route_and_no_private_memory(self):
        self.assertEqual(self.adapter.run({'mode':'cloud','prompt':'synthetic','resume':'own-session'}),0)
        cli=FakeCLI.latest
        self.assertNotIn('provider',cli.kwargs)
        self.assertNotIn('api_key',cli.kwargs)
        self.assertTrue(cli.kwargs['ignore_rules'])
        self.assertEqual(cli.agent.session_id,'own-session')
        self.assertEqual(cli.agent.history,cli.conversation_history)
        self.assertEqual(cli._fallback_model,['existing-cloud-fallback'])
        self.assertEqual(cli.agent.tools,['original-tool'])
        self.assertEqual(self.approval[0]('dangerous command'),'deny')
        self.assertTrue(any(e.get('name')=='terminal' for e in self.events()))
    def test_local_explicit_loopback_no_cloud_fallback_or_compression(self):
        self.adapter.run({'mode':'local','model':'installed-model','prompt':'synthetic'})
        cli=FakeCLI.latest
        self.assertEqual(cli.kwargs['provider'],'custom')
        self.assertEqual(cli.kwargs['base_url'],'http://127.0.0.1:11434/v1')
        self.assertEqual(cli.kwargs['api_key'],'ollama')
        self.assertEqual(cli._fallback_model,[])
        self.assertFalse(cli.agent.compression_enabled)
        self.assertTrue(cli.kwargs['ignore_rules'])
        self.assertFalse(self.events()[0]['fallback_enabled'])
    def test_local_wrong_route_fails_before_model_request(self):
        FakeCLI.wrong_route=True
        with self.assertRaisesRegex(RuntimeError,'loopback'):
            self.adapter.run({'mode':'local','model':'installed-model','prompt':'synthetic'})
        self.assertFalse(FakeCLI.latest.agent.called)
    def test_attachment_text_and_rich_tool_callbacks(self):
        self.adapter.run({'mode':'cloud','prompt':'summarize','attachment_text':'synthetic invoice 42'})
        self.assertIn('synthetic invoice 42',FakeCLI.latest.agent.input)
        events=self.events()
        self.assertEqual(next(e for e in events if e['type']=='tool_start')['id'],'tool-1')
        self.assertIn('hello',next(e for e in events if e['type']=='tool_complete')['output'])
    def test_tool_log_redaction_and_bounds(self):
        value=self.adapter.display_text({'api_key':'synthetic-key','Authorization':'Bearer synthetic-token','password':'fixture-pass'})
        self.assertNotIn('synthetic-key',value)
        self.assertNotIn('synthetic-token',value)
        self.assertNotIn('fixture-pass',value)
        self.assertIn('TRUNCATED',self.adapter.display_text('x'*30000))
    def test_local_images_rejected_before_initialization(self):
        with self.assertRaisesRegex(ValueError,'image input'):
            self.adapter.run({'mode':'local','prompt':'describe','images':['fixture.png']})
    def test_smoke_is_explicit_and_disables_tools(self):
        self.adapter.run({'mode':'cloud','prompt':'synthetic','smoke':True})
        self.assertEqual(FakeCLI.latest.agent.tools,[])
        self.assertEqual(FakeCLI.latest.agent.max_tokens,120)


if __name__=='__main__':
    unittest.main()
