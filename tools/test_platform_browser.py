#!/usr/bin/env python3
"""Real Chromium dashboard test with mobile emulation and local model fixtures.

Requires Playwright and its Chromium binary. No real provider or memory access.
"""
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from hermes_platform.contracts import MODEL_ROLES
from hermes_platform.tests.support import FakeOllama


class BrowserTests(unittest.TestCase):
    def test_mobile_desktop_approval_persistence_and_safe_rendering(self):
        from playwright.sync_api import sync_playwright, expect
        model = FakeOllama()
        server = None
        try:
            with tempfile.TemporaryDirectory(prefix='hermes-browser-') as directory:
                root = Path(directory)
                config = root / 'platform.json'
                config.write_text(json.dumps({'routes': {role: dict(model.route) for role in MODEL_ROLES},
                                               'seconds': 10, 'memory_sources': {}}))
                def start():
                    process = subprocess.Popen([sys.executable, '-B', '-m', 'hermes_platform.server',
                        '--data', str(root / 'state'), '--config', str(config), '--port', '0'],
                        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    if not select.select([process.stdout], [], [], 15)[0]:
                        process.terminate(); process.wait(5)
                        raise RuntimeError('Platform startup timeout')
                    line = process.stdout.readline()
                    if not line:
                        raise RuntimeError('Platform did not start: ' + process.stderr.read()[-1000:])
                    return process, 'http://127.0.0.1:' + str(json.loads(line)['port'])
                def stop(process):
                    process.terminate(); process.wait(8); process.stdout.close(); process.stderr.close()
                server, url = start()
                token = (root / 'state/pairing-token').read_text()
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(headless=True)
                    page = browser.new_page(viewport={'width': 393, 'height': 851}, is_mobile=True, has_touch=True)
                    errors = []; page.on('pageerror', lambda error: errors.append(str(error)))
                    page.goto(url)
                    page.locator('#token').fill('x' * 43); page.locator('#pair-form button').click()
                    expect(page.locator('#notice')).to_contain_text('Pairing required')
                    page.locator('#token').fill(token); page.locator('#pair-form button').click()
                    expect(page.locator('#workspace')).to_be_visible()
                    expect(page.locator('.agent')).to_have_count(6)
                    prompt = 'Create a sorting helper. Synthetic display probe: <img src=x onerror=alert(1)>'
                    page.locator('#prompt').fill(prompt); page.locator('#send').click()
                    expect(page.locator('#approval')).to_be_visible(timeout=20000)
                    expect(page.locator('#task-title')).to_have_text(prompt)
                    expect(page.locator('.messages img')).to_have_count(0)
                    self.assertFalse(page.evaluate('document.documentElement.scrollWidth > innerWidth'))
                    page.locator('#approve').click()
                    expect(page.locator('#task-status')).to_have_text('approved')
                    page.set_viewport_size({'width': 1280, 'height': 900})
                    self.assertFalse(page.evaluate('document.documentElement.scrollWidth > innerWidth'))
                    page.set_viewport_size({'width': 393, 'height': 851})
                    page.screenshot(path='/tmp/hermes-platform-mobile.png', full_page=True)
                    page.reload(); expect(page.locator('#pair-form')).to_be_visible()
                    self.assertEqual(page.locator('#token').input_value(), '')
                    stop(server); server = None
                    server, url = start()
                    self.assertEqual((root / 'state/pairing-token').read_text(), token)
                    page.goto(url); page.locator('#token').fill(token); page.locator('#pair-form button').click()
                    expect(page.locator('#tasks button')).to_have_count(1)
                    page.locator('#tasks button').click()
                    expect(page.locator('#task-status')).to_have_text('approved')
                    self.assertEqual(errors, [])
                    browser.close()
                stop(server); server = None
        finally:
            if server is not None:
                server.terminate(); server.wait(8); server.stdout.close(); server.stderr.close()
            model.close()


if __name__ == '__main__':
    unittest.main(verbosity=2)
