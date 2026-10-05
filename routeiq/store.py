from email.mime import text
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone

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

NEW_COLUMNS = {
    "delivery_status": "TEXT",
    "delivery_error": "TEXT",
    "delivered_at": "TEXT",
    "delivery_updated_at": "TEXT",
}

def _now():
    return datetime.now(timezone.utc).isoformat()

def _escape_like(text):
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
class Store:
    FILTER_COLUMNS = ("action", "tier", "review_status", "delivery_status")

    def __init__(self, path):
        self.path = str(path)
        with closing(self._connect()) as conn, conn:
            conn.execute(SCHEMA)
            self._migrate(conn)

    def list_requests(self, *, action=None, tier=None, review_status=None,
                      delivery_status=None, degraded=None, q=None,
                      limit=50, offset=0, newest_first=True):
        values = {"action": action, "tier": tier,
                  "review_status": review_status, "delivery_status": delivery_status}
        where, params = [], []
        for column in self.FILTER_COLUMNS:
            if values[column] is not None:
                where.append(f"{column} = ?")
                params.append(values[column])
        if degraded is not None:
            where.append("error IS NOT NULL" if degraded else "error IS NULL")
        if q:
            where.append("text LIKE ? ESCAPE '\\'")
            params.append(f"%{_escape_like(q)}%")
        clause = (" WHERE " + " AND ".join(where)) if where else ""
        order = "DESC" if newest_first else "ASC"
        with closing(self._connect()) as conn:
            total = conn.execute(f"SELECT COUNT(*) FROM requests{clause}", params).fetchone()[0]
            rows = conn.execute(
                f"SELECT * FROM requests{clause} ORDER BY id {order} LIMIT ? OFFSET ?",
                [*params, limit, offset],
            ).fetchall()
        return [dict(r) for r in rows], total

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

    def pending(self, limit=50, offset=0):
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT id, created_at, text, label AS suggested_label, confidence, tier"
                " FROM requests WHERE review_status = 'pending' ORDER BY id LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [dict(r) for r in rows]

    def pending_count(self):
        with closing(self._connect()) as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM requests WHERE review_status = 'pending'"
            ).fetchone()[0]

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
        
    def _migrate(self, conn):
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(requests)")}
        for name, sql_type in NEW_COLUMNS.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE requests ADD COLUMN {name} {sql_type}")

    def mark_delivery(self, request_id, status, error=None):
        now = _now()
        delivered_at = now if status == "sent" else None
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "UPDATE requests SET delivery_status = ?, delivery_error = ?,"
                " delivered_at = ?, delivery_updated_at = ? WHERE id = ?",
                (status, error, delivered_at, now, request_id),
            )

    def retryable_deliveries(self, limit=100, stale_seconds=300):
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=stale_seconds)).isoformat()
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT id FROM requests WHERE delivery_status = 'failed'"
                " OR (delivery_status = 'pending'"
                "     AND (delivery_updated_at IS NULL OR delivery_updated_at < ?))"
                " ORDER BY id LIMIT ?",
                (cutoff, limit),
            ).fetchall()
        return [r["id"] for r in rows]
    
    def stats(self):
        with closing(self._connect()) as conn:
            total, cost, avg_latency = conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(cost_usd), 0), COALESCE(AVG(latency_ms), 0)"
                " FROM requests"
            ).fetchone()
            by_tier = self._counts(conn, "tier", "action = 'accepted'")
            actions = self._counts(conn, "action")
            review = self._counts(conn, "review_status", "review_status IS NOT NULL")
            delivery = self._counts(conn, "delivery_status", "delivery_status IS NOT NULL")
            degraded = conn.execute(
                "SELECT COUNT(*) FROM requests WHERE error IS NOT NULL"
            ).fetchone()[0]
            latencies = [r[0] for r in conn.execute(
                "SELECT latency_ms FROM requests WHERE latency_ms IS NOT NULL ORDER BY latency_ms"
            )]
        p95 = latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))] if latencies else 0.0
        return {
            "requests": total,
            "accepted_by_tier": by_tier,
            "human_review": actions.get("human_review", 0),
            "review": {"pending": review.get("pending", 0), "resolved": review.get("resolved", 0)},
            "degraded": degraded,
            "cost_usd": cost,
            "latency_ms": {"avg": avg_latency, "p95": p95},
            "delivery": {
                "pending": delivery.get("pending", 0),
                "sent": delivery.get("sent", 0),
                "failed": delivery.get("failed", 0),
                "retryable": len(self.retryable_deliveries(limit=1_000_000)),
            },
        }

    @staticmethod
    def _counts(conn, column, where="1 = 1"):
        rows = conn.execute(
            f"SELECT {column}, COUNT(*) FROM requests WHERE {where} GROUP BY {column}"
        ).fetchall()
        return {row[0]: row[1] for row in rows}