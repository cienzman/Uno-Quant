import json
import os
import fcntl

STATE_FILE = os.path.join(os.path.dirname(__file__), "voice_state.json")

def _read_state():
    if not os.path.exists(STATE_FILE):
        return {
            "pending_tag_id": None,
            "pending_item_name": None,
            "feedback_resolved": False,
            "resolved_level": None,
        }
    with open(STATE_FILE, "r") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_SH)
            data = json.load(f)
            fcntl.flock(f, fcntl.LOCK_UN)
            return data
        except Exception:
            return {
                "pending_tag_id": None,
                "pending_item_name": None,
                "feedback_resolved": False,
                "resolved_level": None,
            }

def _write_state(state):
    with open(STATE_FILE, "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        json.dump(state, f)
        fcntl.flock(f, fcntl.LOCK_UN)

def set_pending_feedback(tag_id: str, item_name: str):
    state = _read_state()
    state["pending_tag_id"] = tag_id
    state["pending_item_name"] = item_name
    state["feedback_resolved"] = False
    state["resolved_level"] = None
    _write_state(state)

def get_pending_feedback() -> dict:
    return _read_state()

def mark_resolved(level: str):
    state = _read_state()
    state["feedback_resolved"] = True
    state["resolved_level"] = level
    state["pending_tag_id"] = None
    _write_state(state)

def clear():
    state = _read_state()
    state["pending_tag_id"] = None
    state["pending_item_name"] = None
    state["feedback_resolved"] = False
    state["resolved_level"] = None
    _write_state(state)
