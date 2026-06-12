from __future__ import annotations

from datetime import datetime, date
from typing import Dict, Any, Tuple


def count_statuses(inventory: Dict[str, Dict[str, Any]]) -> Dict[str, int]:
    """
    Calculate the total count of each substance status in the current inventory.

    Args:
        inventory (Dict[str, Dict[str, Any]]): A dictionary representing the current 
            inventory state, keyed by RFID tag ID.

    Returns:
        Dict[str, int]: A dictionary mapping status strings (e.g., "Present", 
            "Checked out", "Missing") to their respective occurrence counts.
    """
    statuses = {"Present": 0, "Checked out": 0, "Missing": 0}
    for item in inventory.values():
        statuses[item["status"]] = statuses.get(item["status"], 0) + 1
    return statuses


def get_expiry_alerts(inventory: Dict[str, Dict[str, Any]], days_threshold: int = 45):
    """
    Identify and return a list of inventory items that are expired or approaching expiration.

    Args:
        inventory (Dict[str, Dict[str, Any]]): The current inventory dictionary.
        days_threshold (int, optional): The threshold in days to trigger an 'Expiring soon' alert. 
            Defaults to 45 days.

    Returns:
        list[dict]: A list of alert dictionaries, each containing the item's tag_id, name, 
            expiry_date, days_left, severity ("Expired" or "Expiring soon"), and location.
    """
    today = date.today()
    alerts = []

    for tag_id, item in inventory.items():
        if item.get("expiry_date") in (None, "N/A", ""):
            continue
        
        try:
            expiry = date.fromisoformat(item["expiry_date"])
        except ValueError:
            # Skip records with invalid date formats gracefully
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
    """
    Filter the inventory based on a user-provided search query.

    The search is case-insensitive and matches against multiple fields including 
    name, chemical formula, location, hazard classification, and RFID tag ID.

    Args:
        inventory (Dict[str, Dict[str, Any]]): The current inventory dictionary.
        query (str): The search string provided by the user.

    Returns:
        Dict[str, Dict[str, Any]]: A filtered dictionary containing only the items 
            that match the search criteria. Returns the original inventory if the query is empty.
    """
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
