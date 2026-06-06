import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "db", "inventory.db")

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # rows behave like dicts
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

# ── Substance lookups ────────────────────────────────────────────

def get_substance(rfid_tag_id: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM substances WHERE rfid_tag_id = ?", (rfid_tag_id,)
        ).fetchone()
        return dict(row) if row else None

def get_all_substances() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM substances ORDER BY substance_name").fetchall()
        return [dict(r) for r in rows]

def update_substance_state(rfid_tag_id: str, state: str):
    assert state in ("ON_SHELF", "IN_USE")
    with get_conn() as conn:
        conn.execute(
            "UPDATE substances SET state = ? WHERE rfid_tag_id = ?",
            (state, rfid_tag_id)
        )

# ── Sessions ─────────────────────────────────────────────────────

def open_session(rfid_tag_id: str) -> int:
    """Called on TAKEN. Returns new session id."""
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO sessions (rfid_tag_id, taken_at) VALUES (?, ?)",
            (rfid_tag_id, datetime.now().isoformat())
        )
        return cur.lastrowid

def close_session(rfid_tag_id: str) -> dict | None:
    """Called on RETURNED. Closes the most recent open session. Returns session dict."""
    with get_conn() as conn:
        row = conn.execute("""
            SELECT * FROM sessions
            WHERE rfid_tag_id = ? AND returned_at IS NULL
            ORDER BY taken_at DESC LIMIT 1
        """, (rfid_tag_id,)).fetchone()

        if not row:
            return None

        returned_at = datetime.now().isoformat()
        taken_dt = datetime.fromisoformat(row["taken_at"])
        returned_dt = datetime.fromisoformat(returned_at)
        duration_s = (returned_dt - taken_dt).total_seconds()

        conn.execute("""
            UPDATE sessions
            SET returned_at = ?, session_duration_s = ?
            WHERE id = ?
        """, (returned_at, duration_s, row["id"]))

        return {"id": row["id"], "rfid_tag_id": rfid_tag_id,
                "taken_at": row["taken_at"], "returned_at": returned_at,
                "session_duration_s": duration_s}

def get_open_session(rfid_tag_id: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("""
            SELECT * FROM sessions
            WHERE rfid_tag_id = ? AND returned_at IS NULL
            ORDER BY taken_at DESC LIMIT 1
        """, (rfid_tag_id,)).fetchone()
        return dict(row) if row else None

def get_last_session(rfid_tag_id: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("""
            SELECT * FROM sessions
            WHERE rfid_tag_id = ?
            ORDER BY taken_at DESC LIMIT 1
        """, (rfid_tag_id,)).fetchone()
        return dict(row) if row else None

def get_avg_session_duration(rfid_tag_id: str) -> float:
    with get_conn() as conn:
        row = conn.execute("""
            SELECT AVG(session_duration_s) as avg_duration 
            FROM sessions 
            WHERE rfid_tag_id = ? AND session_duration_s IS NOT NULL
        """, (rfid_tag_id,)).fetchone()
        return row["avg_duration"] if row and row["avg_duration"] else 0.0

def get_sessions_per_day(rfid_tag_id: str) -> float:
    with get_conn() as conn:
        row = conn.execute("""
            SELECT MIN(taken_at) as first_taken, COUNT(*) as count 
            FROM sessions 
            WHERE rfid_tag_id = ?
        """, (rfid_tag_id,)).fetchone()
        
        if not row or not row["first_taken"] or row["count"] == 0:
            return 1.0 # default to 1 session per day
            
        first_taken_dt = datetime.fromisoformat(row["first_taken"])
        days_since_first = (datetime.now() - first_taken_dt).total_seconds() / (24 * 3600)
        
        # Avoid division by zero and cap to max 1 day if it's less than a day
        days_since_first = max(1.0, days_since_first)
        
        return row["count"] / days_since_first

# ── Quantity estimates ────────────────────────────────────────────

def get_latest_estimate(rfid_tag_id: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("""
            SELECT * FROM quantity_estimates
            WHERE rfid_tag_id = ?
            ORDER BY recorded_at DESC LIMIT 1
        """, (rfid_tag_id,)).fetchone()
        return dict(row) if row else None

def save_estimate(rfid_tag_id: str, session_id: int,
                  estimated_remaining: float, consumption_rate: float) -> int:
    with get_conn() as conn:
        cur = conn.execute("""
            INSERT INTO quantity_estimates
                (rfid_tag_id, session_id, estimated_remaining, consumption_rate)
            VALUES (?, ?, ?, ?)
        """, (rfid_tag_id, session_id, estimated_remaining, consumption_rate))
        return cur.lastrowid

def save_feedback(session_id: int, feedback: str):
    assert feedback in ("YES", "NO")
    with get_conn() as conn:
        conn.execute(
            "UPDATE quantity_estimates SET feedback = ? WHERE session_id = ?",
            (feedback, session_id)
        )

def save_micro_feedback(rfid_tag_id: str, session_id: int, enough_for_next: bool, estimated_qty: float):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO quantity_feedback
                (rfid_tag_id, session_id, enough_for_next, estimated_qty_at_feedback)
            VALUES (?, ?, ?, ?)
        """, (rfid_tag_id, session_id, enough_for_next, estimated_qty))

# ── Consumption rates ─────────────────────────────────────────────

def get_rate(rfid_tag_id: str) -> tuple[float, int, float]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT rate_per_usage, n_sessions, rate_variance FROM consumption_rates WHERE rfid_tag_id = ?",
            (rfid_tag_id,)
        ).fetchone()
        return (row["rate_per_usage"], row["n_sessions"], row["rate_variance"]) if row else (0.5, 0, 100.0)

def update_rate(rfid_tag_id: str, new_rate: float, n_sessions: int, rate_variance: float = 100.0):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO consumption_rates (rfid_tag_id, rate_per_usage, n_sessions, rate_variance, last_updated)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(rfid_tag_id) DO UPDATE SET
                rate_per_usage = excluded.rate_per_usage,
                n_sessions = excluded.n_sessions,
                rate_variance = excluded.rate_variance,
                last_updated = excluded.last_updated
        """, (rfid_tag_id, new_rate, n_sessions, rate_variance, datetime.now().isoformat()))

# ── Alerts ────────────────────────────────────────────────────────

def create_alert(rfid_tag_id: str, alert_type: str, message: str):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO alerts (rfid_tag_id, alert_type, message)
            VALUES (?, ?, ?)
        """, (rfid_tag_id, alert_type, message))

def get_open_alerts() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM alerts WHERE resolved = 0 ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

# ── Hardware Pending Scans ────────────────────────────────────────

def add_pending_scan(tag_id: str):
    with get_conn() as conn:
        conn.execute("INSERT INTO pending_scans (tag_id) VALUES (?)", (tag_id,))

def get_and_clear_pending_scans() -> list[str]:
    with get_conn() as conn:
        rows = conn.execute("SELECT id, tag_id FROM pending_scans ORDER BY timestamp ASC").fetchall()
        if not rows:
            return []
        
        ids = [str(r["id"]) for r in rows]
        conn.execute(f"DELETE FROM pending_scans WHERE id IN ({','.join(ids)})")
        return [r["tag_id"] for r in rows]