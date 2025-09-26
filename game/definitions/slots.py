# game/definitions/slots.py
"""
Central definition for all character equipment slots.
This provides a canonical, ordered list for saving and display commands.
"""

# --- SLOT CONSTANTS ---
# These are the string values that match your database columns.
WIELD_MAIN = "main_hand"
WIELD_OFF = "off_hand"
ARMOR_HEAD = "head"
ACCESSORY_NECK = "neck"
ARMOR_SHOULDERS = "shoulders"
ARMOR_TORSO = "torso"
ARMOR_ARMS = "arms"
ARMOR_HANDS = "hands"
ARMOR_LEGS = "legs"
ARMOR_FEET = "feet"
ACCESSORY_WAIST = "waist"
ACCESSORY_FINGER_L = "finger_l"
ACCESSORY_FINGER_R = "finger_r"
ACCESSORY_WRIST_L = "accessory_wrist_l"
ACCESSORY_WRIST_R = "accessory_wrist_r"
ACCESSORY_CLOAK = "accessory_cloak"
BACK = "back" # Simplified constant name for clarity

# --- CANONICAL LIST OF ALL SLOTS ---
# This list is the single source of truth for the entire saving system.
# The order also dictates the display order in commands like 'equipment'.
ALL_SLOTS = [
    WIELD_MAIN,
    WIELD_OFF,
    ARMOR_HEAD,
    ACCESSORY_NECK,
    ARMOR_SHOULDERS,
    ARMOR_TORSO,
    BACK,
    ACCESSORY_CLOAK,
    ARMOR_ARMS,
    ARMOR_HANDS,
    ACCESSORY_WRIST_L,
    ACCESSORY_WRIST_R,
    ACCESSORY_FINGER_L,
    ACCESSORY_FINGER_R,
    ACCESSORY_WAIST,
    ARMOR_LEGS,
    ARMOR_FEET,
]

def is_valid_slot(slot_name: str) -> bool:
    """
    Checks if a given slot name is a valid, defined equipment slot.
    This function is now defined *after* ALL_SLOTS and uses the correct case.
    """
    return slot_name.lower() in ALL_SLOTS