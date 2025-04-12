# game/definitions/skills.py
"""
Defines available skills and their associated attributes.
"""
from typing import TYPE_CHECKING, Optional

#List of all available skills (lowercase)
INITIAL_SKILLS = sorted([
    "acrobatics", "athletics", "armor training", "bartering", "bladed weapons", "bludgeon weapons", "climbing",
    "concentration", "disable device", "dodge", "first aid", "lockpicking", "magical devices", "martial arts", 
    "parrying", "piercing weapons", "perception", "pickpocket", "piety", "projectile weapons", "runecrafting",
    "shield usage", "spellcraft", "stealth", "swimming"
])

# Mapping from skill name (lowercase) to primary attribute name (lowercase)
# Adjust these based on your game design!
SKILL_ATTRIBUTE_MAP = {
    "acrobatics": "agility", # Implemented for complex obstacles
    "athletics": "might",   # Implemented for complex obstacles
    "armor training": "vitality", # Implemented for getting more of your total AV
    "bartering": "persona",
    "bladed weapons": "agility", # Provides more MAR for every 25 points
    "bludgeon weapons": "might", # Provides more MAR for every 25 points
    "climbing": "might", # Implemented for complex obstacles
    "concentration": "intellect", 
    "disable device": "intellect", 
    "dodge": "agility", # Provides 1 DV for every 25 points
    "first aid": "intellect",
    "lockpicking": "agility",
    "magical devices": "intellect", 
    "martial arts": "agility", 
    "parrying": "agility",
    "piercing weapons": "agility", # Provides more MAR for every 25 points
    "perception": "intellect", 
    "pickpocket": "agility",
    "piety": "aura", 
    "projectile weapons": "agility", # Provies more RAR for every 25 points
    "runecrafting": "intellect", 
    "shield usage": "might", # Provides 1% block for every 25 points
    "spellcraft": "intellect", 
    "stealth": "agility",
    "swimming": "vitality", # Implemented for complex obstacles
}

def get_attribute_for_skill(skill_name: str) -> Optional[str]:
    """Gets the governing attribute for a skill (lowercase)."""
    return SKILL_ATTRIBUTE_MAP.get(skill_name.lower())
