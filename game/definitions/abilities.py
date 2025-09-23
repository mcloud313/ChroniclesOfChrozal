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

MAGICAL_DAMAGE_TYPES = {"fire", "cold", "lightning", "earth", "arcane", "divine", "poison", "sonic"}


DAMAGE_ARCANE = "arcane"
DAMAGE_BLUDGEON = "bludgeon"
DAMAGE_COLD = "cold"
DAMAGE_DIVINE = "divine"
DAMAGE_FIRE = "fire"
DAMAGE_PIERCE = "pierce"
DAMAGE_SLASH = "slash"
DAMAGE_PHYSICAL = "physical"

# --- Constants for effects types ---
EFFECT_DAMAGE = "DAMAGE"
EFFECT_HEAL = "HEAL"
EFFECT_BUFF = "BUFF" #Positive temporary effect
EFFECT_DEBUFF = "DEBUFF" #Negative temporary effect
EFFECT_MODIFIED_ATTACK = "MODIFIED_ATTACK" # For abilities like power strike
EFFECT_STUN_ATTEMPT = "STUN_ATTEMPT"
# Add more later: SUMMON, TELEPORT, UTILITY etc.

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

# In game/definitions/abilities.py
# "messages": {
#     # Fired when the spell/ability is successfully cast, after cast_time.
#     "caster_self_complete": "A shimmering bolt flies from your hands!",
#     "room_complete": "{caster_name} launches a shimmering bolt!",

#     # Fired when a BUFF/DEBUFF effect is applied to the target.
#     "apply_msg_self": "You are surrounded by a shimmering barrier!",
#     "apply_msg_target": "{caster_name}'s spell surrounds you with a barrier.",
#     "apply_msg_room": "{target_name} is surrounded by a shimmering barrier.",

#     # Fired when a BUFF/DEBUFF effect expires.
#     "expire_msg_self": "The shimmering barrier around you dissipates.",
#     "expire_msg_room": "The shimmering barrier around {target_name} dissipates."
# }

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
        "name": "Rallying Cry", "type": "ABILITY", "class_req": ["warrior"], "level_req": 7,
        "cost": 15, "target_type": TARGET_AREA, "effect_type": EFFECT_BUFF,
        "effect_details": {
            "name": "Rally", "type": "buff", "aoe_target_scope": "allies",
            "stat_affected": "max_hp", "amount": 20, "duration": 30.0
        },
        "roundtime": 3.0, "description": "...",
        "messages": {
            "apply_msg_room": "{C{caster_name} lets out a powerful rallying cry, bolstering their allies!{x",
            "apply_msg_target": "{CYou feel heartened by the rallying cry!{x",
            "expire_msg_target": "{CThe effect of the rallying cry fades.{x"
        }
    },
    "power strike": {
        "name": "Power Strike", "type": "ABILITY", "class_req": ["warrior", "barbarian"], "level_req": 1,
        "cost": 10, "target_type": TARGET_CHAR_OR_MOB, "cast_time": 0.0,
        "effect_type": EFFECT_MODIFIED_ATTACK,
        "effect_details": { "damage_multiplier": 1.5 },
        "roundtime": 0.0, "description": "...",
        "messages": {
            "caster_self_complete": "{RYou gather your strength for a powerful strike!{x",
            "room_complete": "{R{caster_name} gathers their strength for a powerful strike!{x"
        }
    },
    "shield bash": {
        "name": "Shield Bash", "type": "ABILITY", "class_req": ["warrior", "cleric"], "level_req": 3,
        "cost": 5, "target_type": TARGET_CHAR_OR_MOB, "cast_time": 0.0,
        "effect_type": EFFECT_STUN_ATTEMPT,
        "effect_details": {
            "mar_modifier_mult": 0.8, "stun_chance": 0.25, "stun_duration": 3.0, "requires_shield": True
        },
        "roundtime": 2.5, "description": "...",
        "messages": {
            "caster_self_complete": "You slam your shield into {target_name}!",
            "room_complete": "{caster_name} slams their shield into {target_name}!"
        }
    },
    "cleave": {
        "name": "Cleave", "type": "ABILITY", "class_req": ["warrior", "barbarian"], "level_req": 12,
        "cost": 20, "target_type": TARGET_MOB, "effect_type": EFFECT_MODIFIED_ATTACK,
        "effect_details": { "is_cleave": True, "max_cleave_targets": 3, "damage_multiplier": 0.75 },
        "roundtime": 4.0, "description": "...",
        "messages": {
            "caster_self_complete": "You swing your weapon in a wide arc, striking multiple foes!",
            "room_complete": "{caster_name} swings their weapon in a wide arc, striking multiple foes!"
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
        "description": "A missile of pure arcane energy unerringly strikes your target.",
        "messages": {
            "caster_self_complete": "A shimmering bolt of arcane energy flies from your fingertips!",
            "room_complete": "{caster_name} launches a shimmering bolt of arcane energy!"
        }
    },
    "mage armor": {
        "name": "Mage Armor", "type": "SPELL", "class_req": ["mage"], "level_req": 1,
        "cost": 5, "target_type": TARGET_SELF, "cast_time": 2.0,
        "effect_type": EFFECT_BUFF,
        "effect_details": {"name": "MageArmorBuff", "type": "buff", "stat_affected": STAT_BARRIER_VALUE, "amount": 15, "duration": 180.0},
        "description": "Surrounds you with a shimmering field...",
        "messages": {
            "apply_msg_self": "{WAn shimmering barrier surrounds you!{x",
            "apply_msg_room": "{W{caster_name} is suddenly surrounded by a shimmering barrier.{x",
            "expire_msg_self": "{WThe shimmering barrier around you dissipates.{x",
            "expire_msg_room": "{WThe shimmering barrier surrounding {target_name} dissipates.{x"
        }
    },
    "chill touch": {
        "name": "Chill Touch", "type": "SPELL", "class_req": ["mage"], "level_req": 6,
        "cost": 8, "target_type": TARGET_CHAR_OR_MOB, "cast_time": 2.0,
        "effect_type": EFFECT_DAMAGE,
        "effect_details": {
            "damage_base": 4, "damage_rng": 4, "damage_type": DAMAGE_COLD, "school": "Arcane",
            "applies_effect": { "name": "Chilled", "type": "debuff", "stat_affected": "agility", "amount": -5, "duration": 12.0 }
        },
        "roundtime": 1.5, "description": "...",
        "messages": {
            "caster_self_complete": "{CFrigid energy coalesces around your hand as you touch {target_name}!{x",
            "room_complete": "{C{caster_name} touches {target_name}, leaving a frosty residue.{x",
            "apply_msg_target": "{CYou feel a deep chill seep into your bones, slowing your movements.{x",
            "expire_msg_target": "{CThe deep chill in your bones finally fades.{x"
        }
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
        "description": "A massive explosion of fire that damages all enemies in the area.",
        "messages": {
            "caster_self_complete": "{RYou hurl a tiny bead of flame that blossoms into a roaring inferno!{x",
            "room_complete": "{R{caster_name} hurls a tiny bead of flame that explodes, engulfing the area in a roaring inferno!{x"
        }
    },
    # == CLERIC ==
    "minor heal": {
        "name": "Minor Heal", "type": "SPELL", "class_req": ["cleric"], "level_req": 1,
        "cost": 4, "target_type": TARGET_CHAR_OR_MOB,
        "cast_time": 2.0, # Takes time to invoke
        "effect_type": EFFECT_HEAL,
        "effect_details": {"heal_base": 5, "heal_rng": 6},
        "roundtime": 1.5, # RT applied AFTER spell fires
        "description": "A simple divine plea to mend minor wounds.",
        "messages": {
            "caster_self_complete": "{YGolden light flows from your hands, mending wounds.{x",
            "room_complete": "{YGolden light flows from {caster_name}'s hands, mending {target_name}'s wounds.{x"
        }
    },
    "smite": {
        "name": "Smite", "type": "SPELL", "class_req": ["cleric"], "level_req": 1,
        "cost": 2, "target_type": TARGET_CHAR_OR_MOB, # Changed to allow vs players too
        "cast_time": 1.5, # Takes time to invoke
        "effect_type": EFFECT_DAMAGE,
        "effect_details": {"damage_base": 2, "damage_rng": 6, "damage_type": DAMAGE_DIVINE, "school": "Divine"},
        "roundtime": 2.0, # RT applied AFTER spell fires
        "description": "Calls down divine energy to strike your foe.",
        "messages": {
            "caster_self_complete": "{YYou call down a column of divine light to strike {target_name}!{x",
            "room_complete": "{Y{caster_name} calls down a column of divine light to strike {target_name}!{x"
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
        "class_req": ["cleric"], #
        "level_req": 10, #
        "cost": 15, #
        "target_type": TARGET_CHAR_OR_MOB, #
        "cast_time": 1.5, #
        "effect_type": "CURE", #
        "effect_details": {
            "cure_type": "poison" #
        },
        "roundtime": 2.0, #
        "description": "Neutralizes common poisons afflicting the target.", #
        "messages": {
            "caster_self_complete": "{WYou gesture at {target_name}, and a pure light washes over them, cleansing them of poison.{x",
            "room_complete": "{W{caster_name} gestures at {target_name}, who is bathed in a brief, pure light.{x"
        }
    },
     "circle of healing": {
        "name": "Circle of Healing",
        "type": "SPELL",
        "class_req": ["cleric"], #
        "level_req": 16, #
        "cost": 35, #
        "target_type": TARGET_AREA, #
        "cast_time": 3.0, #
        "effect_type": EFFECT_HEAL, #
        "effect_details": {
            "aoe_target_scope": "allies", #
            "heal_base": 15, #
            "heal_rng": 10 #
        },
        "roundtime": 4.0, #
        "description": "A circle of golden light washes over your allies, mending their wounds.", #
        "messages": {
            "caster_self_complete": "{YAn expanding circle of golden light washes over your allies, mending their wounds.{x",
            "room_complete": "{YA circle of golden light expands from {caster_name}'s feet, washing over their allies.{x"
        }
    },
     "resurrect": {
        "name": "Resurrect",
        "type": "SPELL",
        "class_req": ["cleric"], #
        "level_req": 20, #
        "cost": 100, #
        "target_type": TARGET_CHAR, #
        "effect_type": "RESURRECT", #
        "cast_time": 30.0, #
        "roundtime": 10.0, #
        "effect_details": {
            "xp_cost": 5000 #
        },
        "description": "A powerful plea to restore a soul to its body, preventing tether loss. This ritual costs the caster some of their own life experience.", #
        "messages": {
            "caster_self_complete": "{YYou complete the final words of the ritual, and a blinding column of divine energy surges from the heavens into {target_name}'s corpse!{x",
            "room_complete": "{Y{caster_name} completes a powerful ritual! A blinding column of divine energy surges from the heavens, striking {target_name}'s corpse and bringing them back to life!{x"
        }
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
    "aimed shot": {
        "name": "Aimed Shot", "type": "ABILITY", "class_req": ["ranger"], "level_req": 1,
        "cost": 5, "target_type": TARGET_MOB, "effect_type": EFFECT_MODIFIED_ATTACK,
        "effect_details": { "is_ranged": True, "bonus_rar": 15, "damage_multiplier": 1.25 },
        "roundtime": 4.0, "description": "...",
        "messages": {
            "caster_self_complete": "{GYou take a deep breath, aim carefully, and release your shot at {target_name}!{x",
            "room_complete": "{G{caster_name} takes a moment to aim before firing at {target_name}.{x"
        }
    },

    "serpent sting": {
        "name": "Serpent Sting", "type": "ABILITY", "class_req": ["ranger"], "level_req": 3,
        "cost": 10, "target_type": TARGET_MOB, "effect_type": EFFECT_MODIFIED_ATTACK,
        "effect_details": {
            "is_ranged": True, "damage_multiplier": 0.8,
            "applies_effect": { "name": "SerpentVenom", "type": "poison", "duration": 12.0, "potency": 5 }
        },
        "roundtime": 2.5, "description": "...",
        "messages": {
            "caster_self_complete": "You fire a venom-tipped projectile at {target_name}!",
            "room_complete": "{caster_name} fires a venom-tipped projectile at {target_name}.",
            "apply_msg_target": "{gA sickly green venom begins to course through your veins!{x",
            "expire_msg_target": "{gThe serpent venom has run its course.{x"
        }
    },

    "hunter's mark": {
        "name": "Hunter's Mark",
        "type": "ABILITY",
        "class_req": ["ranger"],
        "level_req": 5,
        "cost": 15,
        "target_type": TARGET_MOB,
        "effect_type": EFFECT_DEBUFF,
        "effect_details": {
            "name": "Marked",
            "type": "debuff",
            "stat_affected": "bonus_dv", # Lowers the target's Dodge Value
            "amount": -2,
            "duration": 60.0
        },
        "roundtime": 2.0,
        "description": "Mark a target as your quarry, making them easier for you and your allies to hit.",
        "apply_msg_room": "{caster_name} points at {target_name}, marking them as prey."
    },
    "rage": {
        "name": "Rage",
        "type": "ABILITY",
        "class_req": ["barbarian"],
        "level_req": 1,
        "cost": 10,
        "target_type": TARGET_SELF,
        "effect_type": EFFECT_BUFF,
        "effect_details": {
            "name": "Rage",
            "type": "buff",
            "stat_affected": "might",
            "amount": 5,
            "duration": 30.0,
            # This buff also applies a secondary debuff
            "secondary_effect": {
                "stat_affected": "bonus_dv",
                "amount": -3
            }
        },
        "roundtime": 1.5,
        "description": "Enter a primal rage, increasing your might but making you easier to hit.",
        "apply_msg_self": "{rYou fly into a screaming rage!{x",
        "apply_msg_room": "{caster_name} bellows with primal fury!",
        "expire_msg_self": "{rYour rage subsides.{x"
    },
    "reckless attack": {
        "name": "Reckless Attack",
        "type": "ABILITY",
        "class_req": ["barbarian"],
        "level_req": 4,
        "cost": 5,
        "target_type": TARGET_CHAR_OR_MOB,
        "effect_type": EFFECT_MODIFIED_ATTACK,
        "effect_details": {
            "bonus_mar": 20,          # Huge accuracy bonus
            "damage_multiplier": 1.2, # 20% damage bonus
            "applies_self_effect": {  # Applies a debuff to the barbarian after using
                "name": "Exposed", "type": "debuff", "stat_affected": "bonus_dv", "amount": -50, "duration": 3.0
            }
        },
        "roundtime": 0, # The roundtime is the weapon's speed
        "description": "Throw all caution to the wind, making a powerful and accurate attack that leaves you exposed for a few moments.",
        "messages": {
            "caster_self_complete": "{RWith a wild roar, you make a reckless attack against {target_name}!{x",
            "room_complete": "{R{caster_name} roars and makes a reckless attack against {target_name}!{x",
            "apply_msg_self": "{RYour reckless attack leaves you completely exposed!{x",
            "expire_msg_self": "{RYou regain your footing.{x"
        }
    },
    "sunder armor": {
        "name": "Sunder Armor",
        "type": "ABILITY",
        "class_req": ["barbarian"],
        "level_req": 8,
        "cost": 15,
        "target_type": TARGET_CHAR_OR_MOB,
        "effect_type": EFFECT_MODIFIED_ATTACK,
        "effect_details": {
            "damage_multiplier": 0.5, # The hit itself is weak
            "applies_effect": {       # But it applies a strong debuff
                "name": "Sundered", "type": "debuff", "stat_affected": "bonus_av", "amount": -20, "duration": 10.0
            }
        },
        "roundtime": 3.0,
        "description": "A focused strike intended to break or disable an opponent's armor, reducing their physical defense.",
        "messages": {
            "caster_self_complete": "You slam your weapon into {target_name}'s armor with a resounding CRACK!",
            "room_complete": "{caster_name} slams their weapon into {target_name}'s armor with a resounding CRACK!",
            "apply_msg_target": "{RYour armor has been sundered, leaving you vulnerable!{x",
            "expire_msg_target": "{RYour sundered armor feels slightly more secure.{x"
        }
}
}
}

# Helper function to get data safely
def get_ability_data(world: 'World', name: str) -> Optional[Dict[str, Any]]:
    """Gets ability data from the world cache."""
    return world.abilities.get(name.lower())