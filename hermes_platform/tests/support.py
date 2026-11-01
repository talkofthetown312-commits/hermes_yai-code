import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading

from hermes_platform.contracts import MODEL_ROLES
from hermes_platform.models import ModelError

OUTPUTS = {
    'coordinator': {'summary': 'Plan a sorting helper', 'assignments': {'research': 'Check sorting behavior', 'developer': 'Propose a pure sorting function'}},
    'research': {'summary': 'Sorting research', 'findings': ['Use the built-in sorted function']},
    'developer': {'summary': 'Sorting helper', 'artifacts': [{'path': 'sorter.py', 'content': 'def sort_items(items):\n    return sorted(items)\n'}]},
    'validator': {'summary': 'Review syntax and behavior', 'passed': True, 'issues': []},
    'reviewer': {'summary': 'Proposal ready for human review', 'approved': True, 'risks': ['Generated code has not been executed']},
}


def body(**changes):
    return {'prompt': 'Create a sorting helper for synthetic values', 'cloud_consent': False, 'memory_sources': []} | changes


class FakeRouter:
    def __init__(self):
        self.routes = {role: {'provider': 'ollama', 'model': 'synthetic'} for role in MODEL_ROLES}
        self.calls = []
        self.failures = 0

    def generate(self, role, context, cloud_consent, has_memory, cancelled):
        self.calls.append((role, context))
        if self.failures:
            self.failures -= 1
            raise ModelError('transport_unavailable', True)
        return json.loads(json.dumps(OUTPUTS[role]))


class FakeOllama:
    def __init__(self):
        self.calls = []
        owner = self
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                packet = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                owner.calls.append(packet)
                role = packet['messages'][0]['content'].split('You are the ')[1].split(' agent')[0]
                raw = json.dumps({'model': packet['model'], 'done': True, 'message': {'content': json.dumps(OUTPUTS[role])}}).encode()
                self.send_response(200); self.send_header('Content-Length', str(len(raw))); self.end_headers(); self.wfile.write(raw)
            def log_message(self, *args):
                pass
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def route(self):
        return {'provider': 'ollama', 'model': 'qwen-synthetic', 'endpoint': f'http://127.0.0.1:{self.server.server_port}', 'key_env': None}

    def close(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()
