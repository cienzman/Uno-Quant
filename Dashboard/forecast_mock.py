from __future__ import annotations

from datetime import date, timedelta
import random
import pandas as pd


import math

def build_mock_forecast(item: dict, history_days: int = 21, forecast_days: int = 30):
    """
    Probabilistic consumption forecast based on Bayesian posterior.
    """
    today = date.today()

    current_quantity = float(item.get("predicted_quantity", 100))
    capacity = float(item.get("capacity", max(current_quantity, 100)))
    unit = item.get("unit", "")
    
    rate_mean = float(item.get("rate_mean", 5))
    rate_var = float(item.get("rate_var", 1))
    rate_std = math.sqrt(rate_var)
    sessions_per_day = float(item.get("sessions_per_day", 1))
    
    daily_usage_mean = rate_mean * sessions_per_day
    daily_usage_upper = (rate_mean + rate_std) * sessions_per_day
    daily_usage_lower = max(0.0, (rate_mean - rate_std) * sessions_per_day)

    rows = []
    # Reconstruct history using daily_usage_mean
    start_quantity = min(capacity, current_quantity + daily_usage_mean * history_days)
    random.seed(item.get("name", "default"))

    for i in range(history_days, 0, -1):
        day = today - timedelta(days=i)
        expected = start_quantity - daily_usage_mean * (history_days - i)
        noise = random.uniform(-daily_usage_mean * 0.35, daily_usage_mean * 0.35)
        quantity = max(0, min(capacity, expected + noise))
        rows.append({
            "date": day,
            "quantity": round(quantity, 2),
            "type": "Historical quantity",
        })

    # Add today's point for all lines to connect nicely
    for t in ["Expected quantity", "Pessimistic (fast depletion)", "Optimistic (slow depletion)"]:
        rows.append({
            "date": today,
            "quantity": round(current_quantity, 2),
            "type": t,
        })

    depletion_date = None
    for i in range(1, forecast_days + 1):
        day = today + timedelta(days=i)
        
        # Expected
        predicted = max(0, current_quantity - daily_usage_mean * i)
        rows.append({
            "date": day,
            "quantity": round(predicted, 2),
            "type": "Expected quantity",
        })
        if predicted <= 0 and depletion_date is None:
            depletion_date = day
            
        # Pessimistic (Upper usage)
        predicted_pessimistic = max(0, current_quantity - daily_usage_upper * i)
        rows.append({
            "date": day,
            "quantity": round(predicted_pessimistic, 2),
            "type": "Pessimistic (fast depletion)",
        })
        
        # Optimistic (Lower usage)
        predicted_optimistic = max(0, current_quantity - daily_usage_lower * i)
        rows.append({
            "date": day,
            "quantity": round(predicted_optimistic, 2),
            "type": "Optimistic (slow depletion)",
        })

    if daily_usage_mean > 0:
        days_remaining = int(current_quantity // daily_usage_mean)
        depletion_date = depletion_date or today + timedelta(days=days_remaining)
    else:
        days_remaining = None

    summary = {
        "residual_quantity": round(current_quantity, 2),
        "daily_usage": round(daily_usage_mean, 2),
        "unit": unit,
        "estimated_depletion_date": depletion_date.isoformat() if depletion_date else "N/A",
        "days_remaining": days_remaining,
    }

    return pd.DataFrame(rows), summary


def build_forecast_summary(inventory: dict) -> pd.DataFrame:
    rows = []
    for tag_id, item in inventory.items():
        _, summary = build_mock_forecast(item)
        rows.append({
            "Tag ID": tag_id,
            "Name": item["name"],
            "Residual quantity": f"{summary['residual_quantity']} {summary['unit']}",
            "Average expected daily usage": f"{summary['daily_usage']} {summary['unit']}/day",
            "Estimated depletion date": summary["estimated_depletion_date"],
            "Days remaining": summary["days_remaining"],
            "Location": item["location"],
        })
    return pd.DataFrame(rows)
