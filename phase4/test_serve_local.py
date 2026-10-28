import importlib.util
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location("serve_local", Path(__file__).with_name("serve_local.py"))
serve_local = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(serve_local)


class LocalOnlySafetyTests(unittest.TestCase):
    def test_unknown_model_fails_closed(self):
        self.assertGreater(serve_local.required_mib("missing", {}), 1000000)

    def test_qwen_9b_needs_large_headroom(self):
        self.assertEqual(serve_local.required_mib("qwen2.5:9b", {"qwen2.5:9b": 1}), 12288)

    def test_small_model_keeps_existing_reviewed_floor(self):
        self.assertEqual(serve_local.required_mib("android-1b:latest", {"android-1b:latest": 1321099632}), 2560)


if __name__ == "__main__":
    unittest.main()
