# game/combat/damage_calculator.py
"""
Handles all damage calculation and mitigation logic.
"""
import random
import math
from dataclasses import dataclass
from typing import Union, Dict, Any, Optional

from ..character import Character
from ..mob import Mob
from ..item import Item

@dataclass
class DamageInfo:
    """A structured result for a pre-mitigation damage calculation."""
    pre_mitigation_damage: int
    damage_type: str
    is_crit: bool

def _roll_exploding_dice(max_roll: int) -> int:
    """Rolls a die, exploding on the maximum result up to 10 times."""
    if max_roll <= 0: return 0
    total, rolls, max_explosions = 0, 0, 10
    while rolls < max_explosions:
        roll = random.randint(1, max_roll)
        total += roll
        if roll < max_roll:
            break
        rolls += 1
    return total

def calculate_physical_damage(attacker: Union[Character, Mob], attack_source: Optional[Union[Item, Dict[str, Any]]], is_crit: bool) -> DamageInfo:
    """Calculates the pre-mitigation damage for a physical attack."""
    base_dmg, rng_dmg, dmg_type = 1, 0, "bludgeon"
    stat_modifier = attacker.might_mod

    if isinstance(attacker, Character):
        if isinstance(attack_source, Item) and attack_source.item_type == "WEAPON":
            base_dmg, rng_dmg, dmg_type = attack_source.damage_base, attack_source.damage_rng, attack_source.damage_type or "bludgeon"
        else: # Unarmed
            base_dmg, rng_dmg = 1, 2
    elif isinstance(attacker, Mob) and isinstance(attack_source, dict):
        base_dmg, rng_dmg = attack_source.get("damage_base", 1), attack_source.get("damage_rng", 0)

    rng_roll_result = random.randint(1, rng_dmg) if rng_dmg > 0 else 0
    if is_crit:
        rng_roll_result += _roll_exploding_dice(rng_dmg)

    pre_mitigation_damage = max(0, base_dmg + rng_roll_result + stat_modifier)
    
    return DamageInfo(pre_mitigation_damage=pre_mitigation_damage, damage_type=dmg_type, is_crit=is_crit)

def mitigate_damage(target: Union[Character, Mob], damage_info: DamageInfo) -> int:
    """Applies mitigation to pre-calculated damage and returns the final amount."""
    pre_mitigation_damage = damage_info.pre_mitigation_damage
    
    # Base mitigation from stats and armor
    mit_pds = target.pds
    mit_av = target.total_av
    mit_bv = math.floor(target.barrier_value / 2) # Barriers are half effective vs physical
    
    post_armor_damage = max(0, pre_mitigation_damage - mit_pds - mit_av - mit_bv)

    # Apply resistances/vulnerabilities
    resistance = target.resistances.get(damage_info.damage_type, 0.0)
    if resistance != 0:
        multiplier = 1.0 - (resistance / 100.0)
        final_damage = int(post_armor_damage * multiplier)
    else:
        final_damage = post_armor_damage
        
    return max(0, final_damage)

def calculate_magical_damage(caster: Union[Character, Mob], spell_data: Dict[str, Any], is_crit: bool) -> DamageInfo:
    """Calculates the pre-mitigation damage for a magical attack."""
    effect_details = spell_data.get("effect_details", {})
    school = effect_details.get("school", "Arcane")
    
    base_dmg = effect_details.get("damage_base", 0)
    rng_dmg = effect_details.get("damage_rng", 0)
    dmg_type = effect_details.get("damage_type", "arcane")
    stat_modifier = caster.apr if school == "Arcane" else caster.dpr

    rng_roll_result = random.randint(1, rng_dmg) if rng_dmg > 0 else 0
    if is_crit:
        rng_roll_result += _roll_exploding_dice(rng_dmg)

    pre_mitigation_damage = max(0, base_dmg + rng_roll_result + stat_modifier)
    
    return DamageInfo(pre_mitigation_damage=pre_mitigation_damage, damage_type=dmg_type, is_crit=is_crit)


def mitigate_magical_damage(target: Union[Character, Mob], damage_info: DamageInfo) -> int:
    """Applies mitigation to pre-calculated magical damage."""
    pre_mitigation_damage = damage_info.pre_mitigation_damage
    
    # Base mitigation from stats and barriers
    mit_sds = target.sds
    mit_bv = target.barrier_value
    
    post_mitigation_damage = max(0, pre_mitigation_damage - mit_sds - mit_bv)

    # Apply resistances/vulnerabilities
    resistance = target.resistances.get(damage_info.damage_type, 0.0)
    if resistance != 0:
        multiplier = 1.0 - resistance
        final_damage = int(post_mitigation_damage * multiplier)
    else:
        final_damage = post_mitigation_damage
        
    return max(0, final_damage)