import os
import sys
import sqlite3
import random
from datetime import datetime, timedelta

# Ensure we can import our db_utils and setup_db
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from db_utils import get_conn, DB_PATH
import setup_db

def generate_synthetic_dataset(days=60):
    """
    Generates synthetic laboratory sessions based on complex temporal and
    co-occurrence rules to pre-train the intelligent tracking model.
    """
    print("Resetting database...")
    setup_db.reset_db()
    
    # Internal hidden stocks
    # 1.0 = 100%. "A LOT" > 0.6, "MEDIUM" > 0.2, "LITTLE" <= 0.2
    stocks = {
        "CA398D32": 1.0, # Sodium Chloride
        "8049D13E": 1.0, # PBS
        "tag3": 1.0,     # Cholesterol
        "tag4": 1.0,     # Acetylamino
        "tag5": 1.0      # Sodium Tripolyphosphate
    }
    
    # Track the last logged level to avoid spamming the same level
    last_logged_level = {k: "A LOT" for k in stocks.keys()}
    
    def get_level(stock):
        if stock > 0.6: return "A LOT"
        if stock > 0.2: return "MEDIUM"
        return "LITTLE"

    start_date = datetime.now() - timedelta(days=days)
    
    conn = get_conn()
    cur = conn.cursor()
    
    total_sessions = 0
    total_feedbacks = 0
    
    print(f"Generating data for {days} days...")
    
    for day_offset in range(days):
        current_date = start_date + timedelta(days=day_offset)
        
        # Decide if there's a morning session (8am - 12pm)
        if random.random() < 0.8: # 80% chance of morning lab work
            hour = random.randint(8, 11)
            minute = random.randint(0, 59)
            session_time = current_date.replace(hour=hour, minute=minute)
            
            # Morning Rule: A (CA398D32) and B (8049D13E) often used together.
            # Heavy usage for A, light for B.
            if random.random() < 0.7:
                # A used
                dur_a = random.randint(300, 1800) # 5-30 mins
                end_a = session_time + timedelta(seconds=dur_a)
                cur.execute("INSERT INTO sessions (rfid_tag_id, taken_at, returned_at, session_duration_s) VALUES (?, ?, ?, ?)",
                            ("CA398D32", session_time.isoformat(), end_a.isoformat(), dur_a))
                stocks["CA398D32"] -= (dur_a / 3600.0) * 0.15 # Consumes ~5-10% per hour of usage
                total_sessions += 1
                
                # B used shortly after
                time_b = session_time + timedelta(minutes=random.randint(1, 10))
                dur_b = random.randint(60, 600) # 1-10 mins
                end_b = time_b + timedelta(seconds=dur_b)
                cur.execute("INSERT INTO sessions (rfid_tag_id, taken_at, returned_at, session_duration_s) VALUES (?, ?, ?, ?)",
                            ("8049D13E", time_b.isoformat(), end_b.isoformat(), dur_b))
                stocks["8049D13E"] -= (dur_b / 3600.0) * 0.05 # Light consumption
                total_sessions += 1

        # Decide if there's an afternoon session (1pm - 5pm)
        if random.random() < 0.9: # 90% chance of afternoon lab work
            hour = random.randint(13, 16)
            minute = random.randint(0, 59)
            session_time = current_date.replace(hour=hour, minute=minute)
            
            # Afternoon Rule: C (tag3) and D (tag4) used together.
            if random.random() < 0.6:
                # C used
                dur_c = random.randint(600, 3600) 
                end_c = session_time + timedelta(seconds=dur_c)
                cur.execute("INSERT INTO sessions (rfid_tag_id, taken_at, returned_at, session_duration_s) VALUES (?, ?, ?, ?)",
                            ("tag3", session_time.isoformat(), end_c.isoformat(), dur_c))
                stocks["tag3"] -= (dur_c / 3600.0) * 0.2
                total_sessions += 1
                
                # D used
                time_d = session_time + timedelta(minutes=random.randint(5, 15))
                dur_d = random.randint(300, 1800)
                end_d = time_d + timedelta(seconds=dur_d)
                cur.execute("INSERT INTO sessions (rfid_tag_id, taken_at, returned_at, session_duration_s) VALUES (?, ?, ?, ?)",
                            ("tag4", time_d.isoformat(), end_d.isoformat(), dur_d))
                stocks["tag4"] -= (dur_d / 3600.0) * 0.1
                total_sessions += 1

            # Another Afternoon pattern: A used with C (different consumption)
            elif random.random() < 0.3:
                dur_a = random.randint(120, 600) 
                end_a = session_time + timedelta(seconds=dur_a)
                cur.execute("INSERT INTO sessions (rfid_tag_id, taken_at, returned_at, session_duration_s) VALUES (?, ?, ?, ?)",
                            ("CA398D32", session_time.isoformat(), end_a.isoformat(), dur_a))
                stocks["CA398D32"] -= (dur_a / 3600.0) * 0.02 # Very light
                total_sessions += 1
                
                time_c = session_time + timedelta(minutes=random.randint(1, 5))
                dur_c = random.randint(300, 900)
                end_c = time_c + timedelta(seconds=dur_c)
                cur.execute("INSERT INTO sessions (rfid_tag_id, taken_at, returned_at, session_duration_s) VALUES (?, ?, ?, ?)",
                            ("tag3", time_c.isoformat(), end_c.isoformat(), dur_c))
                stocks["tag3"] -= (dur_c / 3600.0) * 0.15 # Moderate
                total_sessions += 1

        # Random standalone usage for tag5 (Tripolyphosphate)
        if random.random() < 0.4:
            hour = random.randint(9, 17)
            minute = random.randint(0, 59)
            session_time = current_date.replace(hour=hour, minute=minute)
            dur = random.randint(300, 2400)
            end = session_time + timedelta(seconds=dur)
            cur.execute("INSERT INTO sessions (rfid_tag_id, taken_at, returned_at, session_duration_s) VALUES (?, ?, ?, ?)",
                        ("tag5", session_time.isoformat(), end.isoformat(), dur))
            stocks["tag5"] -= (dur / 3600.0) * 0.12
            total_sessions += 1

        # Check and record feedback if levels changed, or randomly to augment data
        for tag, stock in stocks.items():
            if stock <= 0:
                # Restock event!
                stocks[tag] = 1.0
                last_logged_level[tag] = "A LOT"
                # Log restocking feedback
                fb_time = current_date.replace(hour=18, minute=0)
                cur.execute("INSERT INTO feedback_logs (rfid_tag_id, quantity_level, timestamp) VALUES (?, ?, ?)",
                            (tag, "A LOT", fb_time.isoformat()))
                # Update current state
                cur.execute("UPDATE substances SET quantity_level = ? WHERE rfid_tag_id = ?", ("A LOT", tag))
                total_feedbacks += 1
            else:
                current_lvl = get_level(stock)
                # If the level dropped, log it
                if current_lvl != last_logged_level[tag]:
                    last_logged_level[tag] = current_lvl
                    fb_time = current_date.replace(hour=18, minute=30)
                    cur.execute("INSERT INTO feedback_logs (rfid_tag_id, quantity_level, timestamp) VALUES (?, ?, ?)",
                                (tag, current_lvl, fb_time.isoformat()))
                    cur.execute("UPDATE substances SET quantity_level = ? WHERE rfid_tag_id = ?", (current_lvl, tag))
                    total_feedbacks += 1
                # Or randomly 5% chance of a redundant feedback (user confirms it's still MEDIUM, etc.)
                elif random.random() < 0.05:
                    fb_time = current_date.replace(hour=random.randint(10, 16), minute=random.randint(0, 59))
                    cur.execute("INSERT INTO feedback_logs (rfid_tag_id, quantity_level, timestamp) VALUES (?, ?, ?)",
                                (tag, current_lvl, fb_time.isoformat()))
                    cur.execute("UPDATE substances SET quantity_level = ? WHERE rfid_tag_id = ?", (current_lvl, tag))
                    total_feedbacks += 1

    conn.commit()
    conn.close()
    
    print(f"Synthetic dataset generation complete.")
    print(f"Total sessions generated: {total_sessions}")
    print(f"Total feedbacks generated: {total_feedbacks}")

if __name__ == "__main__":
    generate_synthetic_dataset(100) # generate 100 days to ensure enough data
