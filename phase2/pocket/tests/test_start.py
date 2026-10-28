import importlib.util
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch


class StartTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec=importlib.util.spec_from_file_location('pocket_start',Path(__file__).resolve().parents[1]/'start.py')
        cls.start=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.start)

    def test_exact_session_match_avoids_ollama_prefix_collision(self):
        calls=[]
        def run(args,**kwargs):
            calls.append(args)
            # tmux prefix matching would incorrectly see hermes-pocket-ollama.
            if args[:2]==['tmux','has-session']:
                return subprocess.CompletedProcess(args,1 if args[-1]=='=hermes-pocket' else 0)
            return subprocess.CompletedProcess(args,0)
        with patch.object(self.start.subprocess,'run',side_effect=run):
            self.start.start_session('hermes-pocket',['python','/private/bridge.py'])
        self.assertEqual(calls[0],['tmux','has-session','-t','=hermes-pocket'])
        self.assertEqual(calls[1][:5],['tmux','new-session','-d','-s','hermes-pocket'])

    def test_existing_exact_session_left_untouched(self):
        with patch.object(self.start.subprocess,'run',return_value=subprocess.CompletedProcess([],0)) as run:
            self.start.start_session('hermes-pocket',['python','/private/bridge.py'])
        run.assert_called_once_with(['tmux','has-session','-t','=hermes-pocket'],capture_output=True)


if __name__=='__main__': unittest.main()
