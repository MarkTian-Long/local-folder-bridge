#!/usr/bin/env python3
"""Build a reviewed source distribution. Unknown files are never included."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bridge import __version__

# Adding a module or document requires an intentional edit and release review.
# Historical reports, private configuration and the imported manifest are NOT
# shipped. A fresh manifest is generated inside the ZIP without changing source.
SHARE_FILES = (
    'LICENSE', 'README.md', 'CHANGELOG.md', 'DEVELOPMENT.md', 'RUN_TESTS.cmd',
    'START.cmd', 'THIRD_PARTY_NOTICES.md', 'app.py', 'requirements-dev.txt',
    'bridge/__init__.py', 'bridge/downloads.py', 'bridge/engine.py',
    'bridge/extractors.py', 'bridge/http_server.py', 'bridge/protocol.py',
    'bridge/security.py', 'bridge/store.py', 'bridge/tunnel.py', 'bridge/windows.py',
    'web/app.js', 'web/index.html', 'web/style.css', '使用手册.html',
    'docs/技术说明与安全边界.md', 'docs/操作手册.md', 'docs/插件配置说明.md',
    'docs/测试与验收报告.md', 'docs/本机复核与发布准备.md',
    'docs/images/01-overview.png', 'docs/images/02-reader.png',
    'docs/images/03-approval.png', 'docs/images/04-connection.png',
    'docs/images/05-responsive.png', 'tests/test_bridge.py',
    'tests/test_maintenance.py', 'tools/__init__.py', 'tools/build_manual.py',
    'tools/fixtures.py', 'tools/package.py', 'tools/run_tests.py',
    'tools/test_browser.py', 'tools/verify_delivery.py', 'tools/verify_package.py',
)
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_TOTAL_BYTES = 50 * 1024 * 1024
SECRET_PATTERNS = (
    rb'\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{24,}\b',
    rb'\btunnel_[0-9a-fA-F]{32}\b',
    rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
)


def safe_relative(name: str) -> PurePosixPath:
    rel = PurePosixPath(name)
    if not name or rel.is_absolute() or '\\' in name or ':' in name \
            or any(p in ('', '.', '..') for p in name.split('/')) \
            or any(ord(c) < 32 for c in name) or rel.as_posix() != name:
        raise ValueError('Unsafe distribution path')
    return rel


def checked_file(root: Path, name: str) -> Path:
    rel = safe_relative(name)
    current = root
    for part in (None, *rel.parts):
        if part is not None:
            current = current / part
        st = current.lstat()
        if stat.S_ISLNK(st.st_mode) or getattr(st, 'st_file_attributes', 0) & 0x400:
            raise ValueError('Links/reparse points cannot be packaged: ' + name)
        if current != root / rel:
            if not stat.S_ISDIR(st.st_mode):
                raise ValueError('Expected distribution directory: ' + name)
    if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
        raise ValueError('Only ordinary, non-hardlinked files can be packaged: ' + name)
    if st.st_size > MAX_FILE_BYTES:
        raise ValueError('Distribution file too large: ' + name)
    return current


def sources():
    seen = set()
    for name in sorted(SHARE_FILES):
        if name.casefold() in seen:
            raise ValueError('Duplicate distribution path')
        seen.add(name.casefold())
        yield checked_file(ROOT, name)


def build_archive(target: Path) -> dict:
    target = target.resolve()
    if target.is_relative_to(ROOT.resolve()):
        raise ValueError('Output ZIP must be outside the source tree.')
    entries = {}
    total = 0
    for path in sources():
        name = path.relative_to(ROOT).as_posix()
        content = path.read_bytes()
        total += len(content)
        if len(content) > MAX_FILE_BYTES or total > MAX_TOTAL_BYTES:
            raise ValueError('Distribution size limit exceeded')
        if any(re.search(pattern, content) for pattern in SECRET_PATTERNS):
            # Never print the suspected secret itself.
            raise ValueError('Possible credential or private Tunnel ID in: ' + name)
        entries[name] = content
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in entries.items()}
    entries['MANIFEST.sha256'] = ''.join(
        digest + '  ' + name + '\n' for name, digest in hashes.items()
    ).encode('utf-8')
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_name = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.lfb-package-', suffix='.tmp', delete=False) as tmp:
            tmp_name = Path(tmp.name)
        with zipfile.ZipFile(tmp_name, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for name, data in entries.items():
                info = zipfile.ZipInfo('LocalFolderBridge/' + name, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = (stat.S_IFREG | 0o644) << 16
                archive.writestr(info, data)
        with zipfile.ZipFile(tmp_name) as archive:
            if archive.testzip() or len(archive.namelist()) != len(entries):
                raise ValueError('ZIP integrity check failed')
            for name, data in entries.items():
                if archive.read('LocalFolderBridge/' + name) != data:
                    raise ValueError('ZIP bytes differ: ' + name)
        sha = hashlib.sha256(tmp_name.read_bytes()).hexdigest()
        report = {
            'version': __version__, 'archive': target.name,
            'files_in_archive': len(entries), 'bytes': tmp_name.stat().st_size,
            'sha256': sha, 'crc_passed': True, 'every_manifest_file_verified': True,
            'selection': 'explicit reviewed allowlist; unknown files excluded',
            'credential_shape_check': 'passed; heuristic, not proof of absence',
            'excluded': ['runtime', 'third_party', 'state', 'reports', 'keys', 'unknown files'],
        }
        os.replace(tmp_name, target)
        tmp_name = None
        target.with_suffix(target.suffix + '.sha256').write_text(sha + '  ' + target.name + '\n', encoding='ascii')
        target.with_suffix(target.suffix + '.checks.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        return report
    finally:
        if tmp_name is not None:
            tmp_name.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('target', nargs='?', type=Path,
                        default=ROOT.parent / 'dist' / ('LocalFolderBridge-' + __version__ + '.zip'))
    args = parser.parse_args()
    try:
        print(json.dumps(build_archive(args.target), indent=2))
    except (ValueError, OSError) as exc:
        print('Packaging refused: ' + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
