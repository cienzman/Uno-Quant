from __future__ import annotations

from datetime import datetime, date
from typing import Dict, Any, Tuple


def count_statuses(inventory: Dict[str, Dict[str, Any]]) -> Dict[str, int]:
    statuses = {"Present": 0, "Checked out": 0, "Missing": 0}
    for item in inventory.values():
        statuses[item["status"]] = statuses.get(item["status"], 0) + 1
    return statuses


def get_expiry_alerts(inventory: Dict[str, Dict[str, Any]], days_threshold: int = 45):
    today = date.today()
    alerts = []

    for tag_id, item in inventory.items():
        if item.get("expiry_date") in (None, "N/A", ""):
            continue
        
        try:
            expiry = date.fromisoformat(item["expiry_date"])
        except ValueError:
            continue
            
        days_left = (expiry - today).days

        if days_left < 0:
            severity = "Expired"
        elif days_left <= days_threshold:
            severity = "Expiring soon"
        else:
            continue

        alerts.append({
            "tag_id": tag_id,
            "name": item["name"],
            "expiry_date": item["expiry_date"],
            "days_left": days_left,
            "severity": severity,
            "location": item["location"],
        })

    return alerts


def search_inventory(inventory: Dict[str, Dict[str, Any]], query: str):
    query = query.strip().lower()
    if not query:
        return inventory

    return {
        tag_id: item
        for tag_id, item in inventory.items()
        if query in item["name"].lower()
        or query in item["chemical_formula"].lower()
        or query in item["location"].lower()
        or query in item["hazard"].lower()
        or query in tag_id.lower()
    }
