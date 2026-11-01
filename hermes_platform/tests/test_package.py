import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

from hermes_platform.contracts import PolicyError
from hermes_platform.package import build, digest, install, package_contents, rollback


class PackageTests(unittest.TestCase):
    def test_build_install_repeat_and_checksum_rejection(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); archive = root / 'release.tar.gz'; checksum = build(archive)
            destination = root / 'app'
            target = install(archive, checksum, destination)
            self.assertEqual(install(archive, checksum, destination), target)
            self.assertTrue((destination / 'current/hermes_platform/server.py').is_file())
            self.assertFalse((destination / 'data').exists())
            with self.assertRaises(PolicyError):
                install(archive, '0' * 64, destination)

    def test_two_releases_and_rollback_preserve_data(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); first = root / 'one.tar.gz'; checksum1 = build(first)
            app = root / 'app'; install(first, checksum1, app)
            data = app / 'data'; data.mkdir(); (data / 'sentinel').write_text('synthetic-preserved-state')
            files = package_contents(first, checksum1)
            files['hermes_platform/__init__.py'] += b'\n# Synthetic release update\n'
            files['manifest.json'] = json.dumps({name: digest(raw) for name, raw in files.items()}).encode()
            second = root / 'two.tar.gz'
            with tarfile.open(second, 'w:gz') as archive:
                for name, raw in files.items():
                    info = tarfile.TarInfo(name); info.size = len(raw); archive.addfile(info, io.BytesIO(raw))
            checksum2 = digest(second.read_bytes()); install(second, checksum2, app)
            self.assertEqual(rollback(app), 'releases/' + checksum1)
            self.assertEqual((data / 'sentinel').read_text(), 'synthetic-preserved-state')

    def test_archive_traversal_and_foreign_directory_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); bad = root / 'bad.tar.gz'
            with tarfile.open(bad, 'w:gz') as archive:
                info = tarfile.TarInfo('../escape'); info.size = 1; archive.addfile(info, io.BytesIO(b'x'))
            with self.assertRaises(PolicyError):
                install(bad, digest(bad.read_bytes()), root / 'app')
            good = root / 'good.tar.gz'; checksum = build(good)
            foreign = root / 'foreign'; foreign.mkdir(); (foreign / 'keep').write_text('preserved')
            with self.assertRaises((PolicyError, OSError)):
                install(good, checksum, foreign)
            self.assertEqual((foreign / 'keep').read_text(), 'preserved')


if __name__ == '__main__':
    unittest.main()
