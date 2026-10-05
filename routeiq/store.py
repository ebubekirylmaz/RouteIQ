import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone

from routeiq.timeutil import BUCKET_STEPS, as_utc, floor_to_bucket

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

INDEXES = {
    "idx_requests_review_status": "review_status",
    "idx_requests_delivery_status": "delivery_status",
    "idx_requests_action": "action",
    "idx_requests_tier": "tier",
}

def _now():
    return datetime.now(timezone.utc).isoformat()

def _escape_like(text):
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

def _cutoff(moment):
    return as_utc(moment).isoformat()


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
        for name, column in INDEXES.items():
            conn.execute(f"CREATE INDEX IF NOT EXISTS {name} ON requests({column})")

    def mark_delivery(self, request_id, status, error=None):
        now = _now()
        delivered_at = now if status == "sent" else None
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "UPDATE requests SET delivery_status = ?, delivery_error = ?,"
                " delivered_at = ?, delivery_updated_at = ? WHERE id = ?",
                (status, error, delivered_at, now, request_id),
            )

    def retryable_deliveries(self, limit=100, stale_seconds=300, since=None):
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=stale_seconds)).isoformat()
        sql = (
            "SELECT id FROM requests WHERE (delivery_status = 'failed'"
            " OR (delivery_status = 'pending'"
            "     AND (delivery_updated_at IS NULL OR delivery_updated_at < ?)))"
        )
        params = [cutoff]
        if since is not None:
            sql += " AND created_at >= ?"
            params.append(_cutoff(since))
        with closing(self._connect()) as conn:
            rows = conn.execute(sql + " ORDER BY id LIMIT ?", [*params, limit]).fetchall()
        return [r["id"] for r in rows]
    
    def timeseries(self, bucket, since, until):
        """Buckets from the start of the bucket containing `since` up to `until` (exclusive).

        Buckets without requests are returned with zeros, so charts get a continuous axis.
        """
        length = 13 if bucket == "hour" else 10  # 'YYYY-MM-DDTHH' or 'YYYY-MM-DD'
        step = BUCKET_STEPS[bucket]
        start = floor_to_bucket(since, bucket)
        end = as_utc(until)
        with closing(self._connect()) as conn:
            rows = conn.execute(
                f"SELECT substr(created_at, 1, {length}) AS b, COUNT(*),"
                " COALESCE(SUM(action = 'accepted'), 0), COALESCE(SUM(action = 'human_review'), 0),"
                " COALESCE(SUM(cost_usd), 0), COALESCE(AVG(latency_ms), 0)"
                " FROM requests WHERE created_at >= ? AND created_at < ?"
                " GROUP BY b ORDER BY b",
                (_cutoff(start), _cutoff(end)),
            ).fetchall()
        found = {row[0]: row[1:] for row in rows}

        points = []
        moment = start
        while moment < end:
            key = moment.isoformat()[:length]
            count, accepted, review, cost, latency = found.get(key, (0, 0, 0, 0.0, 0.0))
            points.append({"start": moment, "requests": count, "accepted": accepted,
                           "human_review": review, "cost_usd": cost, "avg_latency_ms": latency})
            moment += step
        return points
    
    def stats(self, since=None):
        window = "created_at >= ?"
        params = [_cutoff(since)] if since is not None else []

        def where(*conditions):
            parts = ([window] if since is not None else []) + list(conditions)
            return (" WHERE " + " AND ".join(parts)) if parts else ""

        agreed_where = where("review_status = 'resolved'", "label = final_label")
        with closing(self._connect()) as conn:
            total, cost, avg_latency = conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(cost_usd), 0), COALESCE(AVG(latency_ms), 0)"
                f" FROM requests{where()}", params,
            ).fetchone()
            by_tier = self._counts(conn, "tier", where("action = 'accepted'"), params)
            actions = self._counts(conn, "action", where(), params)
            review = self._counts(conn, "review_status", where("review_status IS NOT NULL"), params)
            delivery = self._counts(conn, "delivery_status", where("delivery_status IS NOT NULL"), params)
            degraded = conn.execute(
                f"SELECT COUNT(*) FROM requests{where('error IS NOT NULL')}", params
            ).fetchone()[0]
            agreed = conn.execute(f"SELECT COUNT(*) FROM requests{agreed_where}", params).fetchone()[0]
            latencies = [r[0] for r in conn.execute(
                f"SELECT latency_ms FROM requests{where('latency_ms IS NOT NULL')} ORDER BY latency_ms",
                params,
            )]
        p95 = latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))] if latencies else 0.0
        resolved = review.get("resolved", 0)
        return {
            "requests": total,
            "accepted_by_tier": by_tier,
            "human_review": actions.get("human_review", 0),
            "review": {"pending": review.get("pending", 0), "resolved": resolved},
            "reviewer_agreement": {
                "resolved": resolved,
                "agreed": agreed,
                "rate": (agreed / resolved) if resolved else None,
            },
            "degraded": degraded,
            "cost_usd": cost,
            "latency_ms": {"avg": avg_latency, "p95": p95},
            "delivery": {
                "pending": delivery.get("pending", 0),
                "sent": delivery.get("sent", 0),
                "failed": delivery.get("failed", 0),
                "retryable": len(self.retryable_deliveries(limit=1_000_000, since=since)),
            },
        }

    @staticmethod
    def _counts(conn, column, where_clause, params):
        rows = conn.execute(
            f"SELECT {column}, COUNT(*) FROM requests{where_clause} GROUP BY {column}", params
        ).fetchall()
        return {row[0]: row[1] for row in rows}