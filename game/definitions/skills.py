# game/definitions/skills.py
"""
Defines available skills and their associated attributes.
"""
from typing import TYPE_CHECKING, Optional

# --- REMOVED ---
# The INITIAL_SKILLS list has been removed to prevent inconsistencies.
# The SKILL_ATTRIBUTE_MAP is now the single source of truth for all defined skills.

# Mapping from skill name (lowercase) to primary attribute name (lowercase)
SKILL_ATTRIBUTE_MAP = {
    "acrobatics": "agility",
    "athletics": "might",
    "armor training": "vitality",
    "bartering": "persona",
    "bladed weapons": "agility",
    "bludgeon weapons": "might",
    "climbing": "might",
    "conduit": "persona",
    "concentration": "intellect",
    "disable device": "intellect",
    "dodge": "agility",
    "first aid": "intellect",
    "leadership": "persona",
    "lockpicking": "agility",
    "magical devices": "intellect",
    "martial arts": "agility",
    "parrying": "agility",
    "piercing weapons": "agility",
    "perception": "intellect",
    "pickpocket": "agility",
    "piety": "aura",
    "projectile weapons": "agility",
    "runecrafting": "intellect",
    "shield usage": "might",
    "spellcraft": "intellect",
    "stealth": "agility",
    "swimming": "vitality",
    "tactics": "intellect",
    "warding": "aura",
}

def get_attribute_for_skill(skill_name: str) -> Optional[str]:
    """Gets the governing attribute for a skill (lowercase)."""
    return SKILL_ATTRIBUTE_MAP.get(skill_name.lower())