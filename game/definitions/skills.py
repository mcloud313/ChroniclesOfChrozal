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
    "acrobatics": "agility",
    "athletics": "might",
    "armor training": "vitality", # Skill reduces penalties? Base mod?
    "bartering": "persona",
    "bladed weapons": "agility", # Or might? Or average? Agility for finesse.
    "bludgeon weapons": "might", # Strength focus
    "climbing": "might", # Or agility? Might fits strength needed.
    "concentration": "intellect", # Or aura? Int for focus.
    "disable device": "intellect", # Or agility? Int for understanding.
    "dodge": "agility",
    "first aid": "intellect",
    "lockpicking": "agility",
    "magical devices": "intellect", # Using scrolls, wands etc.
    "martial arts": "agility", # Dexterity/speed focus for unarmed
    "parrying": "agility",
    "piercing weapons": "agility", # Dexterity focus
    "perception": "intellect", # Awareness, noticing details
    "pickpocket": "agility",
    "piety": "aura", # Connection to divine
    "projectile weapons": "agility", # Aiming bows, crossbows
    "runecrafting": "intellect", # Understanding runes
    "shield usage": "might", # Strength to hold/maneuver
    "spellcraft": "intellect", # Understanding magic theory (Mage) or aura (Cleric)? Let's use Intellect for general magic knowledge.
    "stealth": "agility",
    "swimming": "vitality", # Strength focus
}

def get_attribute_for_skill(skill_name: str) -> Optional[str]:
    """Gets the governing attribute for a skill (lowercase)."""
    return SKILL_ATTRIBUTE_MAP.get(skill_name.lower())
