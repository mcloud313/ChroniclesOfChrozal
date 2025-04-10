# game/definitions/slots.py
"""
Defines constants for equipment slots.
"""

HEAD = "HEAD"
NECK = "NECK"
SHOULDERS = "SHOULDERS"
TORSO = "TORSO"
LEGS = "LEGS"
FEET = "FEET"
HANDS = "HANDS"
ARMS = "ARMS"
WAIST = "WAIST"
FINGER_L = "FINGER_L"
FINGER_R = "FINGER_R"
WRIST_L = "WRIST_L"
WRIST_R = "WRIST_R"
WIELD_MAIN = "WIELD_MAIN"
WIELD_OFF = "WIELD_OFF"
CLOAK = "CLOAK"
BACK = "BACK"

# List of all wearable slots (order might matter for display)
ALL_SLOTS = [
    HEAD, NECK, SHOULDERS, CLOAK, BACK, TORSO, WAIST, ARMS, WRIST_L, WRIST_R,
    HANDS, WIELD_MAIN, WIELD_OFF, FINGER_L, FINGER_R, LEGS, FEET
]

def is_valid_slot(slot_name: str) -> bool:
    return slot_name.upper() in ALL_SLOTS