# game/definitions/classes.py
"""
Defines class-specific data like starting skill bonuses, equipment permissions, etc.
"""
import logging
from typing import Dict, List, Set, Optional

log = logging.getLogger(__name__) # Assuming logging is configured.

# --- Initial SKill Bonuses ---

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

}

CLASS_STARTING_ABILITIES: Dict[str, Dict[str, List[str]]] = {
    # Using separate lists for 'spells' vs 'abilities'
    "warrior": {
        "spells": [],
        "abilities": ["power strike", "shield bash", "toughness"] # Example placeholder names
    },
    "mage": {
        "spells": ["magic missile", "lesser shield", "ice bolt", "flame bolt"], # Example placeholder names
        "abilities": []
    },
    "cleric": {
        "spells": ["minor heal", "smite", "bless"], # Example placeholder names
        "abilities": ["turn undead"] # Example placeholder names
    },
    "rogue": {
        "spells": [],
        "abilities": ["sneak attack", "evasion", "feint"] # Example placeholder names
    },
}


# --- Helper Functions ---
def get_starting_skill_bonuses(class_name: Optional[str]) -> Dict[str, int]:
    """Gets starting skill bonuses for a class."""
    if not class_name: return {}
    return CLASS_STARTING_SKILL_BONUSES.get(class_name.lower(), {})

def get_starting_spells(class_name: Optional[str]) -> List[str]:
    """Gets the list of starting spell names for a class."""
    if not class_name: return []
    return CLASS_STARTING_ABILITIES.get(class_name.lower(), {}).get("spells", [])

def get_starting_abilities(class_name: Optional[str]) -> List[str]:
    """Gets the list of starting ability names for a class."""
    if not class_name: return []
    return CLASS_STARTING_ABILITIES.get(class_name.lower(), {}).get("abilities", [])