"""Isolated fixture directories outside Windows AppData (which the app forbids).
Only a newly created temporary child is removed; no existing user directory is read.
"""
from __future__ import annotations
import os
from pathlib import Path
import tempfile


def isolated_directory(prefix='lfb-test-'):
    if os.name!='nt':
        return tempfile.TemporaryDirectory(prefix=prefix)
    # Windows' default TEMP is inside AppData. Using it as an authorized root
    # would correctly fail the production path policy, not test our file engine.
    parent=Path(os.environ.get('LFB_TEST_PARENT',str(Path.home()/'LocalFolderBridge-TestRuns')))
    parent.mkdir(parents=True,exist_ok=True)
    return tempfile.TemporaryDirectory(prefix=prefix,dir=str(parent))
