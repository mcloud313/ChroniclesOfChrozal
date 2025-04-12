# game/definitions/races.py
"""
Defines race-specific data like stat modifiers.
"""
from typing import Dict

# Dictionary mapping race name (lowercase) to stat adjustments (multiples of 5)
# Positive values are bonuses, negative values are flaws.
RACIAL_STAT_MODIFIERS: Dict[str, Dict[str, int]] = {
    "chrozalin": {}, # Standard human - no adjustments
    "dwarf": {
        "vitality": 10,    # +5 Vitality (+1 Modifier)
        "persona": -5,    # -5 Persona (-1 Modifier)
        "agility": -5,    # -5 Agility (-1 Modifier) - Optional example
    },
    "elf": {
        "intellect": 5,     # +5 Agility (+1 Modifier)
        "vitality": -5,   # -5 Vitality (-1 Modifier)
    },
    "yan-tar": {          
        "aura": 5,   # +5 Intellect (+1 Modifier)
        "agility": -5,    # -5 Agility (-1 Modifier)
    },
    # Add other races later
}

def get_racial_modifiers(race_name: str) -> Dict[str, int]:
    """
    Safely gets the dictionary of stat modifiers for a given race name.
    Returns an empty dict if race not found.
    """
    return RACIAL_STAT_MODIFIERS.get(race_name.lower(), {})

def format_racial_modifiers(race_name: str) -> str:
    """Formats the racial modifiers into a nice string for display."""
    mods = get_racial_modifiers(race_name)
    if not mods:
        return "Your race provides no inherent advantages or disadvantages to your attributes."

    parts = []
    for stat, mod_val in mods.items():
        sign = "+" if mod_val > 0 else ""
        parts.append(f"{sign}{mod_val} {stat.capitalize()}")
    return f"As a {race_name.capitalize()}, you have the following racial attribute modifiers: {', '.join(parts)}."