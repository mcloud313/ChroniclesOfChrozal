# game/definitions/slots.py
"""
Defines constants for equipment slots.
"""
def is_valid_slot(slot_name: str) -> bool:
    return slot_name.upper() in ALL_SLOTS

# game/definitions/slots.py
"""
Central definition for all character equipment slots.
This provides a canonical order for display in commands.
"""

# --- SLOT CONSTANTS ---
WIELD_MAIN = "main_hand"
WIELD_OFF = "off_hand"

ARMOR_HEAD = "head"
ACCESSORY_NECK = "neck"
ARMOR_SHOULDERS = "shoulders"
ARMOR_TORSO = "torso"
ARMOR_LEGS = "legs"
ARMOR_FEET = "feet"
ARMOR_HANDS = "hands"
ARMOR_ARMS = "arms"

ACCESSORY_WAIST = "waist"
ACCESSORY_FINGER_L = "finger_l"
ACCESSORY_FINGER_R = "finger_r"
ACCESSORY_WRIST_L = "accessory_wrist_l"
ACCESSORY_WRIST_R = "accessory_wrist_r"
ACCESSORY_CLOAK = "accessory_cloak"
ACCESSORY_BACK = "back"

# --- CANONICAL LIST FOR DISPLAY ORDER ---
# Commands like 'look' and 'score' should iterate through this list
# to ensure a consistent and complete display of equipment.
ALL_SLOTS = [
    WIELD_MAIN,
    WIELD_OFF,
    ARMOR_HEAD,
    ACCESSORY_NECK,
    ARMOR_SHOULDERS,
    ARMOR_TORSO,
    ACCESSORY_BACK,
    ACCESSORY_CLOAK,
    ARMOR_ARMS,
    ARMOR_HANDS,
    ACCESSORY_WRIST_L,
    ACCESSORY_FINGER_L,
    ACCESSORY_WRIST_R,
    ACCESSORY_FINGER_R,
    ACCESSORY_WAIST,
    ARMOR_LEGS,
    ARMOR_FEET,
    
]