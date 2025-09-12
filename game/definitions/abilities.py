# game/definitions/abilities.py
"""
Defines data for spells and abilities available in the game.
Keys in ABILITIES_DATA are lowerecase internal names used in commands/storage.
"""
import logging
from typing import Dict, List, Any, Optional
from ..definitions import abilities as ability_defs

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
EFFECT_MODIFIED_ATTACK = "MODIFIED_ATTACK" # For abilities like power strike
EFFECT_STUN_ATTEMPT = "STUN_ATTEMPT"
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
DAMAGE_DIVINE = "divine"
DAMAGE_POISON = "poison"
DAMAGE_SONIC = "sonic"

# --- Constants for Stats Affected by Buff/Debuff ---
STAT_ARMOR_VALUE = "armor_value"
STAT_BARRIER_VALUE = "barrier_value" # NEW: For Mage Armor / Magic defense
STAT_DODGE_VALUE = "dodge_value"
STAT_ROUNDTIME = "roundtime" # For stun/slow effects
STAT_MIGHT = "might"
STAT_VITALITY = "vitality"
STAT_AGILITY = "agility"
STAT_INTELLECT = "intellect"
STAT_AURA = "aura"
STAT_PERSONA = "persona"

 # etc. for base stats

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
    "rallying cry": {
        "name": "Rallying Cry",
        "type": "ABILITY",
        "class_req": ["warrior"],
        "level_req": 7,
        "cost": 15,
        "target_type": TARGET_AREA, # It affects an area
        "effect_type": EFFECT_BUFF,
        "effect_details": {
            "name": "Rally",
            "type": "buff",
            "aoe_target_scope": "allies", # It only affects group members
            "stat_affected": "max_hp", # A new type of buff!
            "amount": 20,
            "duration": 30.0
        },
        "roundtime": 3.0,
        "description": "Unleash a powerful shout, temporarily bolstering the health of all group members in the room.",
        "apply_msg_room": "{C{caster_name} lets out a powerful rallying cry!{x"
    },
    "power strike": {
        "name": "Power Strike", "type": "ABILITY", "class_req": ["warrior"], "level_req": 1,
        "cost": 0, "target_type": TARGET_CHAR_OR_MOB, # Target for the attack
        "cast_time": 0.0, # Instant activation
        "effect_type": EFFECT_MODIFIED_ATTACK, # Special type for combat system
        "effect_details": {
            "mar_modifier_mult": 0.75, # 75% of normal MAR (25% penalty)
            "rng_damage_mult": 2.0, # Double the weapon's random damage component
            "bonus_rt": 0.5, # Add 0.5s to the weapon's speed for final roundtime
            "school": "Physical"
        },
        "roundtime": 0.0, # Base RT applied is weapon speed + bonus_rt
        "description": "A mighty blow sacrificing accuracy for power. Uses your wielded weapon."
    },
    "shield bash": {
        "name": "Shield Bash", "type": "ABILITY", "class_req": ["warrior", "cleric"], "level_req": 3,
        "cost": 0, "target_type": TARGET_CHAR_OR_MOB,
        "cast_time": 0.0, # Instant activation
        "effect_type": EFFECT_STUN_ATTEMPT, # Special type for combat system
        "effect_details": {
            "mar_modifier_mult": 0.5, # 50% MAR penalty to hit with the bash
            "stun_chance": 0.20, # 20% chance to stun if the bash hits
            "stun_duration": 5.0, # Adds 5s roundtime to target if stun succeeds
            "requires_shield": True, # Logic check needed in cmd/resolution
            "school": "Physical"
        },
        "roundtime": 2.5, # RT applied to user after attempting bash
        "description": "Attempt to daze an opponent with your shield, potentially stunning them. Less accurate than a normal attack. (Requires Shield equipped)."
    },
    "cleave": {
        "name": "Cleave",
        "type": "ABILITY",
        "class_req": ["warrior"],
        "level_req": 12,
        "cost": 20,
        "target_type": TARGET_MOB, # The player must select a primary target
        "effect_type": EFFECT_MODIFIED_ATTACK,
        "effect_details": {
            "is_cleave": True,
            "max_cleave_targets": 3, # Hits the primary target + 2 others
            # All targets hit by cleave take 75% of normal weapon damage
            "damage_multiplier": 0.75 
        },
        "roundtime": 4.0,
        "description": "A wide, sweeping attack that strikes your primary target and up to two other enemies in the room for reduced damage.",
        "messages": {
            "caster_self": "You swing your weapon in a wide arc, striking multiple foes!",
            "room": "{caster_name} swings their weapon in a wide arc, striking multiple foes!"
        }
    },

    # == MAGE ==
    "magic missile": {
        "name": "Magic Missile", "type": "SPELL", "class_req": ["mage"], "level_req": 1,
        "cost": 1, "target_type": TARGET_CHAR_OR_MOB,
        "cast_time": 1.5, # Example: Takes 1.5s to cast before firing
        "effect_type": EFFECT_DAMAGE,
        "effect_details": {"damage_base": 2, "damage_rng": 4, "damage_type": DAMAGE_ARCANE, "school": "Arcane", "always_hits": True},
        "roundtime": 1.0, # RT applied AFTER spell fires
        "description": "A missile of pure arcane energy unerringly strikes your target."
    },
    "mage armor": {
        "name": "Mage Armor", "type": "SPELL", "class_req": ["mage"], "level_req": 1,
        "cost": 5, "target_type": TARGET_SELF, "cast_time": 2.0,
        "effect_type": EFFECT_BUFF,
        "effect_details": {"name": "MageArmorBuff", "type": "buff", "stat_affected": STAT_BARRIER_VALUE, "amount": 15, "duration": 180.0},
        "description": "Surrounds you with a shimmering field...",
        "apply_msg_self": "{{WAn shimmering barrier surrounds you!{{x", # {W -> {{W, {x -> {{x
        "apply_msg_target": None,
        "apply_msg_room": "{{W{caster_name} is suddenly surrounded by a shimmering barrier.{{x", 
        "expire_msg_self": "{{WThe shimmering barrier around you dissipates.{{x",
        "expire_msg_room": "{{WThe shimmering barrier surrounding {target_name} dissipates.{{x", 
        # --- ^ ^ ^ ---
    },
    # == CLERIC ==
    "minor heal": {
        "name": "Minor Heal", "type": "SPELL", "class_req": ["cleric"], "level_req": 1,
        "cost": 4, "target_type": TARGET_CHAR_OR_MOB,
        "cast_time": 2.0, # Takes time to invoke
        "effect_type": EFFECT_HEAL,
        "effect_details": {"heal_base": 5, "heal_rng": 6},
        "roundtime": 1.5, # RT applied AFTER spell fires
        "description": "A simple divine plea to mend minor wounds."
    },
    "smite": {
        "name": "Smite", "type": "SPELL", "class_req": ["cleric"], "level_req": 1,
        "cost": 2, "target_type": TARGET_CHAR_OR_MOB, # Changed to allow vs players too
        "cast_time": 1.5, # Takes time to invoke
        "effect_type": EFFECT_DAMAGE,
        "effect_details": {"damage_base": 2, "damage_rng": 6, "damage_type": DAMAGE_DIVINE, "school": "Divine"},
        "roundtime": 2.0, # RT applied AFTER spell fires
        "description": "Calls down divine energy to strike your foe."
    },
    "resurrect": {
        "name": "Resurrect",
        "type": "SPELL",
        "class_req": ["cleric"],
        "level_req": 20,
        "cost": 100,
        "target_type": TARGET_CHAR,
        "effect_type": "RESURRECT",
        "cast_time": 30.0,
        "roundtime": 10.0,
        "effect_details": {
            # Change from component to XP cost
            "xp_cost": 5000 
        },
        "description": "A powerful plea to restore a soul to its body, preventing tether loss. This ritual costs the caster some of their own life experience."
    },
    # == ROGUE ==
    "backstab": {
      "name": "Backstab",
      "type": "ABILITY",
      "class": "Rogue",
      "level_req": 3,
      "cost": 15,
      "roundtime": 3.0,
      "target_type": ability_defs.TARGET_MOB,
      "effect_type": ability_defs.EFFECT_MODIFIED_ATTACK,
      "effect_details": {
          # Custom flags for our combat logic
          "requires_stealth_or_flank": True,
          "damage_multiplier": 3.0
      },
      "messages": {
        "caster_self": "You slip behind {target_name} and drive your weapon home!",
        "room": "{caster_name} slips behind {target_name} and viciously attacks!"
      }
    },
    "quick reflexes": {
        "name": "Quick Reflexes", "type": "ABILITY", "class_req": ["rogue"], "level_req": 1,
        "cost": 3, "target_type": TARGET_SELF, "cast_time": 0.0,
        "effect_type": EFFECT_BUFF,
        "effect_details": {"name": "QuickReflexBuff", "type": "buff", "stat_affected": STAT_DODGE_VALUE, "amount": 5, "duration": 15.0},
        "roundtime": 1.0,
        "description": "Heightens your awareness...",
        "apply_msg_self": "{{GYou feel your reflexes quicken!{{x",
        "apply_msg_target": None,
        "apply_msg_room": "{{G{caster_name} seems to move with sudden alertness.{{x",
        "expire_msg_self": "{{GYour heightened reflexes return to normal.{{x",
        "expire_msg_room": "{{G{target_name} seems less twitchy.{{x",
    },
    "apply poison": {
        "name": "Apply Poison",
        "type": "ABILITY",
        "class_req": ["rogue"],
        "level_req": 2,
        "cost": 10,
        "roundtime": 3.0,
        "target_type": TARGET_SELF, # This ability affects the rogue's next attack
        "effect_type": EFFECT_BUFF,
        "effect_details": {
            "name": "Venom Coat",
            "type": "buff", # This is a buff that enables a poison attack
            "duration": 60.0,
            "potency": 5 # This will be the poison's damage per tick
        },
        "description": "Applies a basic poison to your wielded weapon for 60 seconds. Your next successful attack will poison the target.",
        "apply_msg_self": "{gYou carefully apply a thin coat of poison to your weapon.{x"
    },
}

# Helper function to get data safely
def get_ability_data(name: str) -> Optional[Dict[str, Any]]:
    """
    Gets the data dictionary for a given spell/ability name (case-insensitive).
    Returns None if not found.
    """
    return ABILITIES_DATA.get(name.lower())