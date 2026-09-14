"""SQLite-backed notification + message history for WebCom.

All TeamTalk notifications (PMs, channel/broadcast messages, logins, logouts,
kicks, status changes, joins/leaves, file events) are persisted here so they
can be browsed later, filtered by kind/server/direction, and marked read.

Design notes:
- The TeamTalk server re-assigns user IDs on every login, so user IDs are
  NEVER used as a stable key. We persist the human-readable "peer" label
  (e.g. "donald trump (averlice)") captured at event/send time; the userid is
  kept only in `extra` for reference while that user is online.
- SQLite is single-writer; all writes go through a module-level lock so the
  bridge threads and web threads never collide.
- The DB lives in the /data volume (WEBCOM_DATA_DIR) so history survives
  container restarts.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from pathlib import Path

DATA_DIR = Path(os.environ.get("WEBCOM_DATA_DIR", "/data"))
DB_PATH = Path(os.environ.get("WEBCOM_DB_PATH", str(DATA_DIR / "webcom.db")))

# Category a stored notification may belong to.
KINDS = (
    "pm", "channel", "broadcast", "custom",
    "login", "logout", "kick", "status",
    "joined", "left", "file", "system",
)

_lock = threading.Lock()
_local = threading.local()


def _connect() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    if conn is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        _local.conn = conn
    return conn


def init() -> None:
    """Create tables/indexes if missing. Safe to call repeatedly."""
    with _lock:
        conn = _connect()
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS notifications (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                received_at REAL NOT NULL,
                server      TEXT NOT NULL,
                kind        TEXT NOT NULL,
                direction   TEXT NOT NULL DEFAULT 'in',
                peer        TEXT NOT NULL DEFAULT '',
                text        TEXT NOT NULL DEFAULT '',
                extra       TEXT NOT NULL DEFAULT '{}',
                seen        INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_notif_ts     ON notifications(received_at);
            CREATE INDEX IF NOT EXISTS idx_notif_server ON notifications(server, received_at);
            CREATE INDEX IF NOT EXISTS idx_notif_kind   ON notifications(kind, received_at);
            CREATE INDEX IF NOT EXISTS idx_notif_seen   ON notifications(seen, received_at);
            """
        )
        conn.commit()


def insert(server: str, kind: str, text: str,
           direction: str = "in", peer: str = "", extra: dict | None = None) -> dict | None:
    """Persist one notification and return it as a dict (with its new id)."""
    if kind not in KINDS:
        kind = "system"
    row = {
        "id": None,
        "received_at": time.time(),
        "server": server or "",
        "kind": kind,
        "direction": direction if direction in ("in", "out") else "in",
        "peer": peer or "",
        "text": text or "",
        "extra": json.dumps(extra or {}),
        "seen": 0,
    }
    try:
        with _lock:
            conn = _connect()
            cur = conn.execute(
                "INSERT INTO notifications (received_at, server, kind, direction, peer, text, extra, seen)"
                " VALUES (:received_at, :server, :kind, :direction, :peer, :text, :extra, :seen)",
                row,
            )
            conn.commit()
            row["id"] = cur.lastrowid
    except Exception as exc:
        import logging
        logging.getLogger("webcom").exception("notification insert failed: %s", exc)
        return None
    return _row_to_dict(row)


def query(server: str | None = None, kind: str | None = None,
          direction: str | None = None, seen: int | None = None,
          since: float | None = None, limit: int = 200) -> list[dict]:
    """Return stored notifications newest-first, optionally filtered."""
    sql = "SELECT * FROM notifications WHERE 1=1"
    params: list = []
    if server:
        sql += " AND server = ?"
        params.append(server)
    if kind:
        sql += " AND kind = ?"
        params.append(kind)
    if direction in ("in", "out"):
        sql += " AND direction = ?"
        params.append(direction)
    if seen is not None:
        sql += " AND seen = ?"
        params.append(1 if seen else 0)
    if since:
        sql += " AND received_at >= ?"
        params.append(since)
    sql += " ORDER BY received_at DESC, id DESC LIMIT ?"
    params.append(int(limit))
    try:
        with _lock:
            conn = _connect()
            rows = conn.execute(sql, params).fetchall()
            return [_row_to_dict(dict(r)) for r in rows]
    except Exception as exc:
        import logging
        logging.getLogger("webcom").exception("notification query failed: %s", exc)
        return []


def unread_count(server: str | None = None) -> int:
    sql = "SELECT COUNT(*) AS c FROM notifications WHERE seen = 0"
    params: list = []
    if server:
        sql += " AND server = ?"
        params.append(server)
    try:
        with _lock:
            conn = _connect()
            return int(conn.execute(sql, params).fetchone()["c"])
    except Exception:
        return 0


def mark_seen(ids: list[int] | None = None, server: str | None = None) -> int:
    """Mark notifications as read. ids=None marks everything (optionally scoped)."""
    sql = "UPDATE notifications SET seen = 1 WHERE seen = 0"
    params: list = []
    if ids:
        placeholders = ",".join("?" * len(ids))
        sql += f" AND id IN ({placeholders})"
        params.extend(int(i) for i in ids)
    if server:
        sql += " AND server = ?"
        params.append(server)
    try:
        with _lock:
            conn = _connect()
            cur = conn.execute(sql, params)
            conn.commit()
            return cur.rowcount
    except Exception as exc:
        import logging
        logging.getLogger("webcom").exception("mark_seen failed: %s", exc)
        return 0


def clear(server: str | None = None, kind: str | None = None,
          direction: str | None = None) -> int:
    """Delete stored notifications, optionally scoped by server/kind/direction."""
    sql = "DELETE FROM notifications WHERE 1=1"
    params: list = []
    if server:
        sql += " AND server = ?"
        params.append(server)
    if kind:
        sql += " AND kind = ?"
        params.append(kind)
    if direction in ("in", "out"):
        sql += " AND direction = ?"
        params.append(direction)
    try:
        with _lock:
            conn = _connect()
            cur = conn.execute(sql, params)
            conn.commit()
            return cur.rowcount
    except Exception as exc:
        import logging
        logging.getLogger("webcom").exception("notification clear failed: %s", exc)
        return 0


def _row_to_dict(row: dict) -> dict:
    out = dict(row)
    try:
        out["extra"] = json.loads(out.get("extra") or "{}")
    except Exception:
        out["extra"] = {}
    out["seen"] = bool(out.get("seen"))
    out["readable_time"] = _fmt_time(out.get("received_at") or time.time())
    return out


def _fmt_time(ts: float) -> str:
    import datetime
    return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


# Ensure tables exist on import so the bridge can write immediately.
init()