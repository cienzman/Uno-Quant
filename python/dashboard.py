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
import streamlit.components.v1 as components
import voice_state


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
    /* Import a clean, modern font */
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;600;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'DM Sans', sans-serif;
        font-size: 16px;
    }

    /* Bold and slightly larger all text */
    p, div, span, label, td, th, li {
        font-weight: 600 !important;
        font-size: 15px !important;
    }

    /* Page background */
    .stApp {
        background-color: #f5f7fa;
    }

    /* Title block */
    .lab-title {
        font-size: 2.2rem;
        font-weight: 800;
        color: #0f2942;
        letter-spacing: -0.5px;
        margin-bottom: 0.1rem;
    }
    .lab-subtitle {
        font-size: 0.95rem;
        color: #6b7a8d;
        font-weight: 500 !important;
        margin-bottom: 1.2rem;
    }

    /* Metric cards */
    [data-testid="stMetric"] {
        background: white;
        border-radius: 12px;
        padding: 1rem 1.2rem;
        border: 1px solid #e2e8f0;
        box-shadow: 0 1px 4px rgba(0,0,0,0.05);
    }
    [data-testid="stMetricLabel"] {
        font-size: 0.8rem !important;
        font-weight: 700 !important;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: #6b7a8d !important;
    }
    [data-testid="stMetricValue"] {
        font-size: 2rem !important;
        font-weight: 800 !important;
        color: #0f2942 !important;
    }

    /* Tabs */
    [data-testid="stTabs"] button {
        font-weight: 700 !important;
        font-size: 14px !important;
    }

    /* Dataframe */
    [data-testid="stDataFrame"] {
        border-radius: 10px;
        overflow: hidden;
        border: 1px solid #e2e8f0;
    }

    /* Sidebar */
    [data-testid="stSidebar"] {
        background-color: #0f2942;
    }
    [data-testid="stSidebar"] * {
        color: #e8edf3 !important;
    }
    [data-testid="stSidebar"] .stButton button {
        background-color: #1a4070;
        border: 1px solid #2a5a9f;
        color: white !important;
        border-radius: 8px;
        font-weight: 700 !important;
        transition: background 0.2s;
    }
    [data-testid="stSidebar"] .stButton button:hover {
        background-color: #2a5a9f;
    }

    /* Buttons */
    .stButton button {
        border-radius: 8px;
        font-weight: 700 !important;
    }

    /* Info/success/warning/error boxes */
    [data-testid="stAlert"] {
        border-radius: 10px;
        font-weight: 600 !important;
    }
</style>
""", unsafe_allow_html=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

def format_last_event(raw: str) -> str:
    """Make last-event strings shorter and consistent."""
    import re
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
    if "inventory" not in st.session_state:
        st.session_state.inventory = load_inventory_from_db()
    if "last_event" not in st.session_state:
        st.session_state.last_event = None
    if "open_url" not in st.session_state:
        st.session_state.open_url = None
    if "pending_feedback" not in st.session_state:
        st.session_state.pending_feedback = None
        voice_state.clear()


def handle_feedback(level: str, fb: dict):
    update_substance_quantity(fb["tag_id"], level)
    st.session_state.pending_feedback = None
    voice_state.clear()
    st.session_state.inventory = load_inventory_from_db()


def inventory_to_dataframe(inventory):
    rows = []
    quantity_emojis = {
        "A LOT": "🟢 A LOT",
        "MEDIUM": "🟡 MEDIUM",
        "LOW": "🔴 LOW",
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
            voice_state.set_pending_feedback(tag_id, name)

        st.session_state.last_event = {
            "event_type": "Check-in",
            "message": f"{name} returned."
        }
        st.session_state.open_url = None

    st.session_state.inventory = load_inventory_from_db()


# ── Boot ──────────────────────────────────────────────────────────────────────
initialize_state()

# Poll hardware RFID scans every 3 s
st_autorefresh(interval=3000, key="rfid_polling")
pending_tags = get_and_clear_pending_scans()
if pending_tags:
    for p_tag in pending_tags:
        run_scan(p_tag)
    st.rerun()

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown('<p class="lab-title">🧪 Smart Laboratory Inventory</p>', unsafe_allow_html=True)
st.markdown('<p class="lab-subtitle">RFID-based chemical inventory · real-time tracking · depletion forecast</p>', unsafe_allow_html=True)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## Controls")
    st.markdown("### Scan simulator")
    named_tags = get_named_tags()

    for label, tag_id in named_tags.items():
        if st.button(label, use_container_width=True):
            run_scan(tag_id)
            st.rerun()

    if st.button("⟳  Random RFID scan", use_container_width=True):
        run_scan(get_random_scan())
        st.rerun()



    st.markdown("### System")
    if st.button("↺  Reset inventory", use_container_width=True):
        st.session_state.inventory = load_inventory_from_db()
        st.session_state.last_event = None
        st.session_state.open_url = None
        st.session_state.pending_feedback = None
        voice_state.clear()
        st.rerun()

    if st.button("🗑  Clear events log", use_container_width=True):
        with get_conn() as conn:
            conn.execute("DELETE FROM sessions")
        st.rerun()

    st.divider()
    st.caption("Simulated RFID — will be replaced by RC522 hardware events from Arduino UNO Q.")

# ── Metrics ───────────────────────────────────────────────────────────────────
statuses = count_statuses(st.session_state.inventory)
total_items = len(st.session_state.inventory)

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total items", total_items)
col2.metric("Present", statuses.get("Present", 0))
col3.metric("Checked out", statuses.get("Checked out", 0))
col4.metric("Missing", statuses.get("Missing", 0))

st.divider()

# ── Last event banner ─────────────────────────────────────────────────────────
if st.session_state.last_event:
    event = st.session_state.last_event
    if event["event_type"] == "Unknown tag":
        st.warning(f"⚠️  {event['message']}")
    elif event["event_type"] == "Check-out":
        st.error(f"↑  {event['message']}")
    else:
        st.success(f"↓  {event['message']}")
else:
    st.info("Waiting for the first RFID scan.")

# ── PubChem iframe ────────────────────────────────────────────────────────────
if st.session_state.get("open_url"):
    c_left, c_right = st.columns([0.9, 0.1])
    with c_left:
        st.markdown("#### PubChem Reference")
    with c_right:
        if st.button("✕ Close"):
            st.session_state.open_url = None
            st.rerun()
    st.components.v1.iframe(st.session_state.open_url, height=500, scrolling=True)

# ── Micro-feedback ────────────────────────────────────────────────────────────
vstate = voice_state.get_pending_feedback()
if vstate.get("feedback_resolved"):
    st.success(f"Voice recorded: {vstate['resolved_level']}")
    st.session_state.pending_feedback = None
    st.session_state.inventory = load_inventory_from_db()
    voice_state.clear()
    st.rerun()

if st.session_state.get("pending_feedback"):
    fb = st.session_state.pending_feedback
    st.markdown(f"#### 📋 Quick check — {fb['item_name']}")
    st.info(f"How much **{fb['item_name']}** is left?")
    c1, c2, c3, c4 = st.columns(4)
    if c1.button("🟢 A LOT", use_container_width=True, key=f"fb_alot_{fb['session_id']}"):
        handle_feedback("A LOT", fb)
        st.rerun()
    if c2.button("🟡 MEDIUM", use_container_width=True, key=f"fb_medium_{fb['session_id']}"):
        handle_feedback("MEDIUM", fb)
        st.rerun()
    if c3.button("🔴 LOW", use_container_width=True, key=f"fb_little_{fb['session_id']}"):
        handle_feedback("LOW", fb)
        st.rerun()
    if c4.button("Skip", use_container_width=True, key=f"fb_dismiss_{fb['session_id']}"):
        st.session_state.pending_feedback = None
        voice_state.clear()
        st.rerun()

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_inventory, tab_alerts, tab_events, tab_voice, tab_architecture = st.tabs([
    "Inventory",
    "Safety alerts",
    "Event log",
    "Voice assistant",
    "Architecture",
])

# ── Tab: Inventory ────────────────────────────────────────────────────────────
with tab_inventory:
    st.subheader("Chemical inventory")

    query = st.text_input(
        "Search",
        placeholder="Filter by name, formula, location, hazard or tag ID…",
    )

    filtered_inventory = search_inventory(st.session_state.inventory, query)
    df = inventory_to_dataframe(filtered_inventory)

    def highlight_checked_out(val):
        if val == "Checked out":
            return "background-color: #fff0f0; color: #c0392b; font-weight: 700;"
        return ""

    styled_df = df.style.map(highlight_checked_out, subset=["Status"])
    st.dataframe(styled_df, use_container_width=True, hide_index=True)

    st.markdown("#### Sigma-Aldrich reference")
    selected_tag = st.selectbox(
        "Select substance",
        list(st.session_state.inventory.keys()),
        format_func=lambda tag: st.session_state.inventory[tag]["name"],
    )

    item = st.session_state.inventory[selected_tag]
    if item.get("sigmaaldrich_url"):
        st.info("→  View the full product specification on Sigma-Aldrich.")
        st.link_button("Open Sigma-Aldrich page ↗", item["sigmaaldrich_url"], use_container_width=True)
    else:
        st.caption("No Sigma-Aldrich reference available for this item.")

# ── Tab: Alerts ───────────────────────────────────────────────────────────────
with tab_alerts:
    st.subheader("Safety & expiration alerts")

    alerts = get_expiry_alerts(st.session_state.inventory, days_threshold=45)

    checked_out_items = [
        {"Name": item["name"], "Status": item["status"], "Location": item["location"], "Hazard": item["hazard"]}
        for item in st.session_state.inventory.values()
        if item["status"] == "Checked out"
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
            st.dataframe(
                co_df.style.map(highlight_checked_out, subset=["Status"]),
                use_container_width=True, hide_index=True,
            )

# ── Tab: Event log ────────────────────────────────────────────────────────────
with tab_events:
    st.subheader("RFID event log")
    events_df = load_events()

    if events_df.empty:
        st.info("No events recorded yet.")
    else:
        st.dataframe(
            events_df.sort_values("Taken At", ascending=False),
            use_container_width=True,
            hide_index=True,
        )

# ── Tab: Voice assistant ──────────────────────────────────────────────────────
with tab_voice:
    st.subheader("Voice assistant")
    st.caption("Type a command as if it had been transcribed from speech.")

    command = st.text_input(
        "Command",
        placeholder="e.g. where is acetone · missing items · expiring soon",
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
    st.subheader("System architecture")

    st.markdown("""
```
Current demo (simulated RFID)
──────────────────────────────
Sidebar buttons
      ↓
inventory_logic.py
      ↓
Streamlit dashboard

Production (Arduino UNO Q)
──────────────────────────────
RC522 RFID reader
      ↓
STM32 MCU (sketch.ino)
      ↓
Bridge (Arduino RPC)
      ↓
Python backend (main.py)  →  SQLite DB
      ↓
Streamlit dashboard
      ↓
Browser (any device on Wi-Fi)
```
""")

    st.caption(
        "The dashboard is hardware-independent. "
        "Replace the simulated button events with real RFID tag IDs from Arduino UNO Q."
    )

# ── Voice Widget ──────────────────────────────────────────────────────────────
VOICE_WIDGET_HTML = """
<div id="voice-widget" style="position:fixed;bottom:24px;right:24px;z-index:9999">
  <button id="micBtn" onclick="toggleVoice()"
    style="width:56px;height:56px;border-radius:50%;border:none;
           background:#E53E3E;color:white;font-size:24px;cursor:pointer">
    🎙
  </button>
  <div id="voiceStatus" style="text-align:center;font-size:11px;color:#666;margin-top:4px">
    Off
  </div>
</div>
<script>
// ── State ──────────────────────────────────────────────────────
let ws = null, audioCtx = null, workletNode = null, isActive = false, isStarting = false;

let isHttps = location.protocol === "https:";
try {
  if (window.parent && window.parent.location.protocol === "https:") {
    isHttps = true;
  }
} catch(e) {}
const protocol = isHttps ? "wss://" : "ws://";

let host = "";
try { host = window.parent.location.hostname; } catch(e) {}
if (!host) { host = window.location.hostname; }
if (!host) { host = "localhost"; }

const WS_URL = protocol + host + ":8502/ws/voice";
const STATE_URL = (isHttps ? "https://" : "http://") + host + ":8502/state";

// ── Audio playback queue ──────────────────────────────────────
const audioQueue = [];
let isPlaying = false;

// ── Auto-start Polling ────────────────────────────────────────
setInterval(async () => {
    try {
        const res = await fetch(STATE_URL);
        const state = await res.json();
        
        // Auto-start if there's pending feedback and we aren't active
        if (state.pending_tag_id && !state.feedback_resolved && !isActive) {
            console.log("Auto-starting voice for pending feedback:", state.pending_item_name);
            await startVoice();
        }
        
        // Auto-stop if feedback is resolved or cleared, and we are active
        if ((!state.pending_tag_id || state.feedback_resolved) && isActive) {
            console.log("Auto-stopping voice as feedback is resolved or cleared");
            stopVoice();
        }
    } catch(e) {}
}, 2000);

async function playNext() {
  if (isPlaying || audioQueue.length === 0) return;
  isPlaying = true;
  const pcm = audioQueue.shift();
  const samples = new Int16Array(pcm);
  const float32 = new Float32Array(samples.length);
  for (let i = 0; i < samples.length; i++)
    float32[i] = samples[i] / 32768.0;
  const buf = audioCtx.createBuffer(1, float32.length, 24000);
  buf.getChannelData(0).set(float32);
  const src = audioCtx.createBufferSource();
  src.buffer = buf;
  src.connect(audioCtx.destination);
  src.onended = () => { isPlaying = false; playNext(); };
  src.start();
}

// ── Toggle ─────────────────────────────────────────────────────
async function toggleVoice() {
  isActive ? stopVoice() : await startVoice();
}

async function startVoice() {
  if (isActive || isStarting) return;
  isStarting = true;
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    alert("Microphone access is not supported. Ensure you are accessing the dashboard via HTTPS.");
    isStarting = false;
    return;
  }
  try {
    audioCtx = new AudioContext({ sampleRate: 16000 });
    
    const workletCode = `
      class PCMProcessor extends AudioWorkletProcessor {
          process(inputs, outputs, parameters) {
              const input = inputs[0];
              if (input.length > 0) {
                  const channelData = input[0];
                  const pcm16 = new Int16Array(channelData.length);
                  for (let i = 0; i < channelData.length; i++) {
                      let s = Math.max(-1, Math.min(1, channelData[i]));
                      pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
                  }
                  this.port.postMessage(pcm16.buffer, [pcm16.buffer]);
              }
              return true;
          }
      }
      registerProcessor('pcm-processor', PCMProcessor);
    `;
    const b64 = btoa(workletCode);
    const dataUri = 'data:application/javascript;base64,' + b64;
    
    await audioCtx.audioWorklet.addModule(dataUri);
    if (!audioCtx) return;
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    if (!audioCtx) return;
    const source = audioCtx.createMediaStreamSource(stream);
    workletNode = new AudioWorkletNode(audioCtx, "pcm-processor");
    source.connect(workletNode);

    ws = new WebSocket(WS_URL);
    ws.binaryType = "arraybuffer";
    ws.onopen = () => { isActive = true; isStarting = false; updateUI(true); };
    ws.onerror = (e) => {
        isStarting = false;
        alert("WebSocket connection failed. If you are using HTTPS with a self-signed certificate, your browser is blocking the Voice Assistant on port 8502. \\n\\nPlease open https://" + host + ":8502 in a new tab, accept the security warning ('Advanced' -> 'Proceed'), and then return here to try again.");
    };
    ws.onmessage = (e) => {
      if (e.data instanceof ArrayBuffer) {
        audioQueue.push(e.data);
        playNext();
      }
    };
    ws.onclose = () => stopVoice();

    workletNode.port.onmessage = (e) => {
      if (ws && ws.readyState === 1) ws.send(e.data);
    };
  } catch (err) {
    isStarting = false;
    console.error(err);
    alert("Error starting voice: " + err.message);
    stopVoice();
  }
}

function stopVoice() {
  ws && ws.close();
  if (audioCtx) { audioCtx.close(); }
  ws = null; audioCtx = null; isActive = false; isStarting = false;
  updateUI(false);
}

function updateUI(on) {
  document.getElementById("micBtn").style.background = on ? "#38A169" : "#E53E3E";
  document.getElementById("voiceStatus").textContent = on ? "Listening" : "Off";
}
</script>
"""

components.html(VOICE_WIDGET_HTML, height=100)