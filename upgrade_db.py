import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "db", "inventory.db")

def upgrade_database():
    if not os.path.exists(DB_PATH):
        print(f"Database not found at {DB_PATH}. Please run setup_db.py first.")
        return

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    try:
        # Phase 1: Add rate_variance to consumption_rates if it doesn't exist
        print("Checking consumption_rates table...")
        c.execute("PRAGMA table_info(consumption_rates)")
        columns = [col[1] for col in c.fetchall()]
        if "rate_variance" not in columns:
            print("Adding 'rate_variance' column to 'consumption_rates'...")
            c.execute("ALTER TABLE consumption_rates ADD COLUMN rate_variance REAL DEFAULT 100.0")
        else:
            print("'rate_variance' column already exists.")

        # Phase 2: Create quantity_feedback table
        print("Ensuring 'quantity_feedback' table exists...")
        c.execute("""
            CREATE TABLE IF NOT EXISTS quantity_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rfid_tag_id TEXT NOT NULL,
                session_id INTEGER NOT NULL,
                enough_for_next BOOLEAN NOT NULL,
                estimated_qty_at_feedback REAL NOT NULL,
                timestamp TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (rfid_tag_id) REFERENCES substances(rfid_tag_id),
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            )
        """)

        conn.commit()
        print("Database upgrade completed successfully.")
    except Exception as e:
        print(f"Error upgrading database: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    upgrade_database()
