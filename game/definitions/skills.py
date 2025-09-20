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
    "armor training": "vitality", # Characters don't get the full percentage of their AV unless they are past 50 ranks in Armor Training, past that they'll get a +1 Armor Value for every 10 ranks.
    "bartering": "persona", # Provides +1% profit for selling per 25 ranks, -1% off the total price for every 25 ranks
    "bladed weapons": "agility", # Provides more MAR for every 25 points
    "bludgeon weapons": "might", # Provides more MAR for every 25 points
    "climbing": "might", # Implemented for complex obstacles
    "conduit": "persona", #Grant a small APR/DPR bonus for your group
    "concentration": "intellect",  #Used to not let a spell fizzle when taking a hit
    "disable device": "intellect", #Used for Rogue Commands for disabling traps
    "dodge": "agility", # Provides 1 DV for every 25 points
    "first aid": "intellect", # TODO: Implement healing when out in the field using this skill
    "leadership": "persona", # Provides a small bonus to PDS/SDS for all group members
    "lockpicking": "agility", # Used for forcing locks for doors and chests
    "magical devices": "intellect",  #Used for wands, and scrolls that contain magical spells
    "martial arts": "agility",  # Provides more MAR for unarmed Strike for every 25 points
    "parrying": "agility", # Provides a small block chance from your weapon without using a shield
    "piercing weapons": "agility", # Provides more MAR for every 25 points
    "perception": "intellect",  # Used to find stealthed mobs or characters
    "pickpocket": "agility", # Used in an attempt to lift coins from humanoids
    "piety": "aura", # Used to increase your DPR more DPR for every 25 points
    "projectile weapons": "agility", # Provies more RAR for every 25 points
    "runecrafting": "intellect",  #TODO: Implement Runecrafting 
    "shield usage": "might", # Provides 1% block for every 25 points
    "spellcraft": "intellect", #Used to incresase APR for every 25 points
    "stealth": "agility", #Used in an attempt to hide from mobs and other players
    "tactics": "intellect", #Grant a small MAR/RAR boost to everyone in your group
    "swimming": "vitality", # Implemented for complex obstacles
    "warding": "aura", #Grant a small SDS bonus for your group
}

def get_attribute_for_skill(skill_name: str) -> Optional[str]:
    """Gets the governing attribute for a skill (lowercase)."""
    return SKILL_ATTRIBUTE_MAP.get(skill_name.lower())
