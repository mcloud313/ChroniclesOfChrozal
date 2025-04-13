# game/definitions/abilities.py
"""
Defines data for spells and abilities available in the game.
Keys in ABILITIES_DATA are lowerecase internal names used in commands/storage.
"""
import logging
from typing import Dict, List, Any, Optional

log = logging.getLogger(__name__)

# --- Constants for target types ---
TARGET_SELF  = "SELF"
TARGET_CHAR = "CHAR" # Player characters only
TARGET_MOB = "MOB" # Mobiles only
TARGET_CHAR_OR_MOB = "CHAR_OR_MOB" #Characters or mobiles
TARGET_AREA = "AREA" #Affects others in the room *excluding self)
TARGET_NONE = "NONE" # No target needed

# --- Constants for effects types ---
EFFECT_DAMAGE = "DAMAGE"
EFFECT_HEAL = "HEAL"
EFFECT_BUFF = "BUFF" #Positive temporary effect
EFFECT_DEBUFF = "DEBUFF" #Negative temporary effect
# Add more later: SUMMON, TELEPORT, UTILITY etc.

#--- Constants for damage types
DAMAGE_PHYSICAL = "physical"
DAMAGE_SLASH = "slash"
DAMAGE_PIERCE = "pierce"
DAMAGE_BLUDGEON = "bludgeon"
DAMAGE_FIRE = "fire"
DAMAGE_COLD = "cold"
DAMAGE_LIGHTNING = "lightning"
DAMAGE_EARTH = "earth"
DAMAGE_ARCANE = "arcane"
DAMAGE_DIVINE "divine"
DAMAGE_POISON = "poison"
DAMAGE_SONIC = "sonic"

# --- Ability/Spell Data Dictionary ---
# Structure:
# "internal_name": {
#     "name": "Display Name",
#     "type": "SPELL" | "ABILITY",
#     "class_req": ["classname1", "classname2"], # Lowercase, empty list for all classes
#     "level_req": int,
#     "cost": int, # Essence cost
#     "target_type": TARGET_SELF | TARGET_CHAR_OR_MOB | etc.,
#     "effect_type": EFFECT_DAMAGE | EFFECT_HEAL | etc.,
#     "effect_details": { ... }, # Varies based on effect_type
#     "roundtime": float,
#     # "cooldown": float, # Optional, for later
#     "description": "Help file / info description."
# }
ABILITIES_DATA: Dict[str, Dict[str, Any]] = {

    # == WARRIOR ==
    "power strike": {
        "name": "Power Strike", "type": "ABILITY", "class_req": ["warrior"], "level_req": 1,
        "cost": 0, "target_type": TARGET_CHAR_OR_MOB, "effect_type": EFFECT_DAMAGE,
        "effect_details": {"damage_base": 4, "damage_rng": 4, "damage_type": DAMAGE_PHYSICAL, "school": "Physicla"},
        "roundtime": 2.5, "description": "A mighty blow sacrificing speed for power. Requires a melee weapon." 
    },
    "shield bash": {
        "name": "Shield Bash", "type": "ABILITY", "class_req": ["warrior", "cleric"], "level_req": 3, # Level 3 example
        "cost": 0, "target_type": TARGET_CHAR_OR_MOB, "effect_type": EFFECT_DEBUFF,
        "effect_details": {"name": "BashStun", "stat_affected": "roundtime", "amount": 1.5, "duration": 1.6},
        "roundtime": 3.0, "description": "Attempt to briefly daze an opponent with your shield (Requires Shield equipped)."
    },

    # == MAGE ==
    "magic missile": {
        "name": "Magic Missile", "type": "SPELL", "class_req": ["mage"], "level_req": 1,
        "cost": 3, "target_type": TARGET_CHAR_OR_MOB, "effect_type": EFFECT_DAMAGE,
        "effect_details": {"damage_base": 2, "damage_rng": 4, "damage_type": DAMAGE_ARCANE, "school": "Arcane", "always_hits": True}, # Added always hits flag
        "roundtime": 2.0, "description": "A missile of pure arcane energy unerringly strikes your target."
    },
    "mage armor": { # Renamed from lesser shield
        "name": "Mage Armor", "type": "SPELL", "class_req": ["mage"], "level_req": 1,
        "cost": 5, "target_type": TARGET_SELF, "effect_type": EFFECT_BUFF,
        "effect_details": {"name": "MageArmorBuff", "stat_affected": "armor_value", "amount": 3, "duration": 180.0}, # +3 AV, 3 minutes
        "roundtime": 1.5, "description": "Surrounds you with a shimmering field of force that deflects blows."
    },

    # == CLERIC ==
    "minor heal": {
        "name": "Minor Heal", "type": "SPELL", "class_req": ["cleric"], "level_req": 1,
        "cost": 4, "target_type": TARGET_CHAR_OR_MOB, "effect_type": EFFECT_HEAL,
        "effect_details": {"heal_base": 5, "heal_rng": 6}, # 5 + d6 HP
        "roundtime": 2.0, "description": "A simple divine plea to mend minor wounds."
    },
    "smite": {
        "name": "Smite", "type": "SPELL", "class_req": ["cleric"], "level_req": 1,
        "cost": 2, "target_type": TARGET_MOB, # Typically specific types, but MOB for V1
        "effect_type": EFFECT_DAMAGE,
        "effect_details": {"damage_base": 2, "damage_rng": 6, "damage_type": DAMAGE_DIVINE, "school": "Divine"},
        "roundtime": 2.5, "description": "Calls down divine energy to strike your foe."
    },

        # == ROGUE ==
    "backstab attempt": {
        "name": "Backstab Attempt", "type": "ABILITY", "class_req": ["rogue"], "level_req": 1,
        "cost": 0, "target_type": TARGET_MOB,
        "effect_type": EFFECT_DAMAGE,
        "effect_details": {"damage_base": 4, "damage_rng": 8, "damage_type": DAMAGE_PIERCE, "school": "Physical", "requires_behind": True}, # High damage, requires position
        "roundtime": 3.5, "description": "Attempt a devastating attack from behind an opponent (Requires Piercing Weapon)."
    },
    "quick reflexes": {
        "name": "Quick Reflexes", "type": "ABILITY", "class_req": ["rogue"], "level_req": 1,
        "cost": 3, # Give it a small cost
        "target_type": TARGET_SELF, "effect_type": EFFECT_BUFF,
        "effect_details": {"name": "QuickReflexBuff", "stat_affected": "dodge_value", "amount": 5, "duration": 15.0}, # +5 DV, 15 seconds
        "roundtime": 1.0, "description": "Heightens your awareness, allowing you to dodge attacks more easily for a short time."
    },
}

# Helper function to get data safely
def get_ability_data(name: str) -> Optional[Dict[str, Any]]:
    """
    Gets the data dictionary for a given spell/ability name (case-insensitive).
    Returns None if not found.
    """
    return ABILITIES_DATA.get(name.lower())