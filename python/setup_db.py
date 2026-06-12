# python3 setup_db.py

import sqlite3
import os
import requests
from urllib.parse import quote

# Absolute path resolution for the SQLite database file
DB_PATH = os.path.join(os.path.dirname(__file__), "db", "inventory.db")


def fetch_pubchem_data(substance_name: str) -> dict | None:
    """
    Query the official PubChem API to retrieve the chemical formula and URL for a given substance.

    Args:
        substance_name (str): The common name or query string of the chemical substance.

    Returns:
        dict | None: A dictionary containing the substance name, CID, chemical formula, 
                     and PubChem URL. Returns None if the network request fails, or if 
                     no valid data is returned by the API.
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
    """
    Initialize the SQLite database schema and seed it with a predefined set of demo substances.
    
    This function handles the creation of the database directory, construction of essential 
    tables (substances, sessions, alerts, feedback_logs, pending_scans), and performs automatic 
    PubChem metadata enrichment for the seeded data.
    """
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # ── SUBSTANCES TABLE ──────────────────────────────────────────────────────────
    # Master registry tracking physical chemical containers and their metadata.
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
            quantity_level      TEXT DEFAULT 'UNKNOWN',
            registered_at       TEXT DEFAULT (datetime('now'))
        )
    """)

    # ── SESSIONS TABLE ────────────────────────────────────────────────────────────
    # Logs individual usage sessions, defining duration between TAKEN and RETURNED events.
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

    # ── ALERTS TABLE ──────────────────────────────────────────────────────────────
    # Stores actionable notifications for the user interface.
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

    # ── FEEDBACK LOGS TABLE ───────────────────────────────────────────────────────
    # Dedicated table to collect labeled ground-truth quantity data for ML training.
    c.execute("""
        CREATE TABLE IF NOT EXISTS feedback_logs (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            rfid_tag_id         TEXT NOT NULL,
            quantity_level      TEXT NOT NULL,
            timestamp           TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (rfid_tag_id) REFERENCES substances(rfid_tag_id)
        )
    """)

    # ── PENDING_SCANS TABLE ───────────────────────────────────────────────────────
    # A queue table bridging hardware RFID interrupts with the Streamlit frontend.
    c.execute("""
        CREATE TABLE IF NOT EXISTS pending_scans (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            tag_id              TEXT NOT NULL,
            timestamp           TEXT DEFAULT (datetime('now'))
        )
    """)

    conn.commit()

    # ── DEMO SUBSTANCES SEED DATA ─────────────────────────────────────────────────
    # Define physical constraints manually, but rely on PubChem for exact chemical attributes.

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

    # Execute dynamic PubChem enrichment pipeline for seed data
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

    # Safely batch-insert ignoring predefined existing constraints
    c.executemany("""
        INSERT OR IGNORE INTO substances
            (rfid_tag_id, substance_name, chemical_formula, pubchem_url, sigmaaldrich_url, initial_quantity, unit, location, primary_hazard)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, demo_substances)

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
    """
    Perform a complete tear-down and rebuild of the SQLite database.
    
    Warning: This action permanently deletes all tracked sessions, logs, and state.
    """
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        print(f"Deleted existing database at: {DB_PATH}")
    create_and_populate()
    print("Database reset complete.")

if __name__ == "__main__":
    reset_db()