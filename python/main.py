import os
import sys
import time
import subprocess
import atexit

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# ── Monkey patch to fix Arduino bug: app-bricks-py#236 ───────────────────────
from arduino.app_utils import AppController, App, Bridge

def _patched_loop(self, user_loop=None):
    try:
        if user_loop:
            while True:
                user_loop()
        else:
            while True:
                time.sleep(10)
    except (StopIteration, KeyboardInterrupt):
        pass

AppController.loop = _patched_loop

# ── Your imports ──────────────────────────────────────────────────────────────
from setup_db import create_and_populate
from db_utils import add_pending_scan

# ── 1. Database setup ─────────────────────────────────────────────────────────
print("Initializing Database...")
create_and_populate()

# ── Generate SSL Certificate ──────────────────────────────────────────────────
cert_file = "/tmp/vision-agent-cert.pem"
key_file = "/tmp/vision-agent-key.pem"

if not os.path.exists(cert_file) or not os.path.exists(key_file):
    print("Generating self-signed SSL certificate...")
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import hashes
        from cryptography.x509.oid import NameOID
        from cryptography import x509
        import datetime

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, u"arduino-uno-q")])
        cert = x509.CertificateBuilder().subject_name(subject).issuer_name(issuer).public_key(
            key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(
            datetime.datetime.utcnow()).not_valid_after(
            datetime.datetime.utcnow() + datetime.timedelta(days=365)).sign(key, hashes.SHA256())

        with open(cert_file, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))
        with open(key_file, "wb") as f:
            f.write(key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption()
            ))
        print("Certificate generated successfully.")
    except Exception as e:
        print(f"Error generating certificate: {e}")
        cert_file = None
        key_file = None

# ── 2. Launch dashboard.py as a subprocess on port 8501 ──────────────────────
dashboard_path = os.path.join(os.path.dirname(__file__), "dashboard.py")
print("Starting Streamlit dashboard...")
streamlit_cmd = [
    sys.executable, "-m", "streamlit", "run", dashboard_path,
    "--server.port", "8501",
    "--server.address", "0.0.0.0",
    "--server.headless", "true",
]
if cert_file and key_file:
    streamlit_cmd.extend(["--server.sslCertFile", cert_file, "--server.sslKeyFile", key_file])

streamlit_process = subprocess.Popen(streamlit_cmd)

# ── 2.5 Launch voice_assistant.py as a subprocess on port 8502 ────────────────
voice_path = os.path.join(os.path.dirname(__file__), "voice_assistant.py")
print("Starting Voice Assistant on port 8502...")
log_file = open(os.path.join(os.path.dirname(__file__), "voice_assistant.log"), "w")
voice_process = subprocess.Popen([sys.executable, voice_path], stdout=log_file, stderr=subprocess.STDOUT)

def cleanup_subprocesses():
    print("Terminating background services...")
    streamlit_process.terminate()
    voice_process.terminate()

atexit.register(cleanup_subprocesses)

# ── 3. Bridge RPC handler ─────────────────────────────────────────────────────
def on_rfid_scan(tag_id: str):
    print(f"[Hardware Event] RFID Scan detected: {tag_id}")
    add_pending_scan(tag_id)

Bridge.provide("rfid_scan", on_rfid_scan)
protocol_str = "https" if cert_file else "http"
print(f"Bridge RPC handler registered. Dashboard at {protocol_str}://192.168.1.112:8501")

# ── 4. App.run() owns the main thread ────────────────────────────────────────
App.run()