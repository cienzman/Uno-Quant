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
    get_and_clear_pending_scans
)

from streamlit_autorefresh import st_autorefresh

from inventory_logic import (
    count_statuses,
    get_expiry_alerts,
    search_inventory,
)
from simulated_rfid import get_random_scan, get_named_tags


st.set_page_config(
    page_title="Smart Lab Inventory",
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
        padding-top: 1.8rem;
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
    """Make last-event strings shorter and consistent."""
    # e.g. "Returned at 2026-06-06 14:32:11" → "Returned · 06 Jun 14:32"
    for verb in ("Returned at", "Checked out at", "Registered at"):
        if raw.startswith(verb):
            rest = raw[len(verb):].strip()
            try:
                from datetime import datetime
                dt = datetime.strptime(rest, "%Y-%m-%d %H:%M:%S")
                short = dt.strftime("%d %b %H:%M")
                action = verb.replace(" at", "").replace(" out", " out")
                return f"{action} · {short}"
            except ValueError:
                return raw
    return raw


def load_inventory_from_db():
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
            "status": "Present" if s["state"] == "ON_SHELF" else "Checked out",
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
    if "inventory" not in st.session_state:
        st.session_state.inventory = load_inventory_from_db()
    if "last_event" not in st.session_state:
        st.session_state.last_event = None
    if "open_url" not in st.session_state:
        st.session_state.open_url = None
    if "pending_feedback" not in st.session_state:
        st.session_state.pending_feedback = None


def handle_feedback(level: str, fb: dict):
    update_substance_quantity(fb["tag_id"], level)
    st.session_state.pending_feedback = None
    st.session_state.inventory = load_inventory_from_db()


def inventory_to_dataframe(inventory):
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
            "Expiry": item["expiry_date"],
            "Last Event": item["last_event"],
        })
    return pd.DataFrame(rows)


def load_events():
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
    def highlight_status(val):
        if val == "Checked out":
            return "background-color: #fff0ed; color: #c0392b; font-weight: 800;"
        if val == "Present":
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

# Poll hardware RFID scans every 3 s
st_autorefresh(interval=3000, key="rfid_polling")
pending_tags = get_and_clear_pending_scans()
if pending_tags:
    for p_tag in pending_tags:
        run_scan(p_tag)
    st.rerun()

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
        <div class="hero-eyebrow">● Live dashboard</div>
        <h1 class="hero-title">Smart Laboratory Inventory</h1>
        <p class="hero-subtitle">
            Track chemical containers through RFID, surface safety references instantly,
            and collect quick quantity feedback without exposing users to backend complexity.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ── Metrics ───────────────────────────────────────────────────────────────────
statuses = count_statuses(st.session_state.inventory)
total_items = len(st.session_state.inventory)
checked_out_count = statuses.get("Checked out", 0)
present_count = statuses.get("Present", 0)
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
        st.session_state.pending_feedback = None
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_inventory, tab_alerts, tab_events, tab_voice, tab_architecture = st.tabs([
    "📦 Inventory",
    "🚨 Safety alerts",
    "🕒 Event log",
    "🎙 Voice assistant",
    "🏗 Architecture",
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

        st.caption(f"Showing {len(df)} of {total_items} substances")
        st.dataframe(style_inventory_table(df), use_container_width=True, hide_index=True, height=430)

    with right:
        section_header("🔗", "Reference lookup", "Open supplier information without leaving the dashboard flow.")

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
    section_header("🚨", "Safety and usage alerts", "Focus only on items that need attention.")

    alerts = get_expiry_alerts(st.session_state.inventory, days_threshold=45)

    checked_out_items = [
        {"Name": item["name"], "Status": item["status"], "Location": item["location"], "Hazard": item["hazard"]}
        for item in st.session_state.inventory.values()
        if item["status"] == "Checked out"
    ]

    low_quantity_items = [
        {"Name": item["name"], "Qty": item["quantity_level"], "Location": item["location"], "Hazard": item["hazard"]}
        for item in st.session_state.inventory.values()
        if item.get("quantity_level") == "LITTLE"
    ]

    if not alerts and not checked_out_items and not low_quantity_items:
        st.success("No active alerts. Inventory is currently stable.")
    else:
        alert_col1, alert_col2 = st.columns(2, gap="large")

        with alert_col1:
            st.markdown("#### Checked-out substances")
            if checked_out_items:
                co_df = pd.DataFrame(checked_out_items)
                st.dataframe(
                    co_df.style.map(
                        lambda val: "background-color: #fff0ed; color: #c0392b; font-weight: 800;" if val == "Checked out" else "",
                        subset=["Status"],
                    ),
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.success("No substances are currently checked out.")

        with alert_col2:
            st.markdown("#### Low quantity")
            if low_quantity_items:
                st.dataframe(pd.DataFrame(low_quantity_items), use_container_width=True, hide_index=True)
            else:
                st.success("No low-quantity items.")

        if alerts:
            st.markdown("#### Expiration alerts")
            st.dataframe(pd.DataFrame(alerts), use_container_width=True, hide_index=True)

# ── Tab: Event log ────────────────────────────────────────────────────────────
with tab_events:
    section_header("🕒", "RFID event log", "Chronological history of check-out and return sessions.")
    events_df = load_events()

    if events_df.empty:
        st.info("No events recorded yet. Scan a substance to populate this log.")
    else:
        event_count = len(events_df)
        active_sessions = events_df[events_df["Returned At"] == "Still in use"].shape[0]
        e1, e2 = st.columns(2)
        e1.metric("Recorded sessions", event_count)
        e2.metric("Still in use", active_sessions)

        st.dataframe(
            events_df.sort_values("Taken At", ascending=False),
            use_container_width=True,
            hide_index=True,
            height=460,
        )

# ── Tab: Voice assistant ──────────────────────────────────────────────────────
with tab_voice:
    section_header("🎙", "Voice-style assistant", "Type a simple command as if it had been transcribed from speech.")

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
            missing = [i["name"] for i in st.session_state.inventory.values() if i["status"] == "Checked out"]
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

# ── Tab: Architecture ─────────────────────────────────────────────────────────
with tab_architecture:
    section_header("🏗", "System architecture", "Same backend pipeline, redesigned user-facing layer.")

    col_a, col_b = st.columns(2, gap="large")
    with col_a:
        st.markdown("#### Current demo")
        st.markdown("""
```text
Simulated RFID buttons
        ↓
inventory_logic.py
        ↓
Streamlit dashboard
```
""")
    with col_b:
        st.markdown("#### Production path")
        st.markdown("""
```text
RC522 RFID reader
        ↓
STM32 MCU sketch
        ↓
Arduino RPC bridge
        ↓
Python backend → SQLite DB
        ↓
Streamlit dashboard
```
""")

    st.caption(
        "The dashboard remains hardware-independent. The interface can keep the same user flow while simulated button events are replaced by real Arduino UNO Q RFID tag IDs."
    )
