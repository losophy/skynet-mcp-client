"""SQLite 持久化：sessions / messages / calls（WAL 模式，线程安全）。"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id         TEXT PRIMARY KEY,
    title      TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role       TEXT NOT NULL,
    content    TEXT DEFAULT '',
    ts         TEXT NOT NULL,
    meta       TEXT DEFAULT '{}'          -- JSON：render/pending 等
);
CREATE TABLE IF NOT EXISTS calls (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id    TEXT,
    ts            TEXT NOT NULL,
    tool          TEXT NOT NULL,
    params        TEXT NOT NULL,          -- JSON
    result        TEXT,                   -- JSON {ok, text, render?}
    ok            INTEGER,
    danger_level  TEXT NOT NULL,          -- safe|medium|high
    confirm_required INTEGER DEFAULT 0,
    confirmed     TEXT,                   -- approve|reject|NULL
    status        TEXT NOT NULL,          -- pending|ok|error|rejected
    duration_ms   INTEGER,
    source        TEXT DEFAULT 'agent',   -- agent|poll|replay|manual
    error         TEXT
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_calls_session ON calls(session_id);
CREATE INDEX IF NOT EXISTS idx_calls_ts ON calls(ts);
CREATE INDEX IF NOT EXISTS idx_calls_tool ON calls(tool);
CREATE INDEX IF NOT EXISTS idx_calls_danger ON calls(ts, tool, danger_level);
"""


class Database:
    """sqlite3 封装（WAL + busy_timeout；FastAPI 线程池同步调用）。"""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    @staticmethod
    def now() -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())

    # -- sessions -----------------------------------------------------------

    def create_session(self, session_id: str, title: str = "") -> None:
        now = self.now()
        self._conn.execute(
            "INSERT OR IGNORE INTO sessions(id, title, created_at, updated_at) VALUES (?,?,?,?)",
            (session_id, title, now, now),
        )
        self._conn.commit()

    def list_sessions(self, limit: int = 100) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM sessions ORDER BY updated_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_session(self, session_id: str) -> dict | None:
        r = self._conn.execute(
            "SELECT * FROM sessions WHERE id=?", (session_id,)
        ).fetchone()
        return dict(r) if r else None

    def touch_session(self, session_id: str) -> None:
        self._conn.execute(
            "UPDATE sessions SET updated_at=? WHERE id=?", (self.now(), session_id)
        )
        self._conn.commit()

    def delete_session(self, session_id: str) -> None:
        self._conn.execute("DELETE FROM messages WHERE session_id=?", (session_id,))
        self._conn.execute("DELETE FROM calls WHERE session_id=?", (session_id,))
        self._conn.execute("DELETE FROM sessions WHERE id=?", (session_id,))
        self._conn.commit()

    # -- messages -----------------------------------------------------------

    def add_message(
        self, session_id: str, role: str, content: str, meta: dict | None = None
    ) -> int:
        cur = self._conn.execute(
            "INSERT INTO messages(session_id, role, content, ts, meta) VALUES (?,?,?,?,?)",
            (
                session_id,
                role,
                content,
                self.now(),
                json.dumps(meta or {}, ensure_ascii=False),
            ),
        )
        self._conn.commit()
        self.touch_session(session_id)
        return cur.lastrowid

    def list_messages(self, session_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM messages WHERE session_id=? ORDER BY id", (session_id,)
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["meta"] = json.loads(d.get("meta") or "{}")
            out.append(d)
        return out

    # -- calls（工具调用审计） ------------------------------------------------

    def add_call(
        self,
        *,
        session_id: str | None,
        tool: str,
        params: dict,
        danger_level: str,
        confirm_required: int = 0,
        source: str = "agent",
        status: str = "pending",
    ) -> int:
        cur = self._conn.execute(
            "INSERT INTO calls(session_id, ts, tool, params, danger_level, confirm_required, status, source)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (
                session_id,
                self.now(),
                tool,
                json.dumps(params, ensure_ascii=False),
                danger_level,
                confirm_required,
                status,
                source,
            ),
        )
        self._conn.commit()
        return cur.lastrowid

    def update_call(
        self,
        call_id: int,
        *,
        result: dict | None = None,
        ok: bool | None = None,
        confirmed: str | None = None,
        status: str | None = None,
        duration_ms: int | None = None,
        error: str | None = None,
    ) -> None:
        sets, args = [], []
        if result is not None:
            sets.append("result=?")
            args.append(json.dumps(result, ensure_ascii=False))
        if ok is not None:
            sets.append("ok=?")
            args.append(int(ok))
        if confirmed is not None:
            sets.append("confirmed=?")
            args.append(confirmed)
        if status is not None:
            sets.append("status=?")
            args.append(status)
        if duration_ms is not None:
            sets.append("duration_ms=?")
            args.append(duration_ms)
        if error is not None:
            sets.append("error=?")
            args.append(error)
        if not sets:
            return
        args.append(call_id)
        self._conn.execute(f"UPDATE calls SET {', '.join(sets)} WHERE id=?", args)
        self._conn.commit()

    def list_calls(
        self,
        *,
        session_id: str | None = None,
        tool: str | None = None,
        danger: str | None = None,
        status: str | None = None,
        source: str | None = None,
        limit: int = 200,
    ) -> list[dict]:
        sql = "SELECT * FROM calls WHERE 1=1"
        args: list = []
        if session_id:
            sql += " AND session_id=?"
            args.append(session_id)
        if tool:
            sql += " AND tool=?"
            args.append(tool)
        if danger:
            sql += " AND danger_level=?"
            args.append(danger)
        if status:
            sql += " AND status=?"
            args.append(status)
        if source:
            sql += " AND source=?"
            args.append(source)
        sql += " ORDER BY id DESC LIMIT ?"
        args.append(limit)
        rows = self._conn.execute(sql, args).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["params"] = json.loads(d.get("params") or "{}")
            d["result"] = json.loads(d.get("result") or "null")
            out.append(d)
        return out
