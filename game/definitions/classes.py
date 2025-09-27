# game/definitions/classes.py
"""
Defines class-specific data like starting skill bonuses, equipment permissions, etc.
"""
import logging
from typing import Dict, List, Set, Optional

log = logging.getLogger(__name__) # Assuming logging is configured.

    # Define Hit Dice size per class ID {class_id: die_size}
CLASS_HP_DIE = {
    1: 10,  # Warrior: d10
    2: 4,   # Mage: d4
    3: 8,   # Cleric: d8
    4: 6,   # Rogue: d6
    5: 8,   # Ranger
    6: 12,  # Barbarian: d12
    7: 8,   # Druid: d8
    8: 6,   # Bard d6
}
DEFAULT_HP_DIE = 6 # Default if class not found

CLASS_ESSENCE_DIE = {
    1: 2,   # Warrior: d4
    2: 10,  # Mage: d10
    3: 8,   # Cleric: d8 (Assuming standard progression)
    4: 4,   # Rogue: d6 (Assuming standard progression)
    5: 4,   # Ranger
    6: 2,   # Barbarian: d4
    7: 6,   # Druid: d6,
    8: 8,   # Bard: d8
}
DEFAULT_ESSENCE_DIE = 4 # Default if class not found

# --- Initial Skill Bonuses ---
# Maps lowercase class name to {lowercase skill_name: bonus_rank}
CLASS_STARTING_SKILL_BONUSES: Dict[str, Dict[str, int]] = {
    "warrior": {
        "bladed weapons": 5,
        "bludgeon weapons": 5,
        "piercing weapons": 5,
        "shield usage": 5,
        "armor training": 5,
        "athletics": 3,
        "swimming": 3,
    },
    "mage": {
        "spellcraft": 5,
        "magical devices": 5,
        "concentration": 5,
        "bladed weapons": 1,
        "perception": 3,
        "runecraft": 3,
    },
    "cleric": {
        "piety": 5,
        "bludgeon weapons": 3, # Mace/Hammer archetype
        "shield usage": 3,
        "armor training": 2,
        "first aid": 5,
        "concentration": 5,
    },
    "rogue": {
        "stealth": 5,
        "pickpocket": 5,
        "lockpicking": 5,
        "disable device": 3,
        "piercing weapons": 3, # Dagger archetype
        "acrobatics": 3,
        "climbing": 3,
    },
    "ranger": {
        "projectile weapons": 5,
        "piercing weapons": 3, # For daggers
        "stealth": 3,
        "first aid": 3,
        "perception": 5,
        "athletics": 3,
    },
    "barbarian": {
        "two-handed weapons": 5,
        "bludgeon weapons": 5,
        "bladed weapons": 5,
        "athletics": 5,
        "armor training": 1, 
        "perception": 3
    },
    "druid": {
        "bludgeon weapons": 3,
        "perception": 5,
        "piety": 5,
        "concentration": 3,
        "first aid": 3,
        "climbing": 5,
        "swimming": 5,
    },
    "bard": {
        "performance": 5,
        "perception": 5,
        "bladed weapons": 3,
        "projectile weapons": 3,
        "concentration": 3,
        "acrobatics": 3,
    },

}

# --- Helper Functions ---
def get_starting_skill_bonuses(class_name: Optional[str]) -> Dict[str, int]:
    """Gets starting skill bonuses for a class."""
    if not class_name: return {}
    return CLASS_STARTING_SKILL_BONUSES.get(class_name.lower(), {})