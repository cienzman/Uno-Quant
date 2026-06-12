import os
import sys
import time
import subprocess

# Ensure the current directory is in the system path for module imports.
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# ── Monkey patch to fix Arduino bug: app-bricks-py#236 ───────────────────────
from arduino.app_utils import AppController, App, Bridge

def _patched_loop(self, user_loop=None):
    """
    Patched event loop for the Arduino AppController.
    
    This replaces the default AppController.loop to prevent a known bug
    (app-bricks-py#236) where the thread could exit prematurely. It ensures 
    that the application runs indefinitely unless explicitly interrupted.

    Args:
        user_loop (callable, optional): An optional user-defined loop function.
    """
    try:
        if user_loop:
            while True:
                user_loop()
        else:
            while True:
                time.sleep(10)
    except (StopIteration, KeyboardInterrupt):
        pass

# Apply the monkey patch
AppController.loop = _patched_loop

# ── Core system imports ───────────────────────────────────────────────────────
from setup_db import create_and_populate
from db_utils import add_pending_scan

# ── 1. Database setup ─────────────────────────────────────────────────────────
print("Initializing Database...")
create_and_populate()

# ── 2. Launch dashboard.py as a subprocess on port 8501 ──────────────────────
dashboard_path = os.path.join(os.path.dirname(__file__), "dashboard.py")
print("Starting Streamlit dashboard...")
subprocess.Popen([
    sys.executable, "-m", "streamlit", "run", dashboard_path,
    "--server.port", "8501",
    "--server.address", "0.0.0.0",
    "--server.headless", "true",
])

# ── 3. Bridge RPC handler ─────────────────────────────────────────────────────
def on_rfid_scan(tag_id: str):
    """
    Callback function triggered by an RFID scan event from the hardware bridge.
    
    Args:
        tag_id (str): The unique identifier of the scanned RFID tag.
    """
    print(f"[Hardware Event] RFID Scan detected: {tag_id}")
    add_pending_scan(tag_id)

# Register the RPC handler with the Arduino App Bridge
Bridge.provide("rfid_scan", on_rfid_scan)
print("Bridge RPC handler registered. Dashboard at http://192.168.1.112:8501")

# ── 4. App.run() owns the main thread ────────────────────────────────────────
App.run()