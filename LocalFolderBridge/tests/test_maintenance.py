"""Distribution and Windows regressions; fixtures only, no cloud credentials."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import zipfile

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
import app
from bridge.security import BridgeError
from bridge import __version__
from bridge.windows import protect_secret, unprotect_secret
from tools import package
from tools import verify_package
from tools.fixtures import isolated_directory


class DistributionRegressionTests(unittest.TestCase):
    def test_unknown_local_files_are_not_distribution_sources(self):
        with isolated_directory(prefix='lfb-package-') as folder:
            root = Path(folder)
            (root / 'README.md').write_text('public fixture', encoding='utf-8')
            (root / '.env').write_text('EXAMPLE_PRIVATE=value', encoding='utf-8')
            (root / 'private-notes.md').write_text('private fixture', encoding='utf-8')
            (root / 'docs').mkdir()
            (root / 'docs' / 'private-plan.md').write_text('private', encoding='utf-8')
            with patch.object(package, 'ROOT', root):
                # The reviewed file list must be explicit, not every unknown file
                # that happens not to look like a key or a runtime binary.
                with patch.object(package, 'SHARE_FILES', ('README.md',)):
                    names = {str(p.relative_to(root)) for p in package.sources()}
            self.assertEqual(names, {'README.md'})

    def test_safe_relative_rejects_cross_platform_aliases(self):
        for name in ('', '/file', '../file', 'dir/../file', 'C:/file', 'a:stream',
                     'dir\\file', './file', 'dir//file', 'file\n'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                package.safe_relative(name)

    def test_missing_allowlisted_file_is_an_error(self):
        with isolated_directory() as folder, patch.object(package, 'ROOT', Path(folder)), \
             patch.object(package, 'SHARE_FILES', ('missing.md',)):
            with self.assertRaises(FileNotFoundError):
                list(package.sources())

    def test_source_hardlinks_are_rejected(self):
        with isolated_directory() as folder:
            root = Path(folder)
            original = root / 'original.md'
            original.write_text('fixture', encoding='utf-8')
            (root / 'linked.md').hardlink_to(original)
            with self.assertRaises(ValueError):
                package.checked_file(root, 'linked.md')

    def test_duplicate_casefolded_names_are_rejected(self):
        with isolated_directory() as folder:
            root = Path(folder)
            (root / 'README.md').write_text('fixture', encoding='utf-8')
            with patch.object(package, 'ROOT', root), \
                 patch.object(package, 'SHARE_FILES', ('README.md', 'Readme.md')), \
                 self.assertRaises(ValueError):
                list(package.sources())

    def test_build_is_repeatable_and_does_not_overwrite_imported_manifest(self):
        with isolated_directory() as folder:
            base = Path(folder)
            root = base / 'source'
            root.mkdir()
            (root / 'README.md').write_text('中文 fixture', encoding='utf-8')
            original_manifest = root / 'MANIFEST.sha256'
            original_manifest.write_text('original provenance', encoding='utf-8')
            with patch.object(package, 'ROOT', root), \
                 patch.object(package, 'SHARE_FILES', ('README.md',)):
                a = package.build_archive(base / 'first.zip')
                b = package.build_archive(base / 'second.zip')
            self.assertEqual(a['sha256'], b['sha256'])
            self.assertEqual(original_manifest.read_text(encoding='utf-8'), 'original provenance')
            with zipfile.ZipFile(base / 'first.zip') as archive:
                self.assertEqual(set(archive.namelist()), {'LocalFolderBridge/README.md', 'LocalFolderBridge/MANIFEST.sha256'})
                expected = hashlib.sha256((root / 'README.md').read_bytes()).hexdigest()
                self.assertEqual(archive.read('LocalFolderBridge/MANIFEST.sha256').decode('utf-8'), expected + '  README.md\n')

    def test_credential_shapes_fail_without_echo_or_overwrite(self):
        with isolated_directory() as folder:
            base = Path(folder)
            root = base / 'source'
            root.mkdir()
            target = base / 'existing.zip'
            target.write_bytes(b'previous good archive')
            for secret in ('sk-' + 'x' * 48, 'tunnel_' + 'a' * 32):
                (root / 'README.md').write_text(secret, encoding='utf-8')
                with patch.object(package, 'ROOT', root), \
                     patch.object(package, 'SHARE_FILES', ('README.md',)), \
                     self.assertRaises(ValueError) as cm:
                    package.build_archive(target)
                self.assertNotIn(secret, str(cm.exception))
                self.assertEqual(target.read_bytes(), b'previous good archive')

    def test_archive_cannot_be_written_into_source(self):
        with isolated_directory() as folder, patch.object(package, 'ROOT', Path(folder)):
            with self.assertRaises(ValueError):
                package.build_archive(Path(folder) / 'bad.zip')


class StartupRegressionTests(unittest.TestCase):
    def test_version_cli_does_not_start_service(self):
        output = io.StringIO()
        with patch.object(sys, 'argv', ['app.py', '--version']), \
             contextlib.redirect_stdout(output), self.assertRaises(SystemExit) as cm:
            app.main()
        self.assertEqual(cm.exception.code, 0)
        self.assertEqual(output.getvalue().strip(), __version__)

    def test_second_no_browser_launch_does_not_open_browser(self):
        with isolated_directory(prefix='lfb-second-') as folder:
            state = Path(folder)
            (state / 'runtime.json').write_text(json.dumps({
                'url': 'http://127.0.0.1:18765', 'admin_token': 'fixture-only'
            }), encoding='utf-8')
            lock_function = 'msvcrt.locking' if os.name == 'nt' else 'fcntl.flock'
            with patch.object(sys, 'argv', ['app.py', '--no-browser', '--state-dir', str(state)]), \
                 patch(lock_function, side_effect=OSError('fixture lock held')), \
                 patch.object(app.webbrowser, 'open') as browser, \
                 contextlib.redirect_stdout(io.StringIO()):
                app.main()
            browser.assert_not_called()


class ManifestTests(unittest.TestCase):
    def test_duplicate_manifest_entries_are_rejected(self):
        with isolated_directory() as folder:
            root = Path(folder)
            content = b'fixture'
            (root / 'README.md').write_bytes(content)
            line = hashlib.sha256(content).hexdigest() + '  README.md\n'
            (root / 'MANIFEST.sha256').write_text(line * 2, encoding='utf-8')
            with patch.object(verify_package, 'ROOT', root), \
                 patch.object(package, 'SHARE_FILES', ('README.md',)), \
                 contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(verify_package.main(), 1)

    def test_malformed_manifest_fails_without_traceback(self):
        with isolated_directory() as folder:
            root = Path(folder)
            (root / 'MANIFEST.sha256').write_text('malformed line\n', encoding='utf-8')
            with patch.object(verify_package, 'ROOT', root), \
                 contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(verify_package.main(), 1)


@unittest.skipUnless(os.name == 'nt', 'Windows DPAPI is not available on this OS')
class WindowsCredentialTests(unittest.TestCase):
    def test_dpapi_unicode_round_trip_with_synthetic_secret(self):
        value = 'fictional-test-value-仅用于隔离测试'
        encrypted = protect_secret(value)
        self.assertNotIn(value.encode('utf-8'), encrypted)
        self.assertEqual(unprotect_secret(encrypted), value)

    def test_dpapi_rejects_tampered_ciphertext(self):
        encrypted = bytearray(protect_secret('fictional-test-value'))
        encrypted[-1] ^= 1
        with self.assertRaises(BridgeError):
            unprotect_secret(bytes(encrypted))


if __name__ == '__main__':
    unittest.main()
