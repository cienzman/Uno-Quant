import sqlite3
import os
from datetime import datetime

# Define the absolute path to the SQLite database
DB_PATH = os.path.join(os.path.dirname(__file__), "db", "inventory.db")

def get_conn():
    """
    Establish and configure a connection to the SQLite database.

    Configures the connection to enforce foreign key constraints and
    returns rows as dictionaries using sqlite3.Row for easier access.

    Returns:
        sqlite3.Connection: An active SQLite database connection object.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Ensure rows behave like dictionaries
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

# ── Substance lookups ────────────────────────────────────────────

def get_substance(rfid_tag_id: str) -> dict | None:
    """
    Retrieve a substance record by its RFID tag ID.

    Args:
        rfid_tag_id (str): The unique identifier of the RFID tag.

    Returns:
        dict | None: The substance details if found, otherwise None.
    """
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM substances WHERE rfid_tag_id = ?", (rfid_tag_id,)
        ).fetchone()
        return dict(row) if row else None

def get_all_substances() -> list[dict]:
    """
    Retrieve all substance records from the inventory, ordered alphabetically.

    Returns:
        list[dict]: A list containing dictionaries for all registered substances.
    """
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM substances ORDER BY substance_name").fetchall()
        return [dict(r) for r in rows]

def update_substance_state(rfid_tag_id: str, state: str):
    """
    Update the physical state of a substance (e.g., 'ON_SHELF' or 'IN_USE').

    Args:
        rfid_tag_id (str): The unique identifier of the RFID tag.
        state (str): The new state to apply. Must be "ON_SHELF" or "IN_USE".
    """
    assert state in ("ON_SHELF", "IN_USE"), f"Invalid state provided: {state}"
    with get_conn() as conn:
        conn.execute(
            "UPDATE substances SET state = ? WHERE rfid_tag_id = ?",
            (state, rfid_tag_id)
        )

# ── Sessions ─────────────────────────────────────────────────────

def open_session(rfid_tag_id: str) -> int:
    """
    Open a new usage session when a substance is taken from the shelf.

    Args:
        rfid_tag_id (str): The unique identifier of the RFID tag.

    Returns:
        int: The primary key ID of the newly created session record.
    """
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO sessions (rfid_tag_id, taken_at) VALUES (?, ?)",
            (rfid_tag_id, datetime.now().isoformat())
        )
        return cur.lastrowid

def close_session(rfid_tag_id: str) -> dict | None:
    """
    Close the most recent open session when a substance is returned.
    
    Computes and records the total duration the item was checked out.

    Args:
        rfid_tag_id (str): The unique identifier of the RFID tag.

    Returns:
        dict | None: The finalized session details including duration, or None if no open session exists.
    """
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
    """
    Retrieve the currently open session for a specific substance, if any.

    Args:
        rfid_tag_id (str): The unique identifier of the RFID tag.

    Returns:
        dict | None: The active session details, or None if it is currently on the shelf.
    """
    with get_conn() as conn:
        row = conn.execute("""
            SELECT * FROM sessions
            WHERE rfid_tag_id = ? AND returned_at IS NULL
            ORDER BY taken_at DESC LIMIT 1
        """, (rfid_tag_id,)).fetchone()
        return dict(row) if row else None

def get_last_session(rfid_tag_id: str) -> dict | None:
    """
    Retrieve the most recently recorded session for a given substance, regardless of status.

    Args:
        rfid_tag_id (str): The unique identifier of the RFID tag.

    Returns:
        dict | None: The most recent session details, or None if the item has no history.
    """
    with get_conn() as conn:
        row = conn.execute("""
            SELECT * FROM sessions
            WHERE rfid_tag_id = ?
            ORDER BY taken_at DESC LIMIT 1
        """, (rfid_tag_id,)).fetchone()
        return dict(row) if row else None

# ── Quantity Updates ──────────────────────────────────────────────

def update_substance_quantity(rfid_tag_id: str, quantity_level: str, is_ai_prediction: bool = False):
    """
    Update the remaining quantity level of a substance in the inventory.

    Args:
        rfid_tag_id (str): The unique identifier of the RFID tag.
        quantity_level (str): The new quantity indicator. Must be one of: "A LOT", "MEDIUM", "LITTLE", "UNKNOWN".
        is_ai_prediction (bool, optional): Flag indicating whether the update stems from an AI model 
            prediction. If False, the update is logged as a ground-truth user feedback event. Defaults to False.
    """
    assert quantity_level in ("A LOT", "MEDIUM", "LITTLE", "UNKNOWN")
    with get_conn() as conn:
        conn.execute(
            "UPDATE substances SET quantity_level = ? WHERE rfid_tag_id = ?",
            (quantity_level, rfid_tag_id)
        )
        if not is_ai_prediction and quantity_level != "UNKNOWN":
            conn.execute(
                "INSERT INTO feedback_logs (rfid_tag_id, quantity_level) VALUES (?, ?)",
                (rfid_tag_id, quantity_level)
            )

# ── Alerts ────────────────────────────────────────────────────────

def create_alert(rfid_tag_id: str, alert_type: str, message: str):
    """
    Create and record a new system alert for a specific substance.

    Args:
        rfid_tag_id (str): The associated RFID tag ID.
        alert_type (str): Categorical type of the alert (e.g., 'EXPIRING_SOON').
        message (str): Descriptive text outlining the alert condition.
    """
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO alerts (rfid_tag_id, alert_type, message)
            VALUES (?, ?, ?)
        """, (rfid_tag_id, alert_type, message))

def get_open_alerts() -> list[dict]:
    """
    Retrieve all unresolved system alerts, ordered by creation date descending.

    Returns:
        list[dict]: A list of active alert dictionaries.
    """
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM alerts WHERE resolved = 0 ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

# ── Hardware Pending Scans ────────────────────────────────────────

def add_pending_scan(tag_id: str):
    """
    Queue an incoming hardware RFID scan event for processing by the frontend.

    Args:
        tag_id (str): The scanned RFID tag identifier.
    """
    with get_conn() as conn:
        conn.execute("INSERT INTO pending_scans (tag_id) VALUES (?)", (tag_id,))

def get_and_clear_pending_scans() -> list[str]:
    """
    Atomically retrieve and delete all pending hardware RFID scan events.

    Returns:
        list[str]: A list of RFID tag IDs that require processing.
    """
    with get_conn() as conn:
        rows = conn.execute("SELECT id, tag_id FROM pending_scans ORDER BY timestamp ASC").fetchall()
        if not rows:
            return []
        
        ids = [str(r["id"]) for r in rows]
        conn.execute(f"DELETE FROM pending_scans WHERE id IN ({','.join(ids)})")
        return [r["tag_id"] for r in rows]

# ── ML Feedback Tracker ───────────────────────────────────────────

def get_feedback_count() -> int:
    """
    Fetch the total number of manual micro-feedback responses logged in the system.

    Returns:
        int: The aggregate count of user feedback entries.
    """
    with get_conn() as conn:
        row = conn.execute("SELECT COUNT(*) as count FROM feedback_logs").fetchone()
        return row["count"] if row else 0

def clear_feedbacks():
    """
    Purge all existing manual feedback records from the database.
    Typically used to reset training data states or during system maintenance.
    """
    with get_conn() as conn:
        conn.execute("DELETE FROM feedback_logs")