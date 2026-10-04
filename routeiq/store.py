import sqlite3
from contextlib import closing
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    text TEXT NOT NULL,
    label TEXT,
    confidence REAL,
    tier TEXT,
    action TEXT NOT NULL,
    cost_usd REAL,
    latency_ms REAL,
    error TEXT,
    review_status TEXT,
    final_label TEXT,
    resolved_at TEXT
)
"""


def _now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path):
        self.path = str(path)
        with closing(self._connect()) as conn, conn:
            conn.execute(SCHEMA)

    def _connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def log(self, text, result):
        status = "pending" if result.action == "human_review" else None
        with closing(self._connect()) as conn, conn:
            cur = conn.execute(
                "INSERT INTO requests (created_at, text, label, confidence, tier, action,"
                " cost_usd, latency_ms, error, review_status) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    _now(), text, result.label, result.confidence, result.tier,
                    result.action, result.cost_usd, result.latency_ms, result.error,
                    status,
                ),
            )
            return cur.lastrowid

    def pending(self, limit=50):
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT id, created_at, text, label AS suggested_label, confidence, tier"
                " FROM requests WHERE review_status = 'pending' ORDER BY id LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get(self, request_id):
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT * FROM requests WHERE id = ?", (request_id,)).fetchone()
        return dict(row) if row else None

    def resolve(self, request_id, final_label):
        with closing(self._connect()) as conn, conn:
            cur = conn.execute(
                "UPDATE requests SET review_status = 'resolved', final_label = ?,"
                " resolved_at = ? WHERE id = ? AND review_status = 'pending'",
                (final_label, _now(), request_id),
            )
            return cur.rowcount == 1