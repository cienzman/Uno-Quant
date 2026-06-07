import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "db", "inventory.db")

def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
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



# ── Quantity Updates ──────────────────────────────────────────────

def update_substance_quantity(rfid_tag_id: str, quantity_level: str):
    assert quantity_level in ("A LOT", "MEDIUM", "LOW", "UNKNOWN")
    with get_conn() as conn:
        conn.execute(
            "UPDATE substances SET quantity_level = ? WHERE rfid_tag_id = ?",
            (quantity_level, rfid_tag_id)
        )

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