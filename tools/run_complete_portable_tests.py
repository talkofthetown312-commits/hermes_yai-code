#!/usr/bin/env python3
"""Complete source-handoff tests. Synthetic only; no installed services are used.
Run in a NEW extracted copy. The full private/model 64-entry acceptance is gated.
"""
from pathlib import Path
import json
import os
import re
import select
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]


def main():
    os.umask(0o077)
    (ROOT / 'COMPLETE_PORTABLE_TEST_RESULTS.json').unlink(missing_ok=True)
    if (ROOT / 'phase2/handoff-runtime').exists():
        raise RuntimeError('Use a fresh extracted copy: synthetic preview runtime already exists')
    runtime = ROOT / 'portable-test-runtime'
    (runtime / 'home/hermes').mkdir(parents=True, mode=0o700, exist_ok=True)
    env = {'PATH': os.environ.get('PATH', ''), 'HOME': str(runtime / 'home'),
           'HERMES_HOME': str(runtime / 'home/hermes'), 'TMPDIR': str(runtime),
           'PYTHONDONTWRITEBYTECODE': '1'}
    def run(args, cwd, name):
        process = subprocess.run(args, cwd=cwd, env=env, capture_output=True,
                                 text=True, timeout=240)
        (runtime / (name + '.log')).write_text(process.stdout + process.stderr)
        if process.returncode:
            raise RuntimeError(name + ' failed; inspect private runtime log')
    javascript = sorted({*ROOT.glob('phase*/**/web/*.js'), *ROOT.glob('phase*/**/test*.cjs'), *ROOT.glob('phase*/**/tests/*.cjs')})
    for path in javascript:
        run(['node', '--check', str(path)], ROOT, 'syntax-' + str(path.relative_to(ROOT)).replace('/', '-'))
    run([sys.executable, '-B', str(ROOT / 'tools/run_portable_tests.py')], ROOT, 'core')
    phase1 = ROOT / 'phase1/implementation'
    run([sys.executable, '-B', str(phase1 / 'test_http.py')], phase1, 'phase1-http')
    stage = ROOT / 'phase2'
    if (stage / 'handoff-runtime').exists():
        raise RuntimeError('Use a fresh extracted copy: synthetic preview runtime already exists')
    token_path = stage / 'handoff-runtime/data/pairing-token'
    checks = []
    server = None
    server_log = (runtime / 'synthetic-server.log').open('w')
    def start():
        nonlocal server
        server = subprocess.Popen([sys.executable, '-B', str(ROOT / 'tools/serve_synthetic.py'), '--port', '0'],
                                  cwd=ROOT, env=env, stdout=subprocess.PIPE,
                                  stderr=server_log, text=True)
        if not select.select([server.stdout], [], [], 15)[0]:
            raise RuntimeError('Synthetic server did not signal readiness')
        line = server.stdout.readline()
        found = re.fullmatch(r'Fresh synthetic preview: (http://127\.0\.0\.1:\d+/)\n', line)
        if not found:
            raise RuntimeError('Unexpected synthetic readiness response; inspect private server log')
        url = found.group(1).rstrip('/')
        if urlsplit(url).port in (8766, 8877):
            raise RuntimeError('Refusing production/staging port')
        return url
    def stop(url):
        if server is not None:
            server.terminate()
            try:
                server.wait(timeout=8)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=8)
            server.stdout.close()
        with socket.socket() as client:
            client.settimeout(2)
            if client.connect_ex(('127.0.0.1', urlsplit(url).port)) == 0:
                raise RuntimeError('Test-owned listener did not close')
    url = None
    try:
        url = start()
        key = token_path.read_text().strip()
        env.update(FIXTURE_URL=url, FIXTURE_PAIRING=key, FIXTURE_TOKEN_FILE=str(token_path))
        def request(path, data=None):
            headers = {'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'}
            q = urllib.request.Request(url + '/api/evolution/' + path, headers=headers,
                                       data=json.dumps(data).encode() if data is not None else None)
            try:
                with urllib.request.urlopen(q, timeout=5) as response:
                    return response.status, json.load(response)
            except urllib.error.HTTPError as error:
                code = error.code
                error.close()
                return code, None
        run(['node', str(stage / 'test_ui.cjs')], stage, 'phase2-dom')
        run([sys.executable, '-B', str(stage / 'test_preview_features.py')], stage, 'phase2-features')
        def check(name, condition):
            checks.append({'name': name, 'passed': bool(condition)})
            if not condition:
                raise AssertionError(name)
        _, candidate = request('select-example', {'confirm': True})
        request('review', {'id': candidate['id'], 'hash': candidate['hash'], 'confirm': True})
        _, changed = request('edit-candidate', {'id': candidate['id'], 'messages': [
            {'role': 'user', 'content': 'Return a synthetic marker.'},
            {'role': 'assistant', 'content': 'NEW_SYNTHETIC_TARGET'}]})
        check('editing clears consent', changed['review'] is None)
        check('editing requires new evidence', changed['data']['needs_reverification'] is True)
        check('edited unverified answer cannot be reapproved', request('review', {
            'id': changed['id'], 'hash': changed['hash'], 'confirm': True})[0] == 400)
        check('edited answer cannot be exported', request('export', {
            'ids': [changed['id']], 'confirm': True})[0] == 400)
        _, before = request('state')
        stop(url)
        url = start()
        check('pairing survives synthetic restart', token_path.read_text().strip() == key)
        status, after = request('state')
        check('workflow state survives synthetic restart', status == 200 and
              before['skills']['versions'] == after['skills']['versions'] and
              before['candidates'] == after['candidates'])
        check('grant revocation survives synthetic restart', request('search?q=widget')[1]['count'] == 0)
    finally:
        if server is not None:
            if url is not None:
                stop(url)
            elif server.poll() is None:
                server.terminate()
                server.wait(timeout=8)
        server_log.close()
    core = json.loads((ROOT / 'PORTABLE_TEST_RESULTS.json').read_text())
    phase1_report = json.loads((phase1 / 'HTTP_QA.json').read_text())
    feature = json.loads((stage / 'FEATURE_RESULTS.json').read_text())
    ui = json.loads((stage / 'UI_QA.json').read_text())
    export = json.loads((stage / 'EXPORT_ADAPTER_RESULTS.json').read_text())
    report = {'status': 'PASS', 'javascript_syntax_checks':len(javascript), 'core': core,
              'phase1_http': phase1_report, 'phase2_features': feature,
              'phase2_dom': ui, 'export_adapter': export,
              'dataset_edit_and_restart': checks,
              'test_owned_server_closed': True,
              'production_deployment': False, 'models_or_providers_called': False,
              'native_phone_rendering': 'NOT_VERIFIED',
              'full_private_64_entry_acceptance': 'NOT_RUN: missing private baselines and approval gates'}
    (ROOT / 'COMPLETE_PORTABLE_TEST_RESULTS.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'status': 'PASS', 'portable_acceptance': core['portable_acceptance_passed'],
                      'edge_tests': core['edge_tests'], 'regressions': core['offline_regressions'],
                      'addon_tests': core['addon_tests'],
                      'phase1_http_checks': len(phase1_report['http_checks']),
                      'phase2_feature_checks': feature['passed'],
                      'phase2_dom_assertions': ui['assertion_count'],
                      'dataset_edit_and_restart_checks': len(checks),
                      'test_owned_server_closed': True}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
