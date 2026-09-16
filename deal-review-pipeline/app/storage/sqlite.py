from __future__ import annotations
import sqlite3, json
from pathlib import Path
from datetime import datetime, timezone

class SQLiteStore:
    def __init__(self,path='data/deal_review.sqlite3'):
        Path(path).parent.mkdir(parents=True,exist_ok=True); self.path=path
        with sqlite3.connect(path) as c:
            c.execute('''CREATE TABLE IF NOT EXISTS reviews(document_id TEXT PRIMARY KEY, status TEXT, started_at TEXT, completed_at TEXT, risk_score INTEGER, policy_id TEXT, policy_version TEXT, report_json TEXT, report_pdf TEXT)''')
    def upsert(self, document_id, **kw):
        cols=['document_id']+list(kw); vals=[document_id]+list(kw.values())
        sql=f"INSERT OR REPLACE INTO reviews ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})"
        with sqlite3.connect(self.path) as c: c.execute(sql,vals)
