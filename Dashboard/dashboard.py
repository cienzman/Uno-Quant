import streamlit as st
import pandas as pd
from pathlib import Path
from copy import deepcopy

import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db_utils import (
    get_all_substances,
    get_latest_estimate,
    get_substance,
    update_substance_state,
    open_session,
    close_session,
    get_last_session,
    get_rate,
    update_rate,
    save_estimate,
    get_conn,
    get_avg_session_duration,
    get_sessions_per_day,
    save_micro_feedback
)

from predictive_model import (
    calculate_session_consumption,
    update_rate_belief,
    apply_feedback_correction
)

from inventory_logic import (
    count_statuses,
    get_expiry_alerts,
    search_inventory,
)
from simulated_rfid import get_random_scan, get_named_tags
from forecast_mock import build_mock_forecast, build_forecast_summary


st.set_page_config(
    page_title="Smart Lab Inventory",
    page_icon="🧪",
    layout="wide",
)

st.markdown("""
<style>
    /* Make all dashboard text bold */
    * { font-weight: bold !important; }

    /* Keyframes for flashing effect */
    @keyframes flash {
        0% { color: #ff0000; }
        50% { color: #ffcc00; }
        100% { color: #ff0000; }
    }
    
    .flashing-status {
        animation: flash 1s infinite;
    }
</style>
""", unsafe_allow_html=True)


def load_inventory_from_db():
    inventory = {}
    substances = get_all_substances()
    for s in substances:
        estimate = get_latest_estimate(s["rfid_tag_id"])
        last_session = get_last_session(s["rfid_tag_id"])
        rate_mean, n_sessions, rate_var = get_rate(s["rfid_tag_id"])
        sessions_per_day = get_sessions_per_day(s["rfid_tag_id"])
        
        if last_session:
            if last_session["returned_at"]:
                last_event = f"Returned at {last_session['returned_at']}"
            else:
                last_event = f"Checked out at {last_session['taken_at']}"
        else:
            last_event = f"Registered at {s['registered_at']}"

        current_qty = estimate["estimated_remaining"] if estimate else s["initial_quantity"]
        
        inventory[s["rfid_tag_id"]] = {
            "name": s["substance_name"],
            "chemical_formula": s["chemical_formula"],
            "status": "Present" if s["state"] == "ON_SHELF" else "Checked out",
            "location": s["location"],
            "hazard": s["primary_hazard"],
            "predicted_quantity": current_qty,
            "unit": s["unit"],
            "capacity": s["initial_quantity"],
            "rate_mean": rate_mean,
            "rate_var": rate_var,
            "sessions_per_day": sessions_per_day,
            "expiry_date": "N/A",
            "last_event": last_event,
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

def handle_feedback(feedback_yes: bool, fb: dict):
    new_qty = apply_feedback_correction(fb["estimated_qty"], fb["rate_per_usage"], feedback_yes)
    save_micro_feedback(fb["tag_id"], fb["session_id"], feedback_yes, new_qty)
    save_estimate(fb["tag_id"], fb["session_id"], new_qty, fb["rate_per_usage"])
    st.session_state.pending_feedback = None
    st.session_state.inventory = load_inventory_from_db()


def inventory_to_dataframe(inventory):
    rows = []
    for tag_id, item in inventory.items():
        rows.append({
            "Tag ID": tag_id,
            "Name": item["name"],
            "Formula": item["chemical_formula"],
            "Status": item["status"],
            "Location": item["location"],
            "Hazard": item["hazard"],
            "Predicted quantity": f"{item.get('predicted_quantity', 'N/A')} {item.get('unit', '')}",
            "Expiry date": item["expiry_date"],
            "Last event": item["last_event"],
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
            prev_qty = float(st.session_state.inventory[tag_id]["predicted_quantity"])
            prior_mean, n_sessions, prior_var = get_rate(tag_id)
            
            # Phase 0: Duration scaling
            avg_duration = get_avg_session_duration(tag_id)
            session_duration_s = session_info["session_duration_s"]
            estimated_consumed = calculate_session_consumption(prior_mean, session_duration_s, avg_duration)
            new_qty = max(0.0, prev_qty - estimated_consumed)
            
            # Phase 1: Bayesian update
            if avg_duration and avg_duration > 0 and session_duration_s > 0:
                observed_rate = estimated_consumed / session_duration_s * avg_duration
            else:
                observed_rate = estimated_consumed
                
            likelihood_var = st.session_state.get("likelihood_var", 25.0)
            posterior_mean, posterior_var = update_rate_belief(prior_mean, prior_var, observed_rate, likelihood_var)
            
            update_rate(tag_id, posterior_mean, n_sessions + 1, posterior_var)
            save_estimate(tag_id, session_info["id"], new_qty, posterior_mean)
            
            st.session_state.pending_feedback = {
                "tag_id": tag_id,
                "session_id": session_info["id"],
                "estimated_qty": new_qty,
                "rate_per_usage": posterior_mean,
                "item_name": name
            }
            
        st.session_state.last_event = {
            "event_type": "Check-in",
            "message": f"{name} returned."
        }
        st.session_state.open_url = None

    st.session_state.inventory = load_inventory_from_db()


initialize_state()

st.title("🧪 Smart Laboratory Inventory Dashboard")
st.caption(
    "RFID-based chemical inventory prototype with simulated check-in/check-out events and mocked depletion forecast."
)

# Sidebar
with st.sidebar:
    st.header("Demo controls")

    st.subheader("RFID scan simulator")
    named_tags = get_named_tags()

    for label, tag_id in named_tags.items():
        if st.button(label, use_container_width=True):
            run_scan(tag_id)
            st.rerun()

    if st.button("Random RFID scan", use_container_width=True):
        run_scan(get_random_scan())
        st.rerun()

    st.divider()

    st.subheader("Model settings")
    likelihood_var = st.number_input(
        "Observation Variance (Likelihood)",
        min_value=1.0, max_value=500.0, value=25.0, step=5.0,
        help="Higher value means the model trusts its previous rate belief more than the newly observed duration."
    )
    st.session_state.likelihood_var = likelihood_var

    st.subheader("System actions")
    if st.button("Reset demo inventory", use_container_width=True):
        st.session_state.inventory = load_inventory_from_db()
        st.session_state.last_event = None
        st.session_state.open_url = None
        st.rerun()

    if st.button("Clear events log", use_container_width=True):
        with get_conn() as conn:
            conn.execute("DELETE FROM sessions")
        st.rerun()

    st.divider()
    st.info(
        "In the real version, these buttons will be replaced by RFID events "
        "coming from Arduino UNO Q."
    )


# Metrics
statuses = count_statuses(st.session_state.inventory)
total_items = len(st.session_state.inventory)

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total items", total_items)
col2.metric("Present", statuses.get("Present", 0))

# Custom HTML for flashing metric
checked_out_count = statuses.get("Checked out", 0)
col3.markdown(f"""
    <div data-testid="stMetric" class="flashing-status">
        <label data-testid="stMetricLabel" class="st-emotion-cache-1wivap2 e1i5pmia2">Checked out</label>
        <div data-testid="stMetricValue" class="st-emotion-cache-1wivap2 e1i5pmia3">{checked_out_count}</div>
    </div>
""", unsafe_allow_html=True)

col4.metric("Missing", statuses.get("Missing", 0))

# Last event
if st.session_state.last_event:
    event = st.session_state.last_event

    if event["event_type"] == "Unknown tag":
        st.warning(f"⚠️ {event['message']}")
    elif event["event_type"] == "Check-out":
        st.error(f"📤 {event['message']}")
    else:
        st.success(f"📥 {event['message']}")
else:
    st.info("Waiting for the first simulated RFID scan.")

# PubChem iframe
if st.session_state.get("open_url"):
    c_left, c_right = st.columns([0.9, 0.1])
    with c_left:
        st.markdown("### PubChem Reference")
    with c_right:
        if st.button("❌ Close", key="close_pubchem"):
            st.session_state.open_url = None
            st.rerun()
    st.components.v1.iframe(st.session_state.open_url, height=500, scrolling=True)

# Micro-feedback UI
if st.session_state.get("pending_feedback"):
    fb = st.session_state.pending_feedback
    st.markdown(f"### 📝 Quick Question: {fb['item_name']}")
    st.info(f"Is the {fb['item_name']} enough for at least one more experiment?")
    c1, c2, c3, c4 = st.columns(4)
    if c1.button("✅ YES", use_container_width=True, key=f"fb_yes_{fb['session_id']}"):
        handle_feedback(True, fb)
        st.rerun()
    if c2.button("❌ NO", use_container_width=True, key=f"fb_no_{fb['session_id']}"):
        handle_feedback(False, fb)
        st.rerun()
    if c3.button("Dismiss", use_container_width=True, key=f"fb_dismiss_{fb['session_id']}"):
        st.session_state.pending_feedback = None
        st.rerun()

# Tabs
tab_inventory, tab_forecast, tab_alerts, tab_events, tab_voice, tab_architecture = st.tabs(
    [
        "Inventory",
        "Consumption forecast",
        "Safety alerts",
        "Event log",
        "Voice assistant mock",
        "Architecture",
    ]
)

with tab_inventory:
    st.subheader("Chemical inventory")

    query = st.text_input(
        "Search by name, formula, location, hazard or tag ID",
        placeholder="Example: acetone, flammable, Shelf A...",
    )

    filtered_inventory = search_inventory(st.session_state.inventory, query)
    df = inventory_to_dataframe(filtered_inventory)

    def highlight_checked_out(val):
        return 'background-color: #ffcccc; color: #cc0000; font-weight: bold;' if val == 'Checked out' else ''
        
    styled_df = df.style.map(highlight_checked_out, subset=['Status'])

    st.dataframe(
        styled_df,
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("### Sigma-Aldrich Reference")
    selected_tag = st.selectbox(
        "Select an item",
        list(st.session_state.inventory.keys()),
        format_func=lambda tag: st.session_state.inventory[tag]["name"],
    )

    item = st.session_state.inventory[selected_tag]

    if item.get("sigmaaldrich_url"):
        st.warning("👇 👇 Explore our complete laboratory equipment portfolio on the Sigma-Aldrich website ⬇️⬇️")
        st.link_button("🌐 Open Sigma-Aldrich Reference in New Tab", item["sigmaaldrich_url"], use_container_width=True)
    else:
        st.info("No Sigma-Aldrich reference available for this item.")


with tab_forecast:
    st.subheader("Mocked product depletion forecast")
    st.write(
        "This graph is currently mocked. It simulates historical usage and a simple future trend. "
        "Later, this section can be connected to the real prediction model."
    )

    selected_forecast_tag = st.selectbox(
        "Select substance for forecast",
        list(st.session_state.inventory.keys()),
        format_func=lambda tag: st.session_state.inventory[tag]["name"],
        key="forecast_selectbox",
    )

    forecast_item = st.session_state.inventory[selected_forecast_tag]
    forecast_df, forecast_summary = build_mock_forecast(forecast_item)

    f1, f2, f3 = st.columns(3)
    f1.metric("Residual quantity", f"{forecast_summary['residual_quantity']} {forecast_summary['unit']}")
    f2.metric("Average daily usage", f"{forecast_summary['daily_usage']} {forecast_summary['unit']}/day")
    f3.metric("Estimated depletion", forecast_summary["estimated_depletion_date"])

    chart_df = forecast_df.pivot(index="date", columns="type", values="quantity")
    st.line_chart(chart_df, use_container_width=True)

    days_remaining = forecast_summary["days_remaining"]
    if days_remaining is not None:
        if days_remaining <= 7:
            st.error(f"⚠️ {forecast_item['name']} may run out in {days_remaining} days.")
        elif days_remaining <= 14:
            st.warning(f" {forecast_item['name']} may run out in {days_remaining} days.")
        else:
            st.success(f"{forecast_item['name']} should last about {days_remaining} days.")

    st.markdown("### Forecast summary for all substances")
    st.dataframe(
        build_forecast_summary(st.session_state.inventory),
        use_container_width=True,
        hide_index=True,
    )

with tab_alerts:
    st.subheader("Safety and expiration alerts")

    alerts = get_expiry_alerts(st.session_state.inventory, days_threshold=45)

    checked_out_items = [
        {
            "name": item["name"],
            "status": item["status"],
            "location": item["location"],
            "hazard": item["hazard"],
        }
        for item in st.session_state.inventory.values()
        if item["status"] == "Checked out"
    ]

    forecast_summary_df = build_forecast_summary(st.session_state.inventory)
    low_stock_df = forecast_summary_df[
        forecast_summary_df["Days remaining"].apply(lambda x: x is not None and x <= 14)
    ]

    if not alerts and not checked_out_items and low_stock_df.empty:
        st.success("No current alerts.")
    else:
        if alerts:
            st.markdown("#### Expiration alerts")
            st.dataframe(pd.DataFrame(alerts), use_container_width=True, hide_index=True)

        if checked_out_items:
            st.markdown("#### Checked-out substances")
            checked_out_df = pd.DataFrame(checked_out_items)
            
            def highlight_checked_out(val):
                return 'background-color: #ffcccc; color: #cc0000; font-weight: bold;' if val == 'Checked out' else ''
                
            styled_checked_out_df = checked_out_df.style.map(highlight_checked_out, subset=['status'])
            
            st.dataframe(
                styled_checked_out_df,
                use_container_width=True,
                hide_index=True,
            )

        if not low_stock_df.empty:
            st.markdown("#### Mock low-stock forecast alerts")
            st.dataframe(low_stock_df, use_container_width=True, hide_index=True)

with tab_events:
    st.subheader("RFID events log")
    events_df = load_events()

    if events_df.empty:
        st.info("No events recorded yet.")
    else:
        st.dataframe(
            events_df.sort_values("Taken At", ascending=False),
            use_container_width=True,
            hide_index=True,
        )

with tab_voice:
    st.subheader("Voice assistant mock")
    st.write(
        "This section simulates future speech recognition. "
        "For now, type a command as if it had been transcribed from voice."
    )

    command = st.text_input(
        "Command",
        placeholder="Examples: where is acetone, missing items, expiring soon, when will ethanol run out",
    )

    if command:
        cmd = command.lower().strip()

        if "where is" in cmd:
            item_name = cmd.replace("where is", "").strip()
            matches = [
                item for item in st.session_state.inventory.values()
                if item_name in item["name"].lower()
            ]

            if matches:
                item = matches[0]
                st.success(
                    f"{item['name']} is located in {item['location']} "
                    f"and is currently {item['status']}."
                )
            else:
                st.warning("No matching substance found.")

        elif "missing" in cmd or "checked out" in cmd:
            missing = [
                item["name"]
                for item in st.session_state.inventory.values()
                if item["status"] == "Checked out"
            ]

            if missing:
                st.warning("Currently checked out: " + ", ".join(missing))
            else:
                st.success("No substances are currently checked out.")

        elif "expiring" in cmd or "expiry" in cmd:
            alerts = get_expiry_alerts(st.session_state.inventory, days_threshold=45)
            if alerts:
                names = [f"{a['name']} ({a['expiry_date']})" for a in alerts]
                st.warning("Expiring or expired substances: " + ", ".join(names))
            else:
                st.success("No substances are expiring soon.")

        elif "run out" in cmd or "finish" in cmd or "terminate" in cmd:
            matched = None
            for item in st.session_state.inventory.values():
                if item["name"].lower() in cmd:
                    matched = item
                    break

            if matched:
                _, summary = build_mock_forecast(matched)
                st.info(
                    f"Mock prediction: {matched['name']} will run out around "
                    f"{summary['estimated_depletion_date']} "
                    f"({summary['days_remaining']} days remaining)."
                )
            else:
                st.warning("Specify a substance name, for example: 'when will ethanol run out'.")

        else:
            st.info(
                "Command not recognized. Try: 'where is acetone', "
                "'missing items', 'expiring soon', or 'when will ethanol run out'."
            )

with tab_architecture:
    st.subheader("Prototype architecture")

    st.markdown(
        """
        ```text
        Current demo without board
        ──────────────────────────
        Simulated RFID button
                ↓
        inventory_logic.py
                ↓
        Streamlit dashboard
                ↓
        forecast_mock.py
                ↓
        Mock depletion chart + events_log.csv


        Future version with Arduino UNO Q
        ────────────────────────────────
        RC522 RFID reader + sensors
                ↓
        Arduino UNO Q MCU side
                ↓
        App Lab / Bridge
                ↓
        Python inventory logic
                ↓
        Real prediction model
                ↓
        Local dashboard + optional Telegram / Arduino Cloud
        ```
        """
    )

    st.write(
        "The dashboard is intentionally hardware-independent. "
        "To connect real hardware later, replace the simulated button events "
        "with real RFID tag IDs coming from Arduino UNO Q. To connect the real forecasting model, replace the mocked function in `forecast_mock.py` with the model output."
    )
