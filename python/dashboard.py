import streamlit as st
import pandas as pd
from pathlib import Path
from copy import deepcopy

import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from db_utils import (
    get_all_substances,
    get_substance,
    update_substance_state,
    open_session,
    close_session,
    get_last_session,
    get_conn,
    update_substance_quantity,
    get_and_clear_pending_scans,
    get_feedback_count,
    clear_feedbacks,
)

import threading
import time

from ml_pipeline import predict_quantity, train_model

from inventory_logic import (
    count_statuses,
    get_expiry_alerts,
    search_inventory,
)
from simulated_rfid import get_random_scan, get_named_tags


st.set_page_config(
    page_title="Uno Quant",
    page_icon="🧪",
    layout="wide",
)

# ── Styling ───────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

    :root {
        --bg: #f4f7fb;
        --surface: #ffffff;
        --surface-soft: #f8fafc;
        --primary: #123047;
        --primary-soft: #e8f1f8;
        --accent: #1f7a8c;
        --text: #17212b;
        --muted: #667085;
        --border: #dce4ec;
        --success: #0f8a5f;
        --success-bg: #eaf8f1;
        --warning: #b86e00;
        --warning-bg: #fff6e5;
        --danger: #c0392b;
        --danger-bg: #fff0ed;
        --info-bg: #eef6ff;
    }

    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }

    .stApp {
        background:
            radial-gradient(circle at top left, rgba(31, 122, 140, 0.10), transparent 30%),
            linear-gradient(180deg, #f8fbfd 0%, var(--bg) 100%);
        color: var(--text);
    }

    .block-container {
        padding-top: 3.8rem;
        padding-bottom: 2.5rem;
        max-width: 1440px;
    }

    h1, h2, h3, h4, h5, h6, p, div, span, label, td, th, li {
        letter-spacing: -0.01em;
    }

    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0e263b 0%, #102f49 100%);
        border-right: 1px solid rgba(255,255,255,0.10);
    }

    [data-testid="stSidebar"] * {
        color: #eef6fb !important;
    }

    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
    [data-testid="stSidebar"] .stCaptionContainer {
        color: rgba(238, 246, 251, 0.76) !important;
    }

    [data-testid="stSidebar"] .stButton button {
        width: 100%;
        border-radius: 0.85rem;
        background: rgba(255, 255, 255, 0.10);
        border: 1px solid rgba(255, 255, 255, 0.18);
        color: white !important;
        font-weight: 700;
        padding: 0.68rem 0.8rem;
        transition: all 0.18s ease;
    }

    [data-testid="stSidebar"] .stButton button:hover {
        background: rgba(255, 255, 255, 0.20);
        border-color: rgba(255, 255, 255, 0.38);
        transform: translateY(-1px);
    }

    .hero-card {
        background: linear-gradient(135deg, #123047 0%, #1f7a8c 100%);
        border-radius: 1.5rem;
        padding: 1.45rem 1.65rem;
        color: white;
        box-shadow: 0 18px 45px rgba(15, 41, 66, 0.16);
        margin-bottom: 1.1rem;
    }

    .hero-eyebrow {
        display: inline-flex;
        align-items: center;
        gap: 0.4rem;
        padding: 0.28rem 0.62rem;
        border-radius: 999px;
        background: rgba(255,255,255,0.14);
        border: 1px solid rgba(255,255,255,0.18);
        font-size: 0.78rem;
        font-weight: 700;
        margin-bottom: 0.7rem;
    }

    .hero-title {
        font-size: 2.35rem;
        line-height: 1.05;
        font-weight: 800;
        margin: 0;
    }

    .hero-subtitle {
        margin-top: 0.55rem;
        margin-bottom: 0;
        max-width: 820px;
        color: rgba(255,255,255,0.82);
        font-size: 1rem;
        font-weight: 500;
    }

    .section-header {
        display: flex;
        align-items: center;
        gap: 0.7rem;
        margin: 0.15rem 0 0.85rem 0;
    }

    .section-icon {
        width: 2.15rem;
        height: 2.15rem;
        border-radius: 0.8rem;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        background: var(--primary-soft);
        color: var(--primary);
        font-size: 1.12rem;
    }

    .section-title {
        font-size: 1.25rem;
        line-height: 1.1;
        font-weight: 800;
        color: var(--primary);
        margin: 0;
    }

    .section-caption {
        color: var(--muted);
        font-size: 0.88rem;
        margin: 0.18rem 0 0 0;
    }

    .soft-card {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 1.15rem;
        padding: 1.05rem 1.1rem;
        box-shadow: 0 10px 30px rgba(15, 41, 66, 0.055);
    }

    .status-banner {
        border-radius: 1.1rem;
        padding: 1rem 1.1rem;
        border: 1px solid var(--border);
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 1rem;
        margin: 0.6rem 0 1rem 0;
        box-shadow: 0 8px 24px rgba(15, 41, 66, 0.05);
    }

    .status-banner strong {
        display: block;
        color: var(--text);
        font-size: 0.98rem;
        margin-bottom: 0.15rem;
    }

    .status-banner span {
        color: var(--muted);
        font-size: 0.88rem;
        font-weight: 500;
    }

    .banner-idle { background: var(--info-bg); }
    .banner-success { background: var(--success-bg); }
    .banner-danger { background: var(--danger-bg); }
    .banner-warning { background: var(--warning-bg); }

    .banner-emoji {
        width: 2.5rem;
        height: 2.5rem;
        border-radius: 0.9rem;
        background: rgba(255,255,255,0.72);
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1.3rem;
        flex-shrink: 0;
    }

    .quick-card {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 1.1rem;
        padding: 1rem 1rem 0.95rem 1rem;
        box-shadow: 0 10px 28px rgba(15, 41, 66, 0.05);
        min-height: 6.35rem;
    }

    .quick-label {
        color: var(--muted);
        font-size: 0.78rem;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        font-weight: 800;
        margin-bottom: 0.25rem;
    }

    .quick-value {
        color: var(--primary);
        font-size: 2rem;
        font-weight: 800;
        line-height: 1;
        margin-bottom: 0.3rem;
    }

    .quick-note {
        color: var(--muted);
        font-size: 0.83rem;
        font-weight: 500;
    }

    [data-testid="stMetric"] {
        background: var(--surface);
        border-radius: 1.1rem;
        padding: 1rem 1.05rem;
        border: 1px solid var(--border);
        box-shadow: 0 10px 28px rgba(15, 41, 66, 0.05);
    }

    [data-testid="stMetricLabel"] {
        color: var(--muted) !important;
        font-size: 0.78rem !important;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        font-weight: 800 !important;
    }

    [data-testid="stMetricValue"] {
        color: var(--primary) !important;
        font-size: 2rem !important;
        font-weight: 800 !important;
    }

    [data-testid="stTabs"] button {
        font-weight: 800 !important;
        font-size: 0.92rem !important;
    }

    [data-testid="stDataFrame"] {
        border-radius: 1rem;
        overflow: hidden;
        border: 1px solid var(--border);
        box-shadow: 0 10px 30px rgba(15, 41, 66, 0.045);
    }

    .stTextInput input, .stSelectbox div[data-baseweb="select"] > div {
        border-radius: 0.9rem !important;
        border-color: var(--border) !important;
    }

    .stButton button, .stLinkButton a {
        border-radius: 0.85rem !important;
        font-weight: 800 !important;
    }

    [data-testid="stAlert"] {
        border-radius: 1rem;
        border: 1px solid rgba(15, 41, 66, 0.08);
    }

    .tiny-help {
        color: var(--muted);
        font-size: 0.82rem;
        line-height: 1.45;
        margin-top: 0.2rem;
    }

    .command-chip {
        display: inline-block;
        padding: 0.34rem 0.58rem;
        border-radius: 999px;
        background: var(--surface-soft);
        border: 1px solid var(--border);
        color: var(--primary);
        font-size: 0.82rem;
        font-weight: 700;
        margin: 0.15rem 0.2rem 0.15rem 0;
    }

    .divider-soft {
        height: 1px;
        background: var(--border);
        margin: 1rem 0;
    }
</style>
""", unsafe_allow_html=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

def format_last_event(raw: str) -> str:
    """
    Format raw datetime strings from the database into a concise, human-readable format.
    
    Args:
        raw (str): The raw string, typically formatted as "Action at YYYY-MM-DD HH:MM:SS".
        
    Returns:
        str: A shortened representation, e.g., "Returned · 06 Jun 14:32". Returns the 
             original string if parsing fails.
    """
    import re
    from datetime import datetime
    for verb in ("Returned at", "Checked out at", "Registered at"):
        if raw.startswith(verb):
            rest = raw[len(verb):].strip()
            try:
                # Handle possible ISO format or microseconds
                normalized = rest.replace("T", " ")
                if "." in normalized:
                    dt = datetime.strptime(normalized, "%Y-%m-%d %H:%M:%S.%f")
                else:
                    dt = datetime.strptime(normalized, "%Y-%m-%d %H:%M:%S")
                short = dt.strftime("%d %b %H:%M")
                action = verb.replace(" at", "").replace(" out", " out")
                return f"{action} · {short}"
            except ValueError:
                return raw
    return raw


def load_inventory_from_db() -> dict:
    """
    Load the current state of all chemical substances from the SQLite database.
    
    Constructs a dictionary containing rich metadata (e.g., status, hazards, URLs) 
    mapped by RFID tag ID for fast lookup by the frontend dashboard.
    
    Returns:
        dict: The mapped inventory state dictionary.
    """
    inventory = {}
    substances = get_all_substances()
    for s in substances:
        last_session = get_last_session(s["rfid_tag_id"])

        if last_session:
            if last_session["returned_at"]:
                raw_event = f"Returned at {last_session['returned_at']}"
            else:
                raw_event = f"Checked out at {last_session['taken_at']}"
        else:
            raw_event = f"Registered at {s['registered_at']}"

        inventory[s["rfid_tag_id"]] = {
            "name": s["substance_name"],
            "chemical_formula": s["chemical_formula"],
            "status": "ON SHELF" if s["state"] == "ON_SHELF" else "IN USE",
            "location": s["location"],
            "hazard": s["primary_hazard"],
            "quantity_level": s["quantity_level"],
            "unit": s["unit"],
            "capacity": s["initial_quantity"],
            "expiry_date": "N/A",
            "last_event": format_last_event(raw_event),
            "pubchem_url": s["pubchem_url"],
            "sigmaaldrich_url": s.get("sigmaaldrich_url", ""),
        }
    return inventory


def initialize_state():
    """
    Initialize required Streamlit session state variables to prevent KeyErrors 
    during early execution loops or component re-renders.
    """
    if "inventory" not in st.session_state:
        st.session_state.inventory = load_inventory_from_db()
    if "last_event" not in st.session_state:
        st.session_state.last_event = None
    if "open_url" not in st.session_state:
        st.session_state.open_url = None
    if "pending_feedback" not in st.session_state:
        st.session_state.pending_feedback = None


def check_and_trigger_training():
    """
    Monitor the global feedback count and automatically spawn an asynchronous 
    background thread to retrain the AI sequence model when enough data is collected.
    """
    if get_feedback_count() >= 500:
        st.toast("Training AI model in background...", icon="🧠")
        # Start training in a background thread so we don't block the UI
        def bg_train():
            train_model()
            clear_feedbacks() # Reset counter after successful training
        
        threading.Thread(target=bg_train, daemon=True).start()

def handle_feedback(level: str, fb: dict):
    """
    Process manual quantity micro-feedback submitted by the user.

    Args:
        level (str): The answered quantity level (e.g., "A LOT", "MEDIUM", "LITTLE").
        fb (dict): A dictionary containing context about the targeted session and item.
    """
    update_substance_quantity(fb["tag_id"], level)
    st.session_state.pending_feedback = None
    st.session_state.inventory = load_inventory_from_db()
    check_and_trigger_training()


def inventory_to_dataframe(inventory: dict) -> pd.DataFrame:
    """
    Transform the structured inventory dictionary into a tabular Pandas DataFrame 
    for rendering in Streamlit's data grid UI.

    Args:
        inventory (dict): The mapped inventory state dictionary.

    Returns:
        pd.DataFrame: A formatted dataframe mapping the inventory context.
    """
    rows = []
    quantity_emojis = {
        "A LOT": "🟢 A LOT",
        "MEDIUM": "🟡 MEDIUM",
        "LITTLE": "🔴 LITTLE",
        "UNKNOWN": "⚪ UNKNOWN"
    }
    
    for tag_id, item in inventory.items():
        rows.append({
            "Tag ID": tag_id,
            "Name": item["name"],
            "Formula": item["chemical_formula"],
            "Status": item["status"],
            "Location": item["location"],
            "Hazard": item["hazard"],
            "Qty": quantity_emojis.get(item.get('quantity_level', 'UNKNOWN'), "⚪ UNKNOWN"),
            "Last Event": item["last_event"],
        })
    return pd.DataFrame(rows)


def load_events() -> pd.DataFrame:
    """
    Query the SQLite database for an ordered history of substance usage sessions.

    Returns:
        pd.DataFrame: A DataFrame representing historical check-out/check-in events.
    """
    with get_conn() as conn:
        query = """
            SELECT s.taken_at, s.returned_at, s.session_duration_s, sub.substance_name, s.rfid_tag_id
            FROM sessions s
            JOIN substances sub ON s.rfid_tag_id = sub.rfid_tag_id
            ORDER BY s.taken_at DESC
        """
        rows = conn.execute(query).fetchall()

    if not rows:
        return pd.DataFrame()

    events = []
    for r in rows:
        events.append({
            "Taken At": r["taken_at"],
            "Returned At": r["returned_at"] if r["returned_at"] else "Still in use",
            "Item Name": r["substance_name"],
            "Tag ID": r["rfid_tag_id"],
            "Duration (s)": round(r["session_duration_s"], 1) if r["session_duration_s"] else None
        })
    return pd.DataFrame(events)


def run_scan(tag_id: str):
    """
    Handle the logical processing of a detected RFID tag scan event.
    
    Toggles the state of a registered substance between 'ON_SHELF' and 'IN_USE',
    opens/closes usage sessions, prompts user micro-feedback upon return, 
    and handles unrecognized tags gracefully.

    Args:
        tag_id (str): The detected RFID tag.
    """
    substance = get_substance(tag_id)
    if not substance:
        st.session_state.last_event = {
            "event_type": "Unknown tag",
            "message": f"Unknown RFID tag {tag_id} detected."
        }
        st.session_state.open_url = None
        return

    name = substance["substance_name"]
    if substance["state"] == "ON_SHELF":
        update_substance_state(tag_id, "IN_USE")
        open_session(tag_id)
        st.session_state.last_event = {
            "event_type": "Check-out",
            "message": f"{name} checked out."
        }
        st.session_state.open_url = substance["pubchem_url"]
    else:
        update_substance_state(tag_id, "ON_SHELF")
        session_info = close_session(tag_id)

        if session_info and tag_id in st.session_state.inventory:
            st.session_state.pending_feedback = {
                "tag_id": tag_id,
                "session_id": session_info["id"],
                "item_name": name
            }

        st.session_state.last_event = {
            "event_type": "Check-in",
            "message": f"{name} returned."
        }
        st.session_state.open_url = None

    st.session_state.inventory = load_inventory_from_db()


def section_header(icon: str, title: str, caption: str = ""):
    """Render a styled section header widget using HTML."""
    st.markdown(
        f"""
        <div class="section-header">
            <div class="section-icon">{icon}</div>
            <div>
                <p class="section-title">{title}</p>
                <p class="section-caption">{caption}</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def quick_card(label: str, value: int | str, note: str):
    """Render a styled high-level metric card widget using HTML."""
    st.markdown(
        f"""
        <div class="quick-card">
            <div class="quick-label">{label}</div>
            <div class="quick-value">{value}</div>
            <div class="quick-note">{note}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_last_event():
    """Render a dynamically styled alert banner displaying the most recent hardware event."""
    if not st.session_state.last_event:
        st.markdown(
            """
            <div class="status-banner banner-idle">
                <div style="display:flex; align-items:center; gap:0.85rem;">
                    <div class="banner-emoji">📡</div>
                    <div><strong>Ready for the next scan</strong><span>Waiting for an RFID event from the reader or simulator.</span></div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    event = st.session_state.last_event
    if event["event_type"] == "Unknown tag":
        icon, klass, title = "⚠️", "banner-warning", "Unknown tag detected"
    elif event["event_type"] == "Check-out":
        icon, klass, title = "↗️", "banner-danger", "Substance checked out"
    else:
        icon, klass, title = "↘️", "banner-success", "Substance returned"

    st.markdown(
        f"""
        <div class="status-banner {klass}">
            <div style="display:flex; align-items:center; gap:0.85rem;">
                <div class="banner-emoji">{icon}</div>
                <div><strong>{title}</strong><span>{event['message']}</span></div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def style_inventory_table(df: pd.DataFrame):
    """
    Apply row-level CSS highlighting rules to the rendered inventory DataFrame 
    based on substance status and quantity thresholds.

    Args:
        df (pd.DataFrame): The unstyled inventory DataFrame.

    Returns:
        pd.io.formats.style.Styler: The styled DataFrame object ready for rendering.
    """
    def highlight_status(val):
        if val == "Checked out" or val == "IN USE":
            return "background-color: #fff0ed; color: #c0392b; font-weight: 800;"
        if val == "Present" or val == "ON SHELF":
            return "background-color: #eaf8f1; color: #0f8a5f; font-weight: 800;"
        return ""

    def highlight_qty(val):
        if "LITTLE" in str(val):
            return "background-color: #fff0ed; color: #c0392b; font-weight: 800;"
        if "MEDIUM" in str(val):
            return "background-color: #fff6e5; color: #b86e00; font-weight: 800;"
        if "A LOT" in str(val):
            return "background-color: #eaf8f1; color: #0f8a5f; font-weight: 800;"
        return "background-color: #f8fafc; color: #667085;"

    styled = df.style.map(highlight_status, subset=["Status"])
    styled = styled.map(highlight_qty, subset=["Qty"])
    return styled


# ── Boot ──────────────────────────────────────────────────────────────────────
initialize_state()

# Poll hardware RFID scans every 3 s to keep UI responsive
@st.fragment(run_every=3)
def poll_rfid():
    """
    Streamlit asynchronous fragment that periodically polls the database 
    for newly queued hardware RFID events from the Arduino C++ layer.
    """
    pending_tags = get_and_clear_pending_scans()
    if pending_tags:
        for p_tag in pending_tags:
            run_scan(p_tag)
        st.rerun()

poll_rfid()

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🧪 Smart Lab")
    st.caption("RFID inventory control panel")
    st.markdown("<div class='divider-soft'></div>", unsafe_allow_html=True)

    st.markdown("### Scan simulator")
    st.caption("Use these buttons to simulate RFID scans during the demo.")
    named_tags = get_named_tags()

    for label, tag_id in named_tags.items():
        if st.button(label, use_container_width=True):
            run_scan(tag_id)
            st.rerun()

    if st.button("🎲 Random RFID scan", use_container_width=True):
        run_scan(get_random_scan())
        st.rerun()

    st.markdown("<div class='divider-soft'></div>", unsafe_allow_html=True)
    st.markdown("### Maintenance")

    with st.expander("System actions", expanded=False):
        if st.button("↺ Reset inventory view", use_container_width=True):
            st.session_state.inventory = load_inventory_from_db()
            st.session_state.last_event = None
            st.session_state.open_url = None
            st.rerun()

        if st.button("🗑 Clear event log", use_container_width=True):
            with get_conn() as conn:
                conn.execute("DELETE FROM sessions")
            st.rerun()

    st.caption("Demo mode: simulated scans can be replaced by RC522 events from Arduino UNO Q.")

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown(
    """
    <div class="hero-card">
        <h1 class="hero-title">🧪 Uno Quant</h1>
        <p class="hero-subtitle">
        Smart Laboratory Inventory.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ── Metrics ───────────────────────────────────────────────────────────────────
statuses = count_statuses(st.session_state.inventory)
total_items = len(st.session_state.inventory)
checked_out_count = statuses.get("Checked out", 0) + statuses.get("IN USE", 0)
present_count = statuses.get("Present", 0) + statuses.get("ON SHELF", 0)
missing_count = statuses.get("Missing", 0)
low_stock_count = sum(
    1 for item in st.session_state.inventory.values()
    if item.get("quantity_level") == "LITTLE"
)
unknown_qty_count = sum(
    1 for item in st.session_state.inventory.values()
    if item.get("quantity_level") == "UNKNOWN"
)

m1, m2, m3, m4, m5 = st.columns(5)
with m1:
    quick_card("Total items", total_items, "Registered containers")
with m2:
    quick_card("On shelf", present_count, "Ready to use")
with m3:
    quick_card("In use", checked_out_count, "Currently checked out")
with m4:
    quick_card("Low quantity", low_stock_count, "Need attention")
with m5:
    quick_card("Unknown qty", unknown_qty_count, "Awaiting feedback")

render_last_event()

# ── PubChem iframe ────────────────────────────────────────────────────────────
if st.session_state.get("open_url"):
    st.markdown("<div class='soft-card'>", unsafe_allow_html=True)
    c_left, c_right = st.columns([0.86, 0.14])
    with c_left:
        section_header("🔬", "PubChem reference", "Opened automatically after check-out for faster safety lookup.")
    with c_right:
        if st.button("✕ Close", use_container_width=True):
            st.session_state.open_url = None
            st.rerun()
    st.components.v1.iframe(st.session_state.open_url, height=460, scrolling=True)
    st.markdown("</div>", unsafe_allow_html=True)

# ── Micro-feedback ────────────────────────────────────────────────────────────
if st.session_state.get("pending_feedback"):
    fb = st.session_state.pending_feedback
    st.markdown("<div class='soft-card'>", unsafe_allow_html=True)
    section_header("📋", f"Quick quantity check", f"How much {fb['item_name']} is left after this use?")
    c1, c2, c3, c4 = st.columns(4)
    if c1.button("🟢 A lot", use_container_width=True, key=f"fb_alot_{fb['session_id']}"):
        handle_feedback("A LOT", fb)
        st.rerun()
    if c2.button("🟡 Medium", use_container_width=True, key=f"fb_medium_{fb['session_id']}"):
        handle_feedback("MEDIUM", fb)
        st.rerun()
    if c3.button("🔴 Little", use_container_width=True, key=f"fb_little_{fb['session_id']}"):
        handle_feedback("LITTLE", fb)
        st.rerun()
    if c4.button("Skip", use_container_width=True, key=f"fb_dismiss_{fb['session_id']}"):
        # AI PREDICTION TRIGGER
        st.toast("AI predicting quantity...", icon="🤖")
        predicted_level = predict_quantity(fb["tag_id"])
        update_substance_quantity(fb["tag_id"], predicted_level, is_ai_prediction=True)
        st.session_state.pending_feedback = None
        st.session_state.inventory = load_inventory_from_db()
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

    # ── Browser-based TTS + STT via Web Speech API ────────────────────────────
    # speechSynthesis speaks the prompt; webkitSpeechRecognition listens;
    # the recognised answer clicks the matching Streamlit button as a fallback-safe action.
    substance_name = fb["item_name"]
    voice_html = f"""
<div id="voice-status" style="
    margin-top:10px; padding:10px 14px; border-radius:12px;
    background:#eef6ff; color:#123047; font-family:Inter,sans-serif;
    font-size:14px; font-weight:700; border:1px solid #dce4ec;">
  🎙️ Starting voice prompt…
</div>
<script>
(function() {{
  var statusEl = document.getElementById('voice-status');

  var prompt = "Quick check for {substance_name}. How much {substance_name} is left? Please say: a lot, medium, little, or skip.";
  var utterance = new SpeechSynthesisUtterance(prompt);
  utterance.rate = 0.95;
  utterance.lang = 'en-US';

  utterance.onstart = function() {{
    statusEl.textContent = '🔊 Speaking…';
  }};

  utterance.onend = function() {{
    statusEl.textContent = '🎙️ Listening… say: A LOT, MEDIUM, LITTLE or SKIP';
    startListening();
  }};

  utterance.onerror = function(e) {{
    statusEl.textContent = '⚠️ TTS error: ' + e.error + ' — use the buttons above.';
  }};

  window.speechSynthesis.cancel();
  window.speechSynthesis.speak(utterance);

  function startListening() {{
    var SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {{
      statusEl.textContent = '⚠️ Browser STT not supported — use the buttons above.';
      return;
    }}

    var rec = new SpeechRecognition();
    rec.lang = 'en-US';
    rec.interimResults = false;
    rec.maxAlternatives = 5;

    rec.onresult = function(event) {{
      var heard = Array.from(event.results[0])
                       .map(function(a) {{ return a.transcript.toLowerCase(); }})
                       .join(' ');
      statusEl.textContent = '✅ Heard: "' + heard + '"';

      var level = classify(heard);
      if (level) {{
        statusEl.textContent = '✅ Classified as: ' + level + ' — saving…';
        postAnswer(level);
      }} else {{
        statusEl.textContent = '❓ Not recognised ("' + heard + '") — use the buttons above.';
      }}
    }};

    rec.onerror = function(e) {{
      statusEl.textContent = '⚠️ STT error: ' + e.error + ' — use the buttons above.';
    }};

    rec.onend = function() {{
      if (statusEl.textContent.startsWith('🎙️')) {{
        statusEl.textContent = '⏱️ No speech detected — use the buttons above.';
      }}
    }};

    rec.start();
  }}

  var MAP = [
    ['a lot',        'A LOT'],
    ['running out',  'LITTLE'],
    ['almost empty', 'LITTLE'],
    ['not much',     'LITTLE'],
    ['plenty',       'A LOT'],
    ['enough',       'A LOT'],
    ['alot',         'A LOT'],
    ['lots',         'A LOT'],
    ['lot',          'A LOT'],
    ['full',         'A LOT'],
    ['much',         'A LOT'],
    ['medium',       'MEDIUM'],
    ['middle',       'MEDIUM'],
    ['moderate',     'MEDIUM'],
    ['half',         'MEDIUM'],
    ['some',         'MEDIUM'],
    ['little',       'LITTLE'],
    ['nearly',       'LITTLE'],
    ['almost',       'LITTLE'],
    ['few',          'LITTLE'],
    ['low',          'LITTLE'],
    ['skip',         'SKIP'],
    ['ignore',       'SKIP'],
    ['later',        'SKIP'],
    ['pass',         'SKIP'],
    ['no',           'SKIP'],
  ];

  function classify(text) {{
    for (var i = 0; i < MAP.length; i++) {{
      if (text.indexOf(MAP[i][0]) !== -1) return MAP[i][1];
    }}
    return null;
  }}

  var LABEL_MAP = {{
    'A LOT':  'a lot',
    'MEDIUM': 'medium',
    'LITTLE': 'little',
    'SKIP':   'skip',
  }};

  function postAnswer(level) {{
    var targetLabel = LABEL_MAP[level];
    var buttons = window.parent.document.querySelectorAll('button');
    for (var i = 0; i < buttons.length; i++) {{
      var btn = buttons[i];
      var text = (btn.innerText || '').trim().toLowerCase();
      if (text.indexOf(targetLabel) !== -1) {{
        btn.click();
        statusEl.textContent = '✅ ' + level + ' — saved!';
        return;
      }}
    }}
    statusEl.textContent = '⚠️ Button not found for ' + level + ' — use buttons above.';
  }}
}})();
</script>
"""
    st.components.v1.html(voice_html, height=68)

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_inventory, tab_alerts, tab_events, tab_voice = st.tabs([
    "📦 Inventory",
    "⚠️ Safety alerts",
    "🕒 Event log",
    "🎙 Query system",
])

# ── Tab: Inventory ────────────────────────────────────────────────────────────
with tab_inventory:
    left, right = st.columns([0.72, 0.28], gap="large")

    with left:
        section_header("📦", "Chemical inventory", "Search, inspect status, and check current quantity levels.")

        query = st.text_input(
            "Search inventory",
            placeholder="Filter by name, formula, location, hazard or tag ID…",
            label_visibility="collapsed",
        )

        filtered_inventory = search_inventory(st.session_state.inventory, query)
        df = inventory_to_dataframe(filtered_inventory)

        st.dataframe(style_inventory_table(df), use_container_width=True, hide_index=True, height=430)

    with right:
        section_header("🔗", "Reference lookup", "Open supplier information.")

        selected_tag = st.selectbox(
            "Select substance",
            list(st.session_state.inventory.keys()),
            format_func=lambda tag: st.session_state.inventory[tag]["name"],
        )

        item = st.session_state.inventory[selected_tag]
        st.markdown(
            f"""
            <div class="soft-card">
                <div class="quick-label">Selected item</div>
                <div style="font-size:1.15rem; font-weight:800; color:#123047; margin-bottom:0.35rem;">{item['name']}</div>
                <div class="tiny-help"><strong>Formula:</strong> {item['chemical_formula']}</div>
                <div class="tiny-help"><strong>Location:</strong> {item['location']}</div>
                <div class="tiny-help"><strong>Hazard:</strong> {item['hazard']}</div>
                <div class="tiny-help"><strong>Status:</strong> {item['status']}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if item.get("sigmaaldrich_url"):
            st.link_button("Open Sigma-Aldrich page ↗", item["sigmaaldrich_url"], use_container_width=True)
        else:
            st.info("No Sigma-Aldrich reference available for this item.")

# ── Tab: Alerts ───────────────────────────────────────────────────────────────
with tab_alerts:
    section_header("⚠️", "Safety & expiration alerts", "Monitor items expiring soon or currently out of the lab.")

    alerts = get_expiry_alerts(st.session_state.inventory, days_threshold=45)

    checked_out_items = [
        {"Name": item["name"], "Status": item["status"], "Location": item["location"], "Hazard": item["hazard"]}
        for item in st.session_state.inventory.values()
        if item["status"] == "Checked out" or item["status"] == "IN USE"
    ]

    if not alerts and not checked_out_items:
        st.success("No active alerts.")
    else:
        if alerts:
            st.markdown("##### Expiration alerts")
            st.dataframe(pd.DataFrame(alerts), use_container_width=True, hide_index=True)

        if checked_out_items:
            st.markdown("##### Checked-out substances")
            co_df = pd.DataFrame(checked_out_items)
            def highlight_checked_out_local(val):
                if val == "Checked out" or val == "IN USE":
                    return "background-color: #fff0ed; color: #c0392b; font-weight: 800;"
                return ""
            st.dataframe(
                co_df.style.map(highlight_checked_out_local, subset=["Status"]),
                use_container_width=True, hide_index=True,
            )

# ── Tab: Event log ────────────────────────────────────────────────────────────
with tab_events:
    section_header("🕒", "RFID event log", "Chronological history of check-out and return sessions.")
    events_df = load_events()

    if events_df.empty:
        st.info("No events recorded yet. Scan a substance to populate this log.")
    else:
        st.dataframe(
            events_df.sort_values("Taken At", ascending=False),
            use_container_width=True,
            hide_index=True,
            height=460,
        )

# ── Tab: Voice assistant ──────────────────────────────────────────────────────
with tab_voice:
    section_header("🎙", "Query system", "Type a simple command")

    st.markdown(
        """
        <span class="command-chip">where is acetone</span>
        <span class="command-chip">missing items</span>
        <span class="command-chip">expiring soon</span>
        """,
        unsafe_allow_html=True,
    )

    command = st.text_input(
        "Command",
        placeholder="Try: where is acetone · missing items · expiring soon",
    )

    if command:
        cmd = command.lower().strip()

        if "where is" in cmd:
            item_name = cmd.replace("where is", "").strip()
            matches = [i for i in st.session_state.inventory.values() if item_name in i["name"].lower()]
            if matches:
                i = matches[0]
                st.success(f"{i['name']} is in **{i['location']}** and is currently **{i['status']}**.")
            else:
                st.warning("No matching substance found.")

        elif "missing" in cmd or "checked out" in cmd:
            missing = [i["name"] for i in st.session_state.inventory.values() if i["status"] == "Checked out" or i["status"] == "IN USE"]
            if missing:
                st.warning("Currently checked out: " + ", ".join(missing))
            else:
                st.success("No substances are currently checked out.")

        elif "expiring" in cmd or "expiry" in cmd:
            alerts = get_expiry_alerts(st.session_state.inventory, days_threshold=45)
            if alerts:
                names = [f"{a['name']} ({a['expiry_date']})" for a in alerts]
                st.warning("Expiring soon: " + ", ".join(names))
            else:
                st.success("No substances are expiring soon.")

        else:
            st.info("Command not recognised. Try: 'where is acetone', 'missing items', or 'expiring soon'.")