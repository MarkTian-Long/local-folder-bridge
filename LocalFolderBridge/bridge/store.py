"""Local-only settings and durable approval/audit records. Never a remote config API."""
from __future__ import annotations
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sqlite3
import time

class Store:
    def __init__(self, directory: Path):
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)
        if os.name != 'nt': directory.chmod(0o700)
        self.path = directory / 'state.sqlite3'
        with self.db() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS roots (id TEXT PRIMARY KEY, alias TEXT NOT NULL, path TEXT NOT NULL UNIQUE, identity TEXT NOT NULL, writable INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS operations (id TEXT PRIMARY KEY, created REAL NOT NULL, expires REAL NOT NULL, status TEXT NOT NULL, kind TEXT NOT NULL, root_id TEXT NOT NULL, args TEXT NOT NULL, snapshot TEXT NOT NULL, reason TEXT NOT NULL, request_key TEXT NOT NULL, result TEXT);
                CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY AUTOINCREMENT, at REAL NOT NULL, origin TEXT NOT NULL, action TEXT NOT NULL, root_id TEXT, path TEXT, status TEXT NOT NULL, code TEXT);
            ''')
        if os.name != 'nt': self.path.chmod(0o600)

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('PRAGMA busy_timeout=15000')
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback(); raise
        finally:
            db.close()

    def get(self, key: str, default=None):
        with self.db() as db:
            r = db.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
        return json.loads(r[0]) if r else default

    def set(self, key: str, value):
        with self.db() as db:
            db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)', (key, json.dumps(value, ensure_ascii=False)))

    def roots(self) -> list[dict]:
        with self.db() as db:
            return [dict(r) for r in db.execute('SELECT * FROM roots ORDER BY rowid')]

    def log(self, origin: str, action: str, root_id='', path='', status='ok', code=''):
        # Deliberately no file body, query text, raw RPC or credentials.
        with self.db() as db:
            db.execute('INSERT INTO audit(at,origin,action,root_id,path,status,code) VALUES (?,?,?,?,?,?,?)',
                       (time.time(), origin, action, root_id, path[:1500], status, code))
            db.execute('DELETE FROM audit WHERE id < (SELECT COALESCE(MAX(id),0)-5000 FROM audit)')

    def audit(self, limit=80):
        with self.db() as db:
            return [dict(r) for r in db.execute('SELECT * FROM audit ORDER BY id DESC LIMIT ?', (min(limit, 500),))]

    def expire(self):
        with self.db() as db:
            db.execute("UPDATE operations SET status='expired', args=json_remove(args,'$.content') WHERE status='pending' AND expires < ?", (time.time(),))

    def recover_interrupted(self):
        # Never replay an operation after a crash: its effects require human inspection.
        with self.db() as db:
            db.execute("UPDATE operations SET status='interrupted',args=json_remove(args,'$.content'), result=? WHERE status='executing'", (json.dumps({'executed':False,'state_unknown':True,'message':'执行期间程序中断；请检查目标文件和备份，不会自动重试。'},ensure_ascii=False),))

    def cancel_pending(self, root_id: str | None = None):
        with self.db() as db:
            where, params = ("AND root_id=?", (root_id,)) if root_id else ('', ())
            db.execute("UPDATE operations SET status='cancelled', args=json_remove(args,'$.content') WHERE status='pending' " + where, params)

    def operations(self, limit=80):
        self.expire()
        with self.db() as db:
            rows = [dict(r) for r in db.execute('SELECT * FROM operations ORDER BY created DESC LIMIT ?', (limit,))]
        for r in rows:
            for k in ('args','snapshot','result'):
                r[k] = json.loads(r[k]) if r[k] else None
        return rows
