import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "db", "inventory.db")

def upgrade_database_v2():
    if not os.path.exists(DB_PATH):
        print(f"Database not found at {DB_PATH}. Please run setup_db.py first.")
        return

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    try:
        print("Checking substances table...")
        c.execute("PRAGMA table_info(substances)")
        columns = [col[1] for col in c.fetchall()]
        if "sigmaaldrich_url" not in columns:
            print("Adding 'sigmaaldrich_url' column to 'substances'...")
            c.execute("ALTER TABLE substances ADD COLUMN sigmaaldrich_url TEXT DEFAULT ''")
        else:
            print("'sigmaaldrich_url' column already exists.")

        # Update URLs for existing tags
        urls = {
            "tag1": "https://www.sigmaaldrich.com/IT/it/search/7647-14-5?focus=products&page=1&perpage=15&sort=relevance&term=7647-14-5&type=cas_number",
            "tag2": "https://www.sigmaaldrich.com/IT/it/search/phosphate-buffered-saline?focus=products&page=1&perpage=15&sort=relevance&term=Phosphate%20Buffered%20Saline&type=product",
            "tag3": "https://www.sigmaaldrich.com/IT/it/search/57-88-5?focus=products&page=1&perpage=15&sort=relevance&term=57-88-5&type=cas_number",
            "tag4": "https://www.sigmaaldrich.com/IT/it/search/acetylamino?focus=products&page=1&perpage=15&sort=relevance&term=acetylamino&type=product",
            "tag5": "https://www.sigmaaldrich.com/IT/it/search/7758-29-4?focus=products&page=1&perpage=15&sort=relevance&term=7758-29-4&type=cas_number",
        }

        print("Updating Sigma-Aldrich URLs...")
        for tag, url in urls.items():
            c.execute("UPDATE substances SET sigmaaldrich_url = ? WHERE rfid_tag_id = ?", (url, tag))

        conn.commit()
        print("Database upgrade completed successfully.")
    except Exception as e:
        print(f"Error upgrading database: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    upgrade_database_v2()
