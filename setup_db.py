# python3 setup_db.py

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "db", "inventory.db")

def create_and_populate():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # --- SUBSTANCES TABLE ---
    # Master registry: one row per physical container
    c.execute("""
        CREATE TABLE IF NOT EXISTS substances (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            rfid_tag_id         TEXT UNIQUE NOT NULL,
            substance_name      TEXT NOT NULL,
            chemical_formula    TEXT DEFAULT 'N/A',
            pubchem_url         TEXT NOT NULL,
            sigmaaldrich_url    TEXT DEFAULT '',
            initial_quantity    REAL DEFAULT NULL,       -- e.g. 500.0
            unit                TEXT DEFAULT NULL,       -- 'mL', 'g', etc.
            location            TEXT DEFAULT 'Shelf A',
            primary_hazard      TEXT DEFAULT '',
            state               TEXT DEFAULT 'ON_SHELF', -- 'ON_SHELF' | 'IN_USE'
            registered_at       TEXT DEFAULT (datetime('now'))
        )
    """)

    # --- SESSIONS TABLE ---
    # One row per TAKEN→RETURNED cycle
    c.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            rfid_tag_id         TEXT NOT NULL,
            taken_at            TEXT NOT NULL,
            returned_at         TEXT DEFAULT NULL,       -- NULL while IN_USE
            session_duration_s  REAL DEFAULT NULL,       -- seconds, filled on return
            FOREIGN KEY (rfid_tag_id) REFERENCES substances(rfid_tag_id)
        )
    """)

    # --- QUANTITY_ESTIMATES TABLE ---
    # Running quantity estimate after each session
    c.execute("""
        CREATE TABLE IF NOT EXISTS quantity_estimates (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            rfid_tag_id         TEXT NOT NULL,
            session_id          INTEGER NOT NULL,
            estimated_remaining REAL NOT NULL,           -- in substance's unit
            consumption_rate    REAL NOT NULL,           -- units per minute
            feedback            TEXT DEFAULT NULL,       -- 'YES' | 'NO' | NULL (no answer)
            recorded_at         TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (rfid_tag_id) REFERENCES substances(rfid_tag_id),
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        )
    """)

    # --- QUANTITY_FEEDBACK TABLE ---
    # Micro-feedback from user about remaining quantity
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

    # --- ALERTS TABLE ---
    c.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            rfid_tag_id         TEXT NOT NULL,
            alert_type          TEXT NOT NULL,   -- 'LOW_STOCK' | 'OVERDUE' | 'ANOMALY'
            message             TEXT,
            resolved            INTEGER DEFAULT 0,  -- 0=open, 1=resolved
            created_at          TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (rfid_tag_id) REFERENCES substances(rfid_tag_id)
        )
    """)

    # --- CONSUMPTION_RATES TABLE ---
    # Per-substance learned rate (updated over time)
    c.execute("""
        CREATE TABLE IF NOT EXISTS consumption_rates (
            rfid_tag_id         TEXT PRIMARY KEY,
            rate_per_usage      REAL NOT NULL DEFAULT 0.5,  -- units/usage, seed value
            n_sessions          INTEGER DEFAULT 0,           -- how many sessions trained on
            rate_variance       REAL DEFAULT 100.0,          -- Bayesian variance of the rate
            last_updated        TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (rfid_tag_id) REFERENCES substances(rfid_tag_id)
        )
    """)

    conn.commit()

    # --- POPULATE DEMO SUBSTANCES ---
    demo_substances = [
        ("tag1", "Sodium Chloride",          "ClNa",            "https://pubchem.ncbi.nlm.nih.gov/compound/5234",     "https://www.sigmaaldrich.com/IT/it/search/7647-14-5?focus=products&page=1&perpage=15&sort=relevance&term=7647-14-5&type=cas_number", 200.0, "g",  "Shelf A", "Corrosive"),
        ("tag2", "Phosphate Buffered Saline","Cl2H3K2Na3O8P2", "https://pubchem.ncbi.nlm.nih.gov/compound/24978514",  "https://www.sigmaaldrich.com/IT/it/search/phosphate-buffered-saline?focus=products&page=1&perpage=15&sort=relevance&term=Phosphate%20Buffered%20Saline&type=product", 1.0,   "L",  "Shelf A", ""),
        ("tag3", "Cholesterol",              "C27H46O",         "https://pubchem.ncbi.nlm.nih.gov/compound/5997",      "https://www.sigmaaldrich.com/IT/it/search/57-88-5?focus=products&page=1&perpage=15&sort=relevance&term=57-88-5&type=cas_number", 1.0,   "g",  "Shelf A", ""),
        ("tag4", "Acetylamino",              "C28H44N2O23",     "https://pubchem.ncbi.nlm.nih.gov/compound/24728612",  "https://www.sigmaaldrich.com/IT/it/search/acetylamino?focus=products&page=1&perpage=15&sort=relevance&term=acetylamino&type=product", 5.0,   "g",  "Shelf A", ""),
        ("tag5", "Sodium Tripolyphosphate",  "Na5P3O10",        "https://pubchem.ncbi.nlm.nih.gov/compound/24455",     "https://www.sigmaaldrich.com/IT/it/search/7758-29-4?focus=products&page=1&perpage=15&sort=relevance&term=7758-29-4&type=cas_number", 1.0,   "kg", "Shelf A", "Irritant"),
    ]

    c.executemany("""
        INSERT OR IGNORE INTO substances
            (rfid_tag_id, substance_name, chemical_formula, pubchem_url, sigmaaldrich_url, initial_quantity, unit, location, primary_hazard)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, demo_substances)

    # Seed consumption rates for each substance
    # These are initial guesses — the model will refine them
    seed_rates = [
        ("tag1", 20.0),    # NaCl: 20g/usage
        ("tag2", 0.3),     # PBS: 0.3L/usage
        ("tag3", 0.05),    # Cholesterol: 50mg/usage (0.05g)
        ("tag4", 0.1),     # Acetylamino: 100mg/usage (0.1g)
        ("tag5", 0.001),   # Sodium Tripolyphosphate: 1g/usage (0.001kg)
    ]

    c.executemany("""
        INSERT OR IGNORE INTO consumption_rates (rfid_tag_id, rate_per_usage)
        VALUES (?, ?)
    """, seed_rates)

    conn.commit()
    conn.close()
    print(f"Database initialized at: {DB_PATH}")
    print(f"Inserted {len(demo_substances)} demo substances.")

if __name__ == "__main__":
    create_and_populate()