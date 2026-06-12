import random
from typing import Dict

# Pre-defined list of simulated RFID tag identifiers used for testing hardware-free environments.
SIMULATED_TAGS = [
    "tag1",
    "tag2",
    "tag3",
    "tag4",
    "tag5",
    "tag999",
]


def get_random_scan() -> str:
    """
    Select and return a random simulated RFID tag identifier.

    This is primarily used for stress testing the backend pipeline without requiring physical hardware.

    Returns:
        str: A randomly selected tag ID from the predefined SIMULATED_TAGS list.
    """
    return random.choice(SIMULATED_TAGS)


def get_named_tags() -> Dict[str, str]:
    """
    Provide a user-friendly mapping of physical substance names to their simulated RFID tags.

    This mapping is used extensively by the Streamlit dashboard to render 
    interactive testing buttons (e.g., 'Scan Sodium Chloride').

    Returns:
        Dict[str, str]: A dictionary mapping descriptive action labels to tag IDs.
    """
    return {
        "Scan Sodium Chloride": "tag1",
        "Scan Phosphate Buffered Saline": "tag2",
        "Scan Cholesterol": "tag3",
        "Scan Acetylamino": "tag4",
        "Scan Sodium Tripolyphosphate": "tag5",
        "Scan unknown tag": "tag999",
    }
