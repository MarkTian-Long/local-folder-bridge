"""Repository-only documentation checks; never contacts a service or pushes Git."""
from __future__ import annotations

import json
from pathlib import Path
import posixpath
import re
import subprocess
import sys
from urllib.parse import unquote, urlsplit

from markdown_it import MarkdownIt

ROOT = Path(__file__).resolve().parents[1]
REPO_MAIN = '/MarkTian-Long/local-folder-bridge/blob/main/'


def destinations(tokens):
    for token in tokens:
        if token.type in ('link_open', 'image'):
            target = token.attrGet('src' if token.type == 'image' else 'href')
            if target:
                yield target
        if token.children:
            yield from destinations(token.children)


def check_documents(files: dict[str, str], tracked: set[str]) -> list[str]:
    """Return actionable documentation errors without modifying any files."""
    errors = []
    parser = MarkdownIt('commonmark', {'html': False}).enable('table')
    for name, source in sorted(files.items()):
        if not name.endswith('.md') or name not in tracked:
            continue
        for target in destinations(parser.parse(source)):
            url = urlsplit(target)
            if url.hostname == 'github.com' and url.path.startswith(REPO_MAIN):
                resolved = unquote(url.path[len(REPO_MAIN):])
            elif url.scheme in ('https', 'http', 'mailto') or target.startswith('//'):
                continue
            elif url.scheme or url.path.startswith('/') or '\\' in url.path:
                errors.append(f'{name}: non-portable link {target}')
                continue
            elif not url.path:  # Anchors are not checked by this file-existence gate.
                continue
            else:
                resolved = posixpath.join(posixpath.dirname(name), unquote(url.path))
            resolved = posixpath.normpath(resolved)
            if resolved == '..' or resolved.startswith(('../', '/')) or resolved not in tracked:
                errors.append(f'{name}: link target is not a tracked file: {target}')

    try:
        node_version = json.loads(files['package.json'])['version']
        python_version = re.search(
            r'^__version__ = "([0-9]+\.[0-9]+\.[0-9]+)"$',
            files['LocalFolderBridge/bridge/__init__.py'], re.M,
        ).group(1)
    except (KeyError, ValueError, AttributeError, TypeError):
        return errors + ['Cannot read the two canonical project versions.']

    requirements = {
        'README.md': rf'^版本：{re.escape(node_version)}(?:\s|$)',
        'CHANGELOG.md': rf'^## {re.escape(node_version)}(?:\s|$)',
        'PROJECT.md': rf'^\| 当前版本 \| {re.escape(python_version)} \| {re.escape(node_version)} \|$',
        'LocalFolderBridge/README.md': rf'^# .* {re.escape(python_version)}$',
        'LocalFolderBridge/CHANGELOG.md': rf'^## {re.escape(python_version)}(?:\s|$)',
        'LocalFolderBridge/docs/操作手册.md': rf'^\*\*Local Folder Bridge {re.escape(python_version)}｜',
    }
    for name, expected in requirements.items():
        if not re.search(expected, files.get(name, ''), re.M):
            errors.append(f'{name}: current version label differs from the canonical source.')
    return errors


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    try:
        result = subprocess.run(
            ['git', 'ls-files', '--cached', '-z'], cwd=ROOT,
            check=True, capture_output=True,
        )
        tracked = set(result.stdout.decode('utf-8').rstrip('\0').split('\0')) - {''}
        canonical = {'package.json', 'LocalFolderBridge/bridge/__init__.py'}
        files = {name: (ROOT / name).read_text(encoding='utf-8')
                 for name in tracked if name.endswith('.md') or name in canonical}
        errors = check_documents(files, tracked)
    except (OSError, UnicodeError, subprocess.SubprocessError, ValueError) as exc:
        print(f'Documentation check could not run: {exc}', file=sys.stderr)
        return 1
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print(f'PASS: {sum(name.endswith(".md") for name in files)} tracked Markdown files; '
          'internal file links and both version labels. No external URL/anchor validation.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
