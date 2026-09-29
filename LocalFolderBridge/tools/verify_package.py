#!/usr/bin/env python3
"""Verify release bytes, not authenticity or absence of malware."""
from __future__ import annotations

import hashlib
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import package


def verify(root: Path) -> int:
    manifest = package.checked_file(root, 'MANIFEST.sha256')
    entries = {}
    for line in manifest.read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        match = re.fullmatch(r'([0-9a-f]{64})  (.+)', line)
        if not match:
            raise ValueError('Malformed manifest entry')
        digest, name = match.groups()
        package.safe_relative(name)
        if name.casefold() in {p.casefold() for p in entries}:
            raise ValueError('Duplicate manifest entry')
        entries[name] = digest
    if set(entries) != set(package.SHARE_FILES):
        raise ValueError('Manifest does not match the reviewed distribution file list')
    for name, digest in entries.items():
        path = package.checked_file(root, name)
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError('SHA-256 differs: ' + name)
    return len(entries)


def main():
    try:
        count = verify(ROOT)
    except (OSError, ValueError, UnicodeError) as exc:
        print('Verification failed: ' + str(exc), file=sys.stderr)
        print('This verifies a freshly extracted release, not an edited development tree.', file=sys.stderr)
        return 1
    print(f'PASS: {count} release files match MANIFEST.sha256. Not a malware scan or a digital signature.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
