"""Optional real-browser development UI check; no model/provider calls."""
from pathlib import Path
import sys
import tempfile
import shutil
import threading
from http.server import ThreadingHTTPServer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hermes_runtime.server import Runtime, handler
from test_runtime import FakeProviders


def main():
    from playwright.sync_api import sync_playwright, expect
    with tempfile.TemporaryDirectory() as directory:
        runtime = Runtime(Path(directory) / 'runtime', {'project': 'browser-test'}, FakeProviders())
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler(runtime))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, executable_path=shutil.which('chromium'))
                page = browser.new_page(viewport={'width': 390, 'height': 844})
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(f'http://127.0.0.1:{server.server_port}/#pair={runtime.token}')
                try:
                    expect(page.locator('#settings')).to_have_text('Paired')
                except AssertionError:
                    print('Browser errors:', errors)
                    print('Connection notice:', page.locator('#notice').inner_text())
                    raise
                page.locator('#models').select_option('fixture-local')
                page.locator('#prompt').fill('Hello browser')
                page.locator('#send').click()
                expect(page.locator('#messages')).to_contain_text('Fixture response: Hello browser')
                page.locator('#runtime-toggle').click()
                page.get_by_role('heading', name='Tasks and setup').wait_for()
                page.locator('#runtime-toggle').click()
                if not page.locator('#evolution-panel').is_visible():
                    page.locator('#evolution-toggle').click()
                page.get_by_role('heading', name='Hermes Evolution workbench').wait_for()
                page.screenshot(path=str(Path(directory) / 'runtime-ui.png'), full_page=True)
                assert not errors, errors
                browser.close()
                print('PASS: mobile browser pairing, model selection, chat, tasks and workbench; no JavaScript errors')
        finally:
            server.shutdown(); server.server_close(); thread.join(); runtime.close()


if __name__ == '__main__':
    main()
