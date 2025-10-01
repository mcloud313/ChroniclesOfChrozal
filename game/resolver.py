# game/resolver.py
"""
Coordinates combat resolution by calling specialized modules.
"""
import logging
import random
import math
import time
import json
from typing import Union, Dict, Any, Optional, Tuple, List, TYPE_CHECKING

from . import utils

# The coordinator now imports all its helper modules
from .combat import hit_resolver, damage_calculator, outcome_handler
from .character import Character
from .mob import Mob
from .item import Item
from .room import Room
from .definitions import abilities as ability_defs
from .definitions import item_defs


log = logging.getLogger(__name__)
if TYPE_CHECKING:
    from .world import World

log = logging.getLogger(__name__)

def roll_exploding_dice(max_roll: int) -> int:
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

async def _check_and_break_concentration(target: Union['Character', 'Mob'], damage: int):
    """
    Checks if a character taking damage loses concentration on a spell they are casting.
    """
    if not isinstance(target, Character) or not target.casting_info or damage <= 0:
        return False # Not a player, not casting, or no damage taken

    # DC is 10 or half the damage taken, whichever is higher. A classic!
    dc = max(10, damage // 2)
    check = utils.skill_check(target, "spellcraft", dc)
    
    if not check['success']:
        spell_name = target.casting_info.get("name", "your spell")
        target.casting_info = None
        target.roundtime = 0.0 # Clear casting roundtime
        await target.send(f"<R>The pain of the blow causes you to lose concentration on {spell_name}!<x>")
        return True
    return False

async def resolve_physical_attack(
    attacker: Union[Character, Mob],
    target: Union[Character, Mob],
    attack_source: Optional[Union[Item, Dict[str, Any]]],
    world: 'World',
    damage_multiplier: float = 1.0,
    ability_mods: Optional[Dict[str, Any]] = None # <-- FIX 1: Add the missing argument here
):
    """Resolves a physical attack by coordinating hit, damage, and outcome modules."""
    # ---Initial Checks ---
    if not attacker.is_alive() or not target.is_alive() or attacker.location != target.location:
        return

    # ---Determine Attack Variables (CRITICAL: Do this first!) ---
    wpn_speed = 2.0 # Default for unarmed
    attack_name = "unarmed strike"
    if isinstance(attacker, Character):
        valid_weapon_types = {item_defs.WEAPON, item_defs.TWO_HANDED_WEAPON}
        if isinstance(attack_source, Item) and attack_source.item_type in valid_weapon_types:
            wpn_speed, attack_name = attack_source.speed, attack_source.name
    elif isinstance(attacker, Mob) and isinstance(attack_source, dict):
        wpn_speed, attack_name = attack_source.get("speed", 2.0), attack_source.get("name", "an attack")

    rt_penalty = attacker.total_av * 0.05 if isinstance(attacker, Character) else 0.0
    attacker.roundtime = wpn_speed + rt_penalty + attacker.slow_penalty

    hit_modifier = 0
    if not attacker.can_see():
        hit_modifier -= 4
    if not target.can_see() and attacker.can_see():
        hit_modifier += 4

    use_rar = False
    if isinstance(attacker, Mob) and isinstance(attack_source, dict):
        if attack_source.get("attack_type") == "ranged":
            use_rar = True

    # ---Resolve Hit/Miss ---
    hit_result = hit_resolver.check_physical_hit(attacker, target, use_rar=use_rar, hit_modifier=hit_modifier)
    rt_penalty = attacker.total_av * 0.05 if isinstance(attacker, Character) else 0.0
    
    if not hit_result.is_hit:
        roll_details = f"<i>[Roll: {hit_result.roll} + MAR: {hit_result.attacker_rating} vs DV: {hit_result.target_dv}]<x>"
        if isinstance(attacker, Character):
            await attacker.send(f"You miss {target.name} with your {utils.strip_article(attack_name)}. {roll_details}")
        if isinstance(target, Character):
            await target.send(f"{attacker.name.capitalize()}'s {attack_name} misses you.")
        attacker.roundtime = 1.0 + rt_penalty + attacker.slow_penalty
        return
    
    # --- Resolve Parry ---
    if isinstance(target, Character) and (weapon := target._equipped_items.get("main_hand")):
        parry_skill_rank = target.get_skill_rank("parrying")
        parry_chance = parry_skill_rank * 0.005
        if random.random() < parry_chance:
            await attacker.send(f"<y>{target.name} parries your attack with their {weapon.name}!<x>")
            await target.send(f"<g>You parry {attacker.name}'s attack with your {weapon.name}!<x>")
            attacker.roundtime = 1.0 + rt_penalty + attacker.slow_penalty
            return

    # ---Resolve Block ---
    if isinstance(target, Character) and (shield := target.get_shield()):
        shield_skill_rank = target.get_skill_rank("shield usage")
        block_chance = shield.block_chance + (math.floor(shield_skill_rank / 10) * 0.01)
        if random.random() < block_chance:
            await attacker.send(f"<y>{target.name} blocks your attack with their shield!<x>")
            await target.send(f"<g>You block {attacker.name}'s attack with your shield!<x>")
            attacker.roundtime = wpn_speed + rt_penalty + attacker.slow_penalty
            return
        
    # ---Calculate and Mitigate Damage ---
    # <-- FIX 2: Pass the new 'ability_mods' argument to the calculator
    damage_info = damage_calculator.calculate_physical_damage(attacker, attack_source, hit_result.is_crit, ability_mods=ability_mods)
    
    damage_info.attack_name = attack_name
    if damage_multiplier != 1.0:
        damage_info.pre_mitigation_damage = int(damage_info.pre_mitigation_damage * damage_multiplier)
    final_damage = damage_calculator.mitigate_damage(target, damage_info)

    await _check_and_break_concentration(target, final_damage)

    #--- Handle Consequences
    if isinstance(attack_source, Item):
        await outcome_handler.handle_durability(attacker, target, attack_source, world)
    outcome_handler.apply_damage(target, final_damage)
    await outcome_handler.send_attack_messages(attacker, target, hit_result, damage_info, final_damage)

    if target.hp <= 0:
        await outcome_handler.handle_defeat(attacker, target, world)
        return
    
    if isinstance(attacker, Character) and attacker.is_hidden:
        attacker.is_hidden = False
    
    # --- 8. Apply Final Roundtime for a successful hit ---
    attacker.roundtime = wpn_speed + rt_penalty + attacker.slow_penalty

async def resolve_ranged_attack(
    attacker: Union[Character, Mob],
    target: Union[Character, Mob],
    weapon: Item,
    ammo: Item,
    world: 'World'
):
    """Resolves a ranged attack by coordinating hit, damage, and outcome modules."""
    if not attacker.is_alive() or not target.is_alive() or attacker.location != target.location:
        return

    # --- Set Attacker Roundtime ---
    wpn_speed = weapon.speed
    rt_penalty = attacker.total_av * 0.05 if isinstance(attacker, Character) else 0.0
    attacker.roundtime = wpn_speed + rt_penalty + attacker.slow_penalty

    hit_modifier = 0
    if not attacker.can_see():
        hit_modifier -= 8 # A -8 penalty on a d20 roll (40% reduced chance)
    if not target.can_see() and attacker.can_see():
        hit_modifier += 4 # Same bonus applies

    # --- Resolve Hit/Miss (using RAR instead of MAR) ---
    hit_result = hit_resolver.check_physical_hit(attacker, target, use_rar=True, hit_modifier=hit_modifier)

    if not hit_result.is_hit:
        roll_details = f"<i>[Roll: {hit_result.roll} + RAR: {hit_result.attacker_rating} vs DV: {hit_result.target_dv}]<x>"
        if isinstance(attacker, Character):
            await attacker.send(f"Your {utils.strip_article(ammo.name)} misses {target.name}. {roll_details}")
        if isinstance(target, Character):
            await target.send(f"{attacker.name.capitalize()}'s {ammo.name} flies past you.")
        await attacker.location.broadcast(f"\r\n{attacker.name.capitalize()}'s shot goes wide of {target.name}!\r\n", {attacker, target})
        return
    
       # ---Resolve Block ---
    if isinstance(target, Character) and (shield := target.get_shield()):
        shield_skill_rank = target.get_skill_rank("shield usage")
        block_chance = shield.block_chance + (math.floor(shield_skill_rank / 10) * 0.01)
        if random.random() < block_chance:
            await attacker.send(f"<y>{target.name} blocks your attack with their shield!<x>")
            await target.send(f"<g>You block {attacker.name}'s attack with your shield!<x>")
            attacker.roundtime = wpn_speed + rt_penalty + attacker.slow_penalty
            return
        
    # --- Calculate and Mitigate Damage ---
    # Damage is primarily from the weapon, with a possible bonus from ammo
    damage_info = damage_calculator.calculate_physical_damage(attacker, weapon, hit_result.is_crit)
    
    # Add bonus from ammo
    ammo_bonus = ammo.instance_stats.get("damage_bonus", 0)
    damage_info.pre_mitigation_damage += ammo_bonus
    
    damage_info.attack_name = ammo.name # The projectile is what hits
    final_damage = damage_calculator.mitigate_damage(target, damage_info)

    await _check_and_break_concentration(target, final_damage)

    # --- Handle Consequences ---
    outcome_handler.apply_damage(target, final_damage)
    # We need a ranged-specific message handler
    await outcome_handler.send_ranged_attack_messages(attacker, target, hit_result, damage_info, final_damage)

    if target.hp <= 0:
        await outcome_handler.handle_defeat(attacker, target, world)

    if isinstance(attacker, Character) and attacker.is_hidden:
        attacker.is_hidden = False

async def resolve_magical_attack(
    caster: Union[Character, Mob], 
    target: Union[Character, Mob],
    spell_data: Dict[str, Any],
    world: 'World'
):
    """Resolves spell damage against a target with detailed calculations and messaging."""
    effect_details = spell_data.get("effect_details", {})
    caster_name = caster.name.capitalize()
    target_name = target.name.capitalize()
    spell_name = spell_data.get("name", "a spell")

    if effect_details.get("always_hits"):
        # If the spell can't miss, create a fake HitResult and skip the roll.
        hit_result = hit_resolver.HitResult(is_hit=True, is_crit=False, roll=0, attacker_rating=0, target_dv=0)
    else:


    # ---Get Power and Defense Ratings ---
        school = effect_details.get("school", "Arcane")
        rating_name = "APR" if school == "Arcane" else "DPR"

        hit_result = hit_resolver.check_magical_hit(caster, target, school)

        if not hit_result.is_hit:
            roll_details = f"<i>[Roll: {hit_result.roll} + {rating_name}: {hit_result.attacker_rating} vs DV: {hit_result.target_dv}]<x>"
            if isinstance(caster, Character):
                await caster.send(f"Your {spell_name} misses {target_name}. {roll_details}")
            if isinstance(target, Character):
                await target.send(f"{caster_name}'s {spell_name} misses you.")
            return
    
    # ---Calculate Damage ---
    damage_info = damage_calculator.calculate_magical_damage(caster, spell_data, hit_result.is_crit)

    weather_mod = _get_weather_damage_modifier(caster.location, damage_info.damage_type)
    if weather_mod != 1.0:
        damage_info.pre_mitigation_damage = int(damage_info.pre_mitigation_damage * weather_mod)
    damage_info.attack_name = spell_name # Add spell name to the info object
    final_damage = damage_calculator.mitigate_magical_damage(target, damage_info)


    outcome_handler.apply_damage(target, final_damage)

    await outcome_handler.send_magical_attack_messages(caster, target, hit_result, damage_info, final_damage)
    
    # --- 5. Handle Post-Damage Effects ---
    if isinstance(target, Character) and target.status == "MEDITATING" and final_damage > 0:
        target.status = "ALIVE"
        await target.send("{RThe magical assault disrupts your meditation!{x")
        if caster.location:
            await caster.location.broadcast(f"\r\n{target_name} is snapped out of their meditative trance by the attack!\r\n", exclude={target})

    await _check_and_break_concentration(target, final_damage)

    # Apply any rider effects (e.g., a stun that accompanies the damage)
    if hit_result.is_hit and (rider_effect := effect_details.get("applies_effect")):
        await apply_effect(caster, target, spell_data, rider_effect, world)

    # --- 6. Check for Defeat ---
    if target.hp <= 0:
        await outcome_handler.handle_defeat(caster, target, world)

    if isinstance(caster, Character) and caster.is_hidden:
        caster.is_hidden = False

async def resolve_ability_effect(
    caster: Character,
    target_ref: Optional[Union[int, str]],
    target_type_str: Optional[str],
    ability_data: Dict[str, Any],
    world: 'World'
):
    """Finds the target and calls the specific effect resolution function."""
    effect_type = ability_data.get("effect_type")
    effect_details = ability_data.get("effect_details", {})
    ability_key = ability_data.get("name", "?").lower()
    required_target_type = ability_data.get("target_type")

    # 1. --- Area of Effect (AoE) Logic ---
    if required_target_type == ability_defs.TARGET_AREA:
        if not caster.location: return

        scope = effect_details.get("aoe_target_scope", "enemies") # Default to hitting enemies
        
        potential_targets = list(caster.location.characters) + list(caster.location.mobs)
        final_targets = []

        if scope == "enemies":
            # Target all living mobs
            final_targets = [m for m in caster.location.mobs if m.is_alive()]
        elif scope == "allies":
            # Target all living group members in the room, including the caster
            if caster.group:
                final_targets = [m for m in caster.group.members if m.location == caster.location and m.is_alive()]
            else: # If not in a group, only target self
                final_targets = [caster]
        elif scope == "all":
            # Target all living things in the room except the caster
            final_targets = [p for p in potential_targets if p != caster and p.is_alive()]

        if not final_targets:
            await caster.send("There are no valid targets here.")
            return

        # Apply the primary effect to every target in the list
        for target in final_targets:
            if effect_type == ability_defs.EFFECT_DAMAGE:
                await resolve_magical_attack(caster, target, ability_data, world)
            elif effect_type == ability_defs.EFFECT_HEAL:
                await apply_heal(caster, target, effect_details, world)
            # Add other AoE effect types like DEBUFF here later
        
        return # AoE is fully resolved, exit the function

    # --- 2. Find Target ---
    target: Optional[Union[Character, Mob]] = None

    # Normalize the type string to handle case variation
    target_type_normalized = target_type_str.upper() if target_type_str else ""

    if target_type_normalized == "SELF":
        target = caster
        log.info(f"RESOLVE DEBUG: Self-cast, target = character")
    elif target_type_normalized in ("CHAR", "CHARACTER") and isinstance(target_ref, int):
        target = world.get_active_character(target_ref)
        log.info(f"RESOLVE DEBUG: Character lookup for ID {target_ref}: {target.name if target else 'NOT FOUND'}")
    if not target and target_type_normalized in ("MOB", "CHAR_OR_MOB") and isinstance(target_ref, int):
        if caster.location:
            target = next((m for m in caster.location.mobs if m.instance_id == target_ref), None)
            log.info(f"RESOLVE DEBUG: Mob lookup for instance_id {target_ref}: {target.name if target else 'NOT FOUND'}")


    # --- 3. Validate Target ---
    required_target_type = ability_data.get("target_type")
    if required_target_type != ability_defs.TARGET_NONE and (
        target is None or not target.is_alive() or (target != caster and target.location != caster.location)
    ):
        log.info(f"RESOLVE DEBUG: Target object: {target}")
        log.info(f"RESOLVE DEBUG: Target is_alive: {target.is_alive() if target else 'N/A'}")
        await caster.send("Your target is no longer valid.")
        return

    # --- 4. Resolve Effect ---
    log.debug("Resolving effect '%s' for %s. Caster: %s, Target: %s",
              effect_type, ability_key, caster.name, getattr(target, 'name', 'None'))

    if effect_type == ability_defs.EFFECT_DAMAGE:
        if effect_details.get("is_cone_aoe"):
            primary_target = target
            other_mobs = [m for m in caster.location.mobs if m.is_alive() and m != primary_target]
            random.shuffle(other_mobs)
            
            max_targets = effect_details.get("max_aoe_targets", 1)
            secondary_targets = other_mobs[:max_targets - 1]
            all_targets = [primary_target] + secondary_targets
            
            await caster.send(f"A fan of flames erupts from your hands!")

            for t in all_targets:
                await resolve_magical_attack(caster, t, ability_data, world)
        else:
            await resolve_magical_attack(caster, target, ability_data, world)
    
    elif effect_type == ability_defs.EFFECT_HEAL:
        await apply_heal(caster, target, effect_details, world)
    
    elif effect_type in (ability_defs.EFFECT_BUFF, ability_defs.EFFECT_DEBUFF):
        # --- THIS IS THE CORRECTED LINE ---
        await apply_effect(caster, target, ability_data, effect_details, world)
        # ----------------------------------
    
    elif effect_type == ability_defs.EFFECT_MODIFIED_ATTACK:
        
        if effect_details.get("is_cleave"):
            primary_target = target
            
            other_mobs = [m for m in caster.location.mobs if m.is_alive() and m != primary_target]
            random.shuffle(other_mobs)
            
            max_targets = effect_details.get("max_cleave_targets", 1)
            secondary_targets = other_mobs[:max_targets - 1]
            
            all_targets = [primary_target] + secondary_targets
            
            await caster.send(ability_data["messages"]["caster_self"])
            await caster.location.broadcast(f"\r\n{ability_data['messages']['room'].format(caster_name=caster.name)}\r\n", exclude={caster})

            weapon = caster._equipped_items.get("main_hand")
            damage_mult = effect_details.get("damage_multiplier", 1.0)
            
            for t in all_targets:
                await resolve_physical_attack(caster, t, weapon, world, damage_multiplier=damage_mult)
            return
        
        if effect_details.get("requires_stealth_or_flank"):
            is_stealthed = caster.is_hidden
            is_flanking = (isinstance(target, Mob) and target.is_fighting and target.target != caster)

            if not is_stealthed and not is_flanking:
                await caster.send("You must be hidden or attacking an engaged target to backstab!")
                return

        damage_mult = effect_details.get("damage_multiplier", 1.0)
        
        weapon = None
        if (weapon_obj := caster._equipped_items.get("main_hand")):
            weapon = weapon_obj
            
        await resolve_physical_attack(caster, target, weapon, world, 
                                      ability_mods=effect_details, 
                                      damage_multiplier=damage_mult)
        
    elif effect_type == "RESURRECT":
        if not isinstance(target, Character) or target.status != "DEAD":
            await caster.send("Your spell requires a dead target.")
            return
        
        if target.location != caster.location:
            await caster.send("Your target is not here.")
            return

        # Scale XP cost based on target's remaining tether (exponential scaling)
        base_xp_cost = effect_details.get("xp_cost", 5000)
        tether_multiplier = 2 ** (10 - target.spiritual_tether) # Exponential 1x at 10. 2x at 9, 512x at 1
        xp_cost = base_xp_cost * tether_multiplier

        if caster.xp_total < xp_cost:
            await caster.send(f"<R>You lack the spiritual energy ({xp_cost:,} XP) to perform the ritual.<x>")
            await caster.send(f"<y>(Base cost: {base_xp_cost:,} × {tether_multiplier}x for tether level {target.spiritual_tether})<x>")
            return
    
        caster.xp_total -= xp_cost
        await caster.send(f"<y> You sacrifice {xp_cost:,} of your stored experience to fuel the ritual...<x>")

        # Restore target
        target.status = "ALIVE"
        target.hp = target.max_hp // 10
        target.spiritual_tether = min(10, target.spiritual_tether + 1)
        target.essence = 0
        target.is_dirty = True

        await caster.send(f"<Y>A blinding column of divine energy surges through you into {target.name}'s corpse!<x>")
        await target.send("<Y>You feel your spirit violently pulled back into your body! You have been resurrected!<x>")
        await target.send(f"<g>Your spiritual tether strengthens. ({target.spiritual_tether}/10)<x>")

        if caster.location:
            await caster.location.broadcast(
            f"\r\n<Y>A blinding column of divine energy strikes {target.name}'s corpse as {caster.name} completes a powerful resurrection ritual!<x>\r\n",
            exclude={caster, target}
        )

    elif effect_type == "CURE":
        cure_type = effect_details.get("cure_type")
        if not cure_type: return

        effects_to_remove = [k for k, v in target.effects.items() if v.get('type') == cure_type]
        
        if not effects_to_remove:
            await caster.send(f"{target.name} is not afflicted by {cure_type}.")
            return

        for key in effects_to_remove:
            del target.effects[key]
        
        await caster.send(f"You cure the {cure_type} afflicting {target.name}.")
        if isinstance(target, Character) and target != caster:
            await target.send(f"{caster.name} has cured your {cure_type}!")

    elif effect_type == ability_defs.EFFECT_STUN_ATTEMPT:
        if effect_details.get("requires_shield", False) and not caster.get_shield():
            await caster.send("You need a shield equipped for that!")
            return
        
        if perform_hit_check(caster, target, effect_details.get("mar_modifier_mult", 1.0)):
            await caster.location.broadcast(f"\r\n{caster.name.capitalize()} bashes {target.name}!\r\n", exclude={})
            if random.random() < effect_details.get("stun_chance", 0.0):
                stun_duration = effect_details.get("stun_duration", 3.0)
                target.roundtime += stun_duration
                await caster.location.broadcast(f"\r\n{target.name} is stunned!\r\n", exclude={})
        else:
            await caster.location.broadcast(f"\r\n{caster.name.capitalize()} tries to bash {target.name}, but misses.\r\n", exclude={})

    elif effect_type == "CONTESTED_DEBUFF":
        contest_details = effect_details.get("contest")
        if not contest_details: return

        attacker_mod = caster.get_skill_modifier(contest_details["attacker_skill"])
        defender_mod = target.get_skill_modifier(contest_details["defender_skill"])

        attacker_roll = random.randint(1, 20) + attacker_mod
        defender_roll = random.randint(1, 20) + defender_mod

        if attacker_roll > defender_roll:
            await caster.send(f"<g>You successfully trip {target.name}!<x>")
            success_effects = effect_details.get("on_success")
            if success_effects:
                await apply_effect(caster, target, ability_data, success_effects, world)
        else:
            await caster.send(f"<r>You fail to trip {target.name}.<x>")
    
    if isinstance(caster, Character) and caster.is_hidden:
        caster.is_hidden = False

async def apply_dot_damage(target: Union[Character, Mob], effect_data: Dict[str, Any], world: 'World'):
    """Applies damage from a damage over time effect like poison or bleed."""
    damage = effect_data.get('potency', 0)
    if damage <= 0:
        return
    
    effect_type = effect_data.get('type', 'damage')

    # Apply Damage
    target.hp = max(0.0, target.hp - damage)

    # Send feedback if the target is a player
    if isinstance(target, Character):
        await target.send(f"<r>You take {int(damage)} {effect_type} damage!<x>")

    # Check if the DoT was fatal
    if target.hp <= 0:
        # Create a simple object to represent the effect as the attacker
        class EffectAttacker:
            name = f"the {effect_type}"
            location = target.location

        await outcome_handler.handle_defeat(EffectAttacker(), target, world)

def determine_loot(loot_table: Dict[str, Any]) -> Tuple[int, List[int]]:
    """Calculates loot based on the provided loot_table dictionary."""
    dropped_coinage = 0
    dropped_item_ids = []

    if (max_coinage := loot_table.get("coinage_max", 0)) and isinstance(max_coinage, int):
        dropped_coinage = random.randint(0, max_coinage)

    if (item_list := loot_table.get("items", [])) and isinstance(item_list, list):
        for item_info in item_list:
            if isinstance(item_info, dict):
                if (template_id := item_info.get("template_id")) and \
                   (chance := item_info.get("chance", 0.0)) and \
                   (random.random() < chance):
                    dropped_item_ids.append(template_id)
    
    return dropped_coinage, dropped_item_ids

async def award_xp_to_character(character: Character, xp_amount: int):
    """Awards a specific amount of XP to a character's XP Pool."""
    if xp_amount <= 0:
        return
        
    intellect = character.stats.get("intellect", 10)
    xp_pool_cap = intellect * 100
    space_available = max(0, xp_pool_cap - character.xp_pool)
    actual_xp_added = min(xp_amount, space_available)

    if actual_xp_added > 0:
        character.xp_pool += actual_xp_added
        await character.send(f"You gain {int(actual_xp_added)} experience points into your pool.")
    # To avoid spam, we don't show the "pool is full" message to group members
    elif not character.group:
        await character.send("Your mind cannot hold any more raw experience right now.")

def perform_hit_check(attacker: Union[Character, Mob], target: Union[Character, Mob], mar_mult: float = 1.0) -> bool:
    """ Basic hit check logic (d20 + MAR*mult vs DV). """
    mod_mar = math.floor(attacker.mar * mar_mult)
    target_dv = target.dv
    hit_roll = random.randint(1, 20)
    if hit_roll == 1: return False
    if hit_roll == 20: return True
    return (mod_mar + hit_roll) >= target_dv

async def apply_heal(caster: Character, target: Union[Character, Mob], effect_details: Dict[str, Any], world: 'World'):
    """Applies healing to a target, and can revive them from a DYING state."""
    # Allow healing on DYING characters, but not DEAD ones.
    if isinstance(target, Character) and target.status == "DEAD":
        await caster.send(f"{target.name.capitalize()} is beyond simple healing.")
        return
    # Mobs that are not alive cannot be healed.
    if not target.is_alive() and isinstance(target, Mob):
        return

    heal_amount = effect_details.get("heal_base", 0) + random.randint(0, effect_details.get("heal_rng", 0))
    if heal_amount <= 0: return

    was_dying = isinstance(target, Character) and target.status == "DYING"

    actual_healed = min(heal_amount, target.max_hp - target.hp)
    target.hp += actual_healed

    # If they were dying, bring them back to consciousness
    if was_dying and target.hp > 0:
        target.status = "ALIVE"
        target.death_timer_ends_at = None # Stop the death timer
        await target.send("{gYou feel life return to your limbs! You are no longer dying.{x")
        if target.location:
            await target.location.broadcast(f"\r\n{target.name} stirs and returns from the brink of death!\r\n", exclude={target})

    msg_caster = f"You heal yourself for {int(actual_healed)} hit points." if caster == target else f"You heal {target.name} for {int(actual_healed)} hit points."
    msg_target = f"{caster.name.capitalize()} heals you for {int(actual_healed)} hit points."
    msg_room = f"{caster.name.capitalize()} heals {target.name}."
    
    await caster.send(msg_caster)
    if target != caster and isinstance(target, Character):
        await target.send(msg_target)
    if target.location:
        await target.location.broadcast(f"\r\n{msg_room}\r\n", exclude={caster, target})

async def apply_effect(caster: Union[Character, Mob], target: Union[Character, Mob], ability_data: Dict[str, Any], effect_details: Dict[str, Any], world: 'World'):
    """
    Applies a temporary effect (BUFF/DEBUFF) to the target, handling special cases and messaging.
    This is the single, consolidated function for all effects.
    """
    effect_name = effect_details.get("name")
    if not effect_name:
        log.warning("Attempted to apply an effect with no name.")
        return

    # Create a mutable copy to allow for dynamic modifications
    final_effect_details = effect_details.copy()

    # --- SPECIAL CASE: Mage Armor Spellcraft Bonus ---
    if ability_data.get("name") == "Mage Armor" and isinstance(caster, Character):
        spellcraft_skill = caster.get_skill_rank("spellcraft")
        bonus_amount = spellcraft_skill // 25
        final_effect_details["amount"] += bonus_amount
        log.debug(f"Mage Armor bonus: {bonus_amount} from {spellcraft_skill} spellcraft.")
    # --- END SPECIAL CASE ---

    duration = final_effect_details.get("duration", 0.0)
    stat = final_effect_details.get("stat_affected")
    amount = final_effect_details.get("amount", final_effect_details.get("potency"))

    if not all([duration > 0, stat, amount is not None]):
        log.error("Invalid effect data for '%s': %s", effect_name, final_effect_details)
        await caster.send("The effect seems to dissipate harmlessly.")
        return

    # --- Shapechange Logic: Remove old shapechange effects ---
    if final_effect_details.get("is_shapechange"):
        for effect_key, effect_data in list(target.effects.items()):
            source_key = effect_data.get("source_ability_key")
            if not source_key: continue
            
            source_ability = world.abilities.get(source_key)
            if source_ability and source_ability.get("effect_details", {}).get("is_shapechange"):
                # Use the resolver's own function to ensure messages are sent
                await resolve_effect_expiration(target, effect_key, world)

    # --- Store the final effect on the target ---
    target.effects[effect_name] = {
        "name": effect_name,
        "type": final_effect_details.get('type', 'buff'),
        "stat_affected": stat,
        "amount": amount,
        "applied_at": time.monotonic(),
        "ends_at": time.monotonic() + duration,
        "caster_id": caster.dbid if isinstance(caster, Character) else None,
        "source_ability_key": ability_data.get("internal_name")
    }
    target.is_dirty = True
    log.info("Applied effect '%s' to %s for %.1f seconds.", effect_name, target.name, duration)

    # --- Handle Immediate Secondary Effects ---
    if stat == "max_hp": # For effects that boost constitution
        target.max_hp += amount
        target.hp += amount

    if final_effect_details.get('type') == 'stun':
        stun_duration = final_effect_details.get('potency', 0.0)
        target.roundtime += stun_duration
        if isinstance(target, Character):
            await target.send("{RYou are stunned!{x")
        if target.location:
            await target.location.broadcast(f"\\r\\n{target.name.capitalize()} is stunned!\\r\\n", exclude={target})

    if new_stance := final_effect_details.get('set_stance'):
        if isinstance(target, Character):
            target.stance = new_stance

    # --- Unified Messaging ---
    messages = ability_data.get("messages", {})
    caster_name = caster.name.capitalize()
    target_name = target.name.capitalize()

    if target == caster:
        if msg := messages.get("apply_msg_self"):
            await caster.send(msg)
    else:
        if msg := messages.get("apply_msg_target"):
            await target.send(msg.format(caster_name=caster_name))
        await caster.send(f"You apply {effect_name} to {target_name}.")

    if msg_room := messages.get("apply_msg_room"):
        if target.location:
            await target.location.broadcast(f"\\r\\n{msg_room.format(caster_name=caster_name, target_name=target_name)}\\r\\n", exclude={caster, target})

async def resolve_effect_expiration(target: Union[Character, Mob], effect_key: str, world: 'World'):
    """
    Removes an expired effect from a target and sends expiration messages.
    """
    # Safely get the effect data before it's deleted
    effect_data = target.effects.pop(effect_key, None)
    if not effect_data:
        return # Effect was already removed, do nothing.

    log.info(f"Effect '{effect_key}' expired for {target.name}.")
    target.is_dirty = True

    # --- Revert Stat Changes ---
    stat_affected = effect_data.get("stat_affected")
    amount = effect_data.get("amount", 0)
    if stat_affected == "max_hp":
        target.max_hp -= amount
        target.hp = min(target.hp, target.max_hp) # Prevent HP from exceeding the new max

    # --- Send Expiration Messages ---
    source_ability_key = effect_data.get("source_ability_key")
    if not source_ability_key:
        return # No source, no message

    # Find the original ability to get its message block
    ability_data = world.abilities.get(source_ability_key)
    if not ability_data:
        return

    messages = ability_data.get("messages", {})
    target_name = target.name.capitalize()

    # Send the correct message to the right person
    if isinstance(target, Character):
        if msg := messages.get("expire_msg_self"):
            await target.send(msg.format(target_name=target_name))
        elif msg := messages.get("expire_msg_target"): # Fallback for debuffs cast by others
             await target.send(msg.format(target_name=target_name))


    if msg_room := messages.get("expire_msg_room"):
        if target.location:
            await target.location.broadcast(f"\\r\\n{msg_room.format(target_name=target_name)}\\r\\n", exclude={target})

async def resolve_consumable_effect(character: Character, item_template: Dict[str, Any], world: 'World') -> bool:
    """Applies the effect of a consumable item (FOOD/DRINK)."""
    try:
        stats = json.loads(item_template.get('stats', '{}') or '{}')
    except json.JSONDecodeError:
        stats = {}

    effect_name = stats.get("effect")
    amount = stats.get("amount")
    item_name = item_template.get('name', 'the item')

    if not effect_name or not isinstance(amount, int):
        await character.send(f"The {item_name} doesn't seem to do anything.")
        return True # Return true to consume the item

    # --- NEW LOGIC START ---
    if effect_name == "restore_hunger":
        if character.hunger >= 100:
            await character.send("You are too full to eat anything else.")
            return False # Do not consume the item
        
        character.hunger = min(100, character.hunger + amount)
        await character.send(f"You eat the {item_name} and feel less hungry.")
        return True

    elif effect_name == "restore_thirst":
        if character.thirst >= 100:
            await character.send("You are too full to drink anything else.")
            return False # Do not consume the item
            
        character.thirst = min(100, character.thirst + amount)
        await character.send(f"You drink the {item_name} and feel refreshed.")
        return True
    # --- NEW LOGIC END ---

    # Keep heal_hp for potions, but food/drink should now use the logic above
    elif effect_name == "heal_hp":
        if character.hp >= character.max_hp:
            await character.send("You are already at full health.")
            return False
        actual_healed = min(amount, character.max_hp - character.hp)
        character.hp += actual_healed
        await character.send(f"You consume the {item_name}, healing for {actual_healed} HP.")
        return True

    else:
        await character.send(f"The {item_name} doesn't seem to do anything.")
        return True
    
async def apply_damage(target: Union['Character', 'Mob'], damage_amount: int, damage_type: str, world: 'World'):
    """
    Applies direct damage to a target from a non-attack source (e.g., traps, falling).
    A simplified version of the main combat damage application logic.
    """
    if not target.is_alive() or damage_amount <= 0:
        return

    # In the future, resistances could be applied here
    final_damage = damage_amount
    target.hp = max(0.0, target.hp - final_damage)

    if isinstance(target, Character):
        await target.send(f"<R>You take {final_damage} {damage_type} damage from the fall!<x>")

    if target.hp <= 0:
        # Create a generic object to represent the "attacker"
        class EnvironmentAttacker:
            name = "the environment"
            location = target.location
        await outcome_handler.handle_defeat(EnvironmentAttacker(), target, world)

def _get_weather_damage_modifier(room: 'Room', damage_type: str) -> float:
    """Returns damage multiplier based on weather conditions in the room."""
    if not room:
        return 1.0
    
    modifier = 1.0

    # WET Conditions
    if "WET" in room.flags:
        if damage_type == "fire":
            modifier *= 0.75 
        elif damage_type == "lightning":
            modifier *= 1.25
    
    # STORMY conditions (bonus to lightning)
    if "STORMY" in room.flags and damage_type == "lightning":
        modifier *= 1.5  # +50%
    
    # FREEZING conditions
    if "FREEZING" in room.flags:
        if damage_type == "cold":
            modifier *= 1.25  # +25%
        elif damage_type == "fire":
            modifier *= 0.9  # -10%
    
    # BLAZING conditions
    if "BLAZING" in room.flags:
        if damage_type == "fire":
            modifier *= 1.25  # +25%
        elif damage_type == "cold":
            modifier *= 0.75  # -25%
    
    # SANDSTORM (reduces all magic)
    if "SANDSTORM" in room.flags:
        if damage_type in ["arcane", "fire", "cold", "lightning"]:
            modifier *= 0.85  # -15%
    
    return modifier