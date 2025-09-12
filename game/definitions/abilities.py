# game/definitions/abilities.py
"""
Defines data for spells and abilities available in the game.
Keys in ABILITIES_DATA are lowerecase internal names used in commands/storage.
"""
import logging
from typing import Dict, List, Any, Optional, TYPE_CHECKING
from ..definitions import abilities as ability_defs

if TYPE_CHECKING:
    from ..world import World


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
    "defensive stance": {
        "name": "Defensive Stance",
        "type": "ABILITY",
        "class_req": ["warrior"],
        "level_req": 18,
        "cost": 10, # Essence cost to enter the stance
        "target_type": TARGET_SELF,
        "effect_type": EFFECT_BUFF,
        "effect_details": {
            "is_stance": True,
            # This "meta-effect" will apply two separate effects
            "effects_to_apply": [
                {"name": "DefStanceAV", "type": "buff", "stat_affected": "bonus_av", "amount": 25, "duration": -1},
                {"name": "DefStanceMAR", "type": "debuff", "stat_affected": "bonus_mar", "amount": -15, "duration": -1}
            ]
        },
        "roundtime": 1.5,
        "description": "Assume a defensive posture, greatly increasing armor at the cost of accuracy. Use the ability again to exit the stance."
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
    "chill touch": {
        "name": "Chill Touch",
        "type": "SPELL",
        "class_req": ["mage"],
        "level_req": 6,
        "cost": 8,
        "target_type": TARGET_CHAR_OR_MOB,
        "cast_time": 2.0,
        "effect_type": EFFECT_DAMAGE,
        "effect_details": {
            "damage_base": 4,
            "damage_rng": 4,
            "damage_type": DAMAGE_COLD,
            "school": "Arcane",
            # This "rider" effect is applied on a successful hit
            "applies_effect": {
                "name": "Chilled", "type": "slow", "duration": 8.0, "potency": 0.5
            }
        },
        "roundtime": 1.5,
        "description": "A touch of frigid energy damages your target and leaves them slowed."
    },
    "burning hands": {
        "name": "Burning Hands",
        "type": "SPELL",
        "class_req": ["mage"],
        "level_req": 14,
        "cost": 25,
        "target_type": TARGET_MOB, # Player selects a primary target
        "cast_time": 3.0,
        "effect_type": EFFECT_DAMAGE,
        "effect_details": {
            "is_cone_aoe": True,
            "max_aoe_targets": 3,
            "damage_base": 15,
            "damage_rng": 10,
            "damage_type": DAMAGE_FIRE,
            "school": "Arcane"
        },
        "roundtime": 3.0,
        "description": "A fan of flames erupts from your hands, scorching your target and up to two other nearby enemies."
    },
    "fireball": {
        "name": "Fireball",
        "type": "SPELL",
        "class_req": ["mage"],
        "level_req": 22,
        "cost": 40,
        "target_type": TARGET_AREA, # <-- This is the key
        "cast_time": 6.0,
        "effect_type": EFFECT_DAMAGE,
        "effect_details": {
            "aoe_target_scope": "enemies", # Hits all mobs in the room
            "damage_base": 25,
            "damage_rng": 15,
            "damage_type": DAMAGE_FIRE,
            "school": "Arcane"
        },
        "roundtime": 4.0,
        "description": "A massive explosion of fire that damages all enemies in the area."
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
     "bless": {
        "name": "Bless",
        "type": "SPELL",
        "class_req": ["cleric"],
        "level_req": 5,
        "cost": 12,
        "target_type": TARGET_CHAR_OR_MOB,
        "cast_time": 2.0,
        "effect_type": EFFECT_BUFF,
        "effect_details": {
            "effects_to_apply": [
                {"name": "BlessMAR", "type": "buff", "stat_affected": "bonus_mar", "amount": 5, "duration": 120.0},
                {"name": "BlessRAR", "type": "buff", "stat_affected": "bonus_rar", "amount": 5, "duration": 120.0}
            ]
        },
        "roundtime": 2.0,
        "description": "Fills an ally with divine favor, increasing their accuracy in combat.",
        "apply_msg_target": "{yYou feel blessed!{x"
    },
    "cure poison": {
        "name": "Cure Poison",
        "type": "SPELL",
        "class_req": ["cleric"],
        "level_req": 10,
        "cost": 15,
        "target_type": TARGET_CHAR_OR_MOB,
        "cast_time": 1.5,
        "effect_type": "CURE", # A new custom type for our logic
        "effect_details": {
            "cure_type": "poison" # Specifies what kind of effect to remove
        },
        "roundtime": 2.0,
        "description": "Neutralizes common poisons afflicting the target."
    },
    "circle of healing": {
        "name": "Circle of Healing",
        "type": "SPELL",
        "class_req": ["cleric"],
        "level_req": 16,
        "cost": 35,
        "target_type": TARGET_AREA,
        "cast_time": 3.0,
        "effect_type": EFFECT_HEAL,
        "effect_details": {
            "aoe_target_scope": "allies", # Heals all group members in the room
            "heal_base": 15,
            "heal_rng": 10
        },
        "roundtime": 4.0,
        "description": "A circle of golden light washes over your allies, mending their wounds."
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
    "trip": {
        "name": "Trip",
        "type": "ABILITY",
        "class_req": ["rogue"],
        "level_req": 8,
        "cost": 15,
        "target_type": TARGET_CHAR_OR_MOB,
        "effect_type": "CONTESTED_DEBUFF", # A new custom type for our logic
        "effect_details": {
            # Defines the skill contest
            "contest": {"attacker_skill": "acrobatics", "defender_skill": "acrobatics"},
            # Defines the effects to apply if the attacker wins
            "on_success": {
                "name": "Prone", "type": "stun", "duration": 3.0, "potency": 3.0,
                "set_stance": "Lying" # A new custom flag
            }
        },
        "roundtime": 2.0,
        "description": "Attempt to trip your opponent, knocking them prone and stunning them briefly."
    },
    "garrote": {
        "name": "Garrote",
        "type": "ABILITY",
        "class_req": ["rogue"],
        "level_req": 15,
        "cost": 25,
        "target_type": TARGET_CHAR_OR_MOB,
        "effect_type": EFFECT_DEBUFF,
        "effect_details": {
            "requires_stealth": True, # A new flag for the 'use' command
            # This ability will apply two separate effects
            "effects_to_apply": [
                {"name": "GarroteBleed", "type": "bleed", "duration": 9.0, "potency": 8, "stat_affected": "hp"},
                {"name": "GarroteSilence", "type": "silence", "duration": 6.0, "stat_affected": "none"}
            ]
        },
        "roundtime": 3.0,
        "description": "A vicious attack from the shadows that causes a deep bleeding wound and prevents spellcasting."
    },
}

# Helper function to get data safely
def get_ability_data(world: 'World', name: str) -> Optional[Dict[str, Any]]:
    """Gets ability data from the world cache."""
    return world.abilities.get(name.lower())