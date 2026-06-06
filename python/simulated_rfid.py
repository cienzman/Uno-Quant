import random

SIMULATED_TAGS = [
    "tag1",
    "tag2",
    "tag3",
    "tag4",
    "tag5",
    "tag999",
]


def get_random_scan() -> str:
    """Return a random simulated RFID tag."""
    return random.choice(SIMULATED_TAGS)


def get_named_tags():
    """Useful mapping for buttons in the dashboard."""
    return {
        "Scan Sodium Chloride": "tag1",
        "Scan Phosphate Buffered Saline": "tag2",
        "Scan Cholesterol": "tag3",
        "Scan Acetylamino": "tag4",
        "Scan Sodium Tripolyphosphate": "tag5",
        "Scan unknown tag": "tag999",
    }
