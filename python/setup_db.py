# python3 setup_db.py

import sqlite3
import os
import requests
from urllib.parse import quote

DB_PATH = os.path.join(os.path.dirname(__file__), "db", "inventory.db")


def fetch_pubchem_data(substance_name: str):
    """
    Given a substance name, fetches its chemical formula and PubChem link.
    """

    encoded_name = quote(substance_name)

    url = (
        "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/"
        f"{encoded_name}/property/MolecularFormula/JSON"
    )

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()

        data = response.json()
        props = data["PropertyTable"]["Properties"][0]

        cid = props["CID"]
        formula = props.get("MolecularFormula", "N/A")
        pubchem_url = f"https://pubchem.ncbi.nlm.nih.gov/compound/{cid}"

        return {
            "name": substance_name,
            "cid": cid,
            "formula": formula,
            "pubchem_url": pubchem_url
        }

    except requests.exceptions.RequestException as e:
        print(f"Network/API error for '{substance_name}': {e}")
        return None

    except KeyError:
        print(f"Unexpected response format for '{substance_name}'")
        return None

    except IndexError:
        print(f"No PubChem result found for '{substance_name}'")
        return None


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
            pubchem_url         TEXT DEFAULT '',
            sigmaaldrich_url    TEXT DEFAULT '',
            initial_quantity    REAL DEFAULT NULL,
            unit                TEXT DEFAULT NULL,
            location            TEXT DEFAULT 'Shelf A',
            primary_hazard      TEXT DEFAULT '',
            state               TEXT DEFAULT 'ON_SHELF',
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
            returned_at         TEXT DEFAULT NULL,
            session_duration_s  REAL DEFAULT NULL,
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
            estimated_remaining REAL NOT NULL,
            consumption_rate    REAL NOT NULL,
            feedback            TEXT DEFAULT NULL,
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
            alert_type          TEXT NOT NULL,
            message             TEXT,
            resolved            INTEGER DEFAULT 0,
            created_at          TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (rfid_tag_id) REFERENCES substances(rfid_tag_id)
        )
    """)

    # --- CONSUMPTION_RATES TABLE ---
    # Per-substance learned rate, updated over time
    c.execute("""
        CREATE TABLE IF NOT EXISTS consumption_rates (
            rfid_tag_id         TEXT PRIMARY KEY,
            rate_per_usage      REAL NOT NULL DEFAULT 0.5,
            n_sessions          INTEGER DEFAULT 0,
            rate_variance       REAL DEFAULT 100.0,
            last_updated        TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (rfid_tag_id) REFERENCES substances(rfid_tag_id)
        )
    """)

    # --- PENDING_SCANS TABLE ---
    # Hardware scans queuing to bridge Arduino to Streamlit
    c.execute("""
        CREATE TABLE IF NOT EXISTS pending_scans (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            tag_id              TEXT NOT NULL,
            timestamp           TEXT DEFAULT (datetime('now'))
        )
    """)

    conn.commit()

    # --- POPULATE DEMO SUBSTANCES ---
    # Qui restano manuali solo i dati fisici/locali del laboratorio.
    # Formula chimica e PubChem URL vengono recuperati automaticamente da PubChem.

    demo_substances_input = [
        {
            "rfid_tag_id": "CA398D32",
            "display_name": "Sodium Chloride",
            "pubchem_query": "Sodium Chloride",
            "sigmaaldrich_url": "https://www.sigmaaldrich.com/IT/it/search/7647-14-5?focus=products&page=1&perpage=15&sort=relevance&term=7647-14-5&type=cas_number",
            "initial_quantity": 200.0,
            "unit": "g",
            "location": "Shelf A",
            "primary_hazard": "Corrosive"
        },
        {
            "rfid_tag_id": "8049D13E",
            "display_name": "Phosphate Buffered Saline",
            "pubchem_query": "Phosphate Buffered Saline",
            "sigmaaldrich_url": "https://www.sigmaaldrich.com/IT/it/search/phosphate-buffered-saline?focus=products&page=1&perpage=15&sort=relevance&term=Phosphate%20Buffered%20Saline&type=product",
            "initial_quantity": 1.0,
            "unit": "L",
            "location": "Shelf A",
            "primary_hazard": ""
        },
        {
            "rfid_tag_id": "tag3",
            "display_name": "Cholesterol",
            "pubchem_query": "Cholesterol",
            "sigmaaldrich_url": "https://www.sigmaaldrich.com/IT/it/search/57-88-5?focus=products&page=1&perpage=15&sort=relevance&term=57-88-5&type=cas_number",
            "initial_quantity": 1.0,
            "unit": "g",
            "location": "Shelf A",
            "primary_hazard": ""
        },
        {
            "rfid_tag_id": "tag4",
            "display_name": "Acetylamino",
            "pubchem_query": "Oligo Hyaluronic Acid",
            "sigmaaldrich_url": "https://www.sigmaaldrich.com/IT/it/search/acetylamino?focus=products&page=1&perpage=15&sort=relevance&term=acetylamino&type=product",
            "initial_quantity": 5.0,
            "unit": "g",
            "location": "Shelf A",
            "primary_hazard": ""
        },
        {
            "rfid_tag_id": "tag5",
            "display_name": "Sodium Tripolyphosphate",
            "pubchem_query": "Pentasodium triphosphate",
            "sigmaaldrich_url": "https://www.sigmaaldrich.com/IT/it/search/7758-29-4?focus=products&page=1&perpage=15&sort=relevance&term=7758-29-4&type=cas_number",
            "initial_quantity": 1.0,
            "unit": "kg",
            "location": "Shelf A",
            "primary_hazard": "Irritant"
        },
    ]

    demo_substances = []

    for item in demo_substances_input:
        pubchem_data = fetch_pubchem_data(item["pubchem_query"])

        if pubchem_data is None:
            print(f"Using fallback values for '{item['display_name']}'")

            chemical_formula = "N/A"
            pubchem_url = ""
        else:
            chemical_formula = pubchem_data["formula"]
            pubchem_url = pubchem_data["pubchem_url"]

        demo_substances.append((
            item["rfid_tag_id"],
            item["display_name"],
            chemical_formula,
            pubchem_url,
            item["sigmaaldrich_url"],
            item["initial_quantity"],
            item["unit"],
            item["location"],
            item["primary_hazard"]
        ))

    c.executemany("""
        INSERT OR IGNORE INTO substances
            (rfid_tag_id, substance_name, chemical_formula, pubchem_url, sigmaaldrich_url, initial_quantity, unit, location, primary_hazard)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, demo_substances)

    # Seed consumption rates for each substance
    # These are initial guesses — the model will refine them
    seed_rates = [
    ("CA398D32", 20.0),   # NaCl: 20g/usage
    ("8049D13E", 0.3),    # PBS: 0.3L/usage
    ("tag3", 0.05),       # Cholesterol
    ("tag4", 0.1),        # Acetylamino
    ("tag5", 0.001),      # Sodium Tripolyphosphate
    ]

    c.executemany("""
        INSERT OR IGNORE INTO consumption_rates (rfid_tag_id, rate_per_usage)
        VALUES (?, ?)
    """, seed_rates)

    conn.commit()
    conn.close()

    print(f"Database initialized at: {DB_PATH}")
    print(f"Inserted {len(demo_substances)} demo substances.")

    print("\nInserted substances:")
    for substance in demo_substances:
        print("-------------------------")
        print(f"RFID tag: {substance[0]}")
        print(f"Name: {substance[1]}")
        print(f"Formula: {substance[2]}")
        print(f"PubChem URL: {substance[3]}")
        print(f"Initial quantity: {substance[5]} {substance[6]}")


if __name__ == "__main__":
    create_and_populate()

def reset_db():
    """Delete and fully recreate the database from scratch."""
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        print(f"Deleted existing database at: {DB_PATH}")
    create_and_populate()
    print("Database reset complete.")

if __name__ == "__main__":
    reset_db()