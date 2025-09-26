# game/combat/hit_resolver.py
"""
Handles the logic for determining if an attack hits, misses, or crits.
"""
import random
from dataclasses import dataclass
from typing import Union

from ..character import Character
from ..mob import Mob

@dataclass
class HitResult:
    """A structured result for a hit check."""
    is_hit: bool
    is_crit: bool
    roll: int
    attacker_rating: int
    target_dv: int

def check_physical_hit(attacker: Union[Character, Mob], target: Union[Character, Mob], use_rar: bool = False, hit_modifier: int = 0) -> HitResult:
    """
    Performs a physical hit check (d20 + MAR vs DV).

    Returns:
        A hitresult object with the outcome
    """
    attacker_rating = attacker.rar if use_rar else attacker.mar

    if isinstance(attacker, Character):
        weapon = attacker._equipped_items.get('main_hand')
        if not weapon:
            attacker_rating += attacker.get_skill_rank("martial arts") // 25
        elif weapon.item_type == "WEAPON":
            if weapon.damage_type in ['slash', 'pierce']:
                attacker_rating += attacker.get_skill_rank("bladed weapons") // 25
            elif weapon.damage_type == 'bludgeon':
                attacker_rating += attacker.get_skill_rank("bludgeon weapons") // 25
            
    # FIX: Apply armor penalty to target's dodge value
    target_dv = target.dv
    if isinstance(target, Character):
        target_dv = max(0, target_dv - target.total_av)


    target_dv = target.dv
    roll = random.randint(1, 20)
    modified_roll = roll + hit_modifier

    if modified_roll <= 1:
        is_hit, is_crit = False, False  # Critical miss
    elif modified_roll >= 20:
        is_hit, is_crit = True, True   # Critical hit
    else:
        is_hit = (modified_roll + attacker_rating) > target_dv
        is_crit = False

    return HitResult(
        is_hit=is_hit,
        is_crit=is_crit,
        roll=roll,
        attacker_rating=attacker_rating,
        target_dv=target_dv
    )

def check_magical_hit(caster: Union[Character, Mob], target: Union[Character, Mob], school: str) -> HitResult:
    """
    Performs a magical hit check (d20 + APR/DPR vs DV).

    Args:
        school (str): The magic school, typically "Arcane" or "Divine", to determine rating.

    Returns:
        A HitResult object with the outcome.
    """
    attacker_rating = caster.apr if school == "Arcane" else caster.dpr
    target_dv = target.dv
    roll = random.randint(1, 20)

    is_crit = (roll == 20)
    is_fumble = (roll == 1)

    is_hit = is_crit or (not is_fumble and (attacker_rating + roll) >= target_dv)

    return HitResult(
        is_hit=is_hit,
        is_crit=is_crit,
        roll=roll,
        attacker_rating=attacker_rating,
        target_dv=target_dv
    )