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

async def resolve_physical_attack(
    attacker: Union[Character, Mob],
    target: Union[Character, Mob],
    attack_source: Optional[Union[Item, Dict[str, Any]]],
    world: 'World',
    damage_multiplier: float = 1.0
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

    # ---Resolve Hit/Miss ---
    hit_result = hit_resolver.check_physical_hit(attacker, target)
    rt_penalty = attacker.total_av * 0.05 if isinstance(attacker, Character) else 0.0
    
    if not hit_result.is_hit:
        roll_details = f"{{i[Roll: {hit_result.roll} + MAR: {hit_result.attacker_rating} vs DV: {hit_result.target_dv}]{{x"
        if isinstance(attacker, Character):
            await attacker.send(f"You miss {target.name} with your {utils.strip_article(attack_name)}. {roll_details}")
        if isinstance(target, Character):
            await target.send(f"{attacker.name.capitalize()}'s {attack_name} misses you.")
        attacker.roundtime = 1.0 + rt_penalty + attacker.slow_penalty
        return
    
    # --- Resolve Parry ---
    if isinstance(target, Character) and (weapon := target._equipped_items.get("main_hand")):
        parry_skill_rank = target.get_skill_rank("parrying")
        parry_chance = parry_skill_rank * 0.005 # 0.5% chance per rank
        if random.random() < parry_chance:
            await attacker.send(f"{{y{target.name} parries your attack with their {weapon.name}!{{x")
            await target.send(f"{{gYou parry {attacker.name}'s attack with your {weapon.name}!{{x")
            attacker.roundtime = 1.0 + rt_penalty + attacker.slow_penalty
            return

    # ---Resolve Block ---
    if isinstance(target, Character) and (shield := target.get_shield()):
        shield_skill_rank = target.get_skill_rank("shield usage")
        block_chance = shield.block_chance + (math.floor(shield_skill_rank / 10) * 0.01)
        if random.random() < block_chance:
            await attacker.send(f"{{y{target.name} blocks your attack with their shield!{{x")
            await target.send(f"{{gYou block {attacker.name}'s attack with your shield!{{x")
            # Apply correct roundtime on a block
            attacker.roundtime = wpn_speed + rt_penalty + attacker.slow_penalty
            return
        
    # ---Calculate and Mitigate Damage ---
    damage_info = damage_calculator.calculate_physical_damage(attacker, attack_source, hit_result.is_crit)
    damage_info.attack_name = attack_name # Add attack_name to the info object
    if damage_multiplier != 1.0:
        damage_info.pre_mitigation_damage = int(damage_info.pre_mitigation_damage * damage_multiplier)
    final_damage = damage_calculator.mitigate_damage(target, damage_info)

    #--- Handle Consequences
    if isinstance(attack_source, Item):
        await outcome_handler.handle_durability(attacker, target, attack_source, world)
    outcome_handler.apply_damage(target, final_damage)
    await outcome_handler.send_attack_messages(attacker, target, hit_result, damage_info, final_damage)

    if target.hp <= 0:
        await outcome_handler.handle_defeat(attacker, target, world)
        return
    
    # --- 8. Apply Final Roundtime for a successful hit ---
    attacker.roundtime = wpn_speed + rt_penalty + attacker.slow_penalty

    log.info(
        f"[COMBAT-DEBUG] Roundtime for {attacker.name}: "
        f"{attacker.roundtime:.2f}s (Speed: {wpn_speed:.2f}s, "
        f"Armor Penalty: {rt_penalty:.2f}s, Slow Penalty: {attacker.slow_penalty:.2f}s)"
    )

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

    # --- Resolve Hit/Miss (using RAR instead of MAR) ---
    hit_result = hit_resolver.check_physical_hit(attacker, target, use_rar=True) # We will add this flag

    if not hit_result.is_hit:
        roll_details = f"{{i[Roll: {hit_result.roll} + RAR: {hit_result.attacker_rating} vs DV: {hit_result.target_dv}]{{x"
        if isinstance(attacker, Character):
            await attacker.send(f"Your {utils.strip_article(ammo.name)} misses {target.name}. {roll_details}")
        if isinstance(target, Character):
            await target.send(f"{attacker.name.capitalize()}'s {ammo.name} flies past you.")
        await attacker.location.broadcast(f"\r\n{attacker.name.capitalize()}'s shot goes wide of {target.name}!\r\n", {attacker, target})
        return
        
    # Ranged attacks cannot be parried or blocked by default. This can be changed later.

    # --- Calculate and Mitigate Damage ---
    # Damage is primarily from the weapon, with a possible bonus from ammo
    damage_info = damage_calculator.calculate_physical_damage(attacker, weapon, hit_result.is_crit)
    
    # Add bonus from ammo
    ammo_bonus = ammo.instance_stats.get("damage_bonus", 0)
    damage_info.pre_mitigation_damage += ammo_bonus
    
    damage_info.attack_name = ammo.name # The projectile is what hits
    final_damage = damage_calculator.mitigate_damage(target, damage_info)

    # --- Handle Consequences ---
    outcome_handler.apply_damage(target, final_damage)
    # We need a ranged-specific message handler
    await outcome_handler.send_ranged_attack_messages(attacker, target, hit_result, damage_info, final_damage)

    if target.hp <= 0:
        await outcome_handler.handle_defeat(attacker, target, world)

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

    # ---Get Power and Defense Ratings ---
    school = effect_details.get("school", "Arcane")
    rating_name = "APR" if school == "Arcane" else "DPR"

    hit_result = hit_resolver.check_magical_hit(caster, target, school)

    if not hit_result.is_hit:
        roll_details = f"{{i[Roll: {hit_result.roll} + {rating_name}: {hit_result.attacker_rating} vs DV: {hit_result.target_dv}]{{x"
        if isinstance(caster, Character):
            await caster.send(f"Your {spell_name} misses {target_name}. {roll_details}")
        if isinstance(target, Character):
             await target.send(f"{caster_name}'s {spell_name} misses you.")
        return
    
    # ---Calculate Damage ---
    damage_info = damage_calculator.calculate_magical_damage(caster, spell_data, hit_result.is_crit)
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

    # Apply any rider effects (e.g., a stun that accompanies the damage)
    if hit_result.is_hit and (rider_effect := effect_details.get("applies_effect")):
        await apply_effect(caster, target, rider_effect, spell_data, world)

    # --- 6. Check for Defeat ---
    if target.hp <= 0:
        await outcome_handler.handle_defeat(caster, target, world)

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
    if target_type_str == "SELF":
        target = caster
    elif target_type_str in ("CHAR", "CHAR_OR_MOB") and isinstance(target_ref, int):
        target = world.get_active_character(target_ref)
    
    if not target and target_type_str in ("MOB", "CHAR_OR_MOB") and isinstance(target_ref, int):
        if caster.location:
            target = next((m for m in caster.location.mobs if m.instance_id == target_ref), None)

    # --- 3. Validate Target ---
    required_target_type = ability_data.get("target_type")
    if required_target_type != ability_defs.TARGET_NONE and (
        target is None or not target.is_alive() or (target != caster and target.location != caster.location)
    ):
        await caster.send("Your target is no longer valid.")
        return

    # --- 4. Resolve Effect ---
    log.debug("Resolving effect '%s' for %s. Caster: %s, Target: %s",
              effect_type, ability_key, caster.name, getattr(target, 'name', 'None'))

    if effect_type == ability_defs.EFFECT_DAMAGE:
        # --- NEW: Handle Cone AoE spells like Burning Hands ---
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
            # Original single-target damage logic
            await resolve_magical_attack(caster, target, ability_data, world)
    
    elif effect_type == ability_defs.EFFECT_HEAL:
        await apply_heal(caster, target, effect_details, world)
    
    elif effect_type in (ability_defs.EFFECT_BUFF, ability_defs.EFFECT_DEBUFF):
        await apply_effect(caster, target, effect_details, ability_data, world)
    
    elif effect_type == ability_defs.EFFECT_MODIFIED_ATTACK:
        
        if effect_details.get("is_cleave"):
            primary_target = target # The target resolved by the block above
            
            # Find other potential targets in the room
            other_mobs = [m for m in caster.location.mobs if m.is_alive() and m != primary_target]
            random.shuffle(other_mobs) # Shuffle to hit random secondary targets
            
            max_targets = effect_details.get("max_cleave_targets", 1)
            secondary_targets = other_mobs[:max_targets - 1]
            
            all_targets = [primary_target] + secondary_targets
            
            await caster.send(ability_data["messages"]["caster_self"])
            await caster.location.broadcast(f"\r\n{ability_data['messages']['room'].format(caster_name=caster.name)}\r\n", exclude={caster})

            # Get the weapon once
            weapon = caster._equipped_items.get("WIELD_MAIN")
            damage_mult = effect_details.get("damage_multiplier", 1.0)
            
            # Attack each target in the list
            for t in all_targets:
                await resolve_physical_attack(caster, t, weapon, world, damage_multiplier=damage_mult)
            return # End of Cleave logic
        
        if effect_details.get("requires_stealth_or_flank"):
            is_stealthed = caster.is_hidden
            is_flanking = (isinstance(target, Mob) and target.is_fighting and target.target != caster)

            if not is_stealthed and not is_flanking:
                await caster.send("You must be hidden or attacking an engaged target to backstab!")
                return # Stop the ability

        # Get the damage multiplier from the ability's data
        damage_mult = effect_details.get("damage_multiplier", 1.0)
        
        weapon = None
        # Use .get() on _equipped_items for safety
        if (weapon_obj := caster._equipped_items.get("WIELD_MAIN")):
            weapon = weapon_obj
            
        await resolve_physical_attack(caster, target, weapon, world, 
                                      ability_mods=effect_details, 
                                      damage_multiplier=damage_mult)
        
    elif effect_type == "RESURRECT":
        if not isinstance(target, Character) or target.status != "DEAD":
            await caster.send("Your spell requires a dead target.")
            return

        # Check for and consume the XP cost from the caster's pool
        xp_cost = effect_details.get("xp_cost", 5000)
        if caster.xp_total < xp_cost:
            await caster.send(f"{{RYou lack the spiritual energy ({xp_cost} XP) to perform the ritual.{{x")
            return
        
        caster.xp_total -= xp_cost
        await caster.send(f"{{yYou sacrifice {xp_cost} of your stored experience to fuel the ritual...{{x")

        # Perform the resurrection
        target.status = "ALIVE"
        target.hp = 1
        
        # Move the resurrected player to the caster's location
        if target.location != caster.location:
            if old_room := target.location:
                old_room.remove_character(target)
            target.update_location(caster.location)
            caster.location.add_character(target)

        await world.broadcast(f"{{Y{caster.name}'s divine intervention brings {target.name} back from the dead!{{x")

    elif effect_type == "CURE":
        cure_type = effect_details.get("cure_type")
        if not cure_type: return

        # Find and remove all effects of the specified type
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
        if effect_details.get("requires_shield", False) and not caster.get_shield(world):
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

        # Perform a skill vs skill contest
        attacker_mod = caster.get_skill_modifier(contest_details["attacker_skill"])
        defender_mod = target.get_skill_modifier(contest_details["defender_skill"])

        attacker_roll = random.randint(1, 20) + attacker_mod
        defender_roll = random.randint(1, 20) + defender_mod

        if attacker_roll > defender_roll:
            # Attacker wins, apply the 'on_success' effects
            await caster.send(f"{{gYou successfully trip {target.name}!{{x")
            success_effects = effect_details.get("on_success")
            if success_effects:
                await apply_effect(caster, target, success_effects, ability_data, world)
        else:
            # Defender wins
            await caster.send(f"{{rYou fail to trip {target.name}.{{x")

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
        await target.send(f"{{rYou take {int(damage)} {effect_type} damage!{{x")

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

async def apply_effect(caster: Character, target: Union[Character, Mob], effect_details: Dict[str, Any], ability_data: Dict[str, Any], world: 'World'):
    """Applies a temporary BUFF or DEBUFF effect to the target."""
    effect_name = effect_details.get("name", "UnknownEffect")
    duration = effect_details.get("duration", 0.0)
    stat = effect_details.get("stat_affected")
    amount = effect_details.get("amount")

    if not all([duration > 0, stat, amount is not None]):
        log.error("Invalid effect data for '%s': %s", effect_name, effect_details)
        await caster.send("The effect seems to dissipate harmlessly.")
        return

    target.effects[effect_name] = {
        "ends_at": time.monotonic() + duration,
        "amount": amount,
        "stat_affected": stat, # Changed from "stat" to "stat_affected" for consistency
        "type": effect_details.get('type'),
        "caster_id": caster.dbid,
        "source_ability_key": ability_data.get("internal_name")
    }
    log.info("Applied effect '%s' to %s for %.1f seconds.", effect_name, target.name, duration)

    if stat == "max_hp":
        target.max_hp += amount
        target.hp += amount # Also grant the current HP

    # Check for and apply instant effects like stun
    if effect_details.get('type') == 'stun':
        stun_duration = effect_details.get('potency', 0.0)
        target.roundtime += stun_duration
        if isinstance(target, Character):
            await target.send("{RYou are stunned!{x")
        if target.location:
            await target.location.broadcast(f"\r\n{target.name.capitalize()} is stunned!\r\n", exclude={target})

    if new_stance := effect_details.get('set_stance'):
        if isinstance(target, Character):
            target.stance = new_stance

    if effect_details.get("is_shapechange"):
        # Iterate over a copy of the items, as we may modify the dictionary
        for effect_key, effect_data in list(target.effects.items()):
            # Find the source ability for the existing effect
            source_key = effect_data.get("source_ability_key")
            if not source_key: continue
            
            source_ability = world.abilities.get(source_key)
            if not source_ability: continue

            # Check if the existing effect is also a shapechange
            if source_ability.get("effect_details", {}).get("is_shapechange"):
                # Remove the old shapechange effect
                del target.effects[effect_key]
                # Send the expiration message for the old form
                old_messages = source_ability.get("messages", {})
                if msg := old_messages.get("expire_msg_self"):
                    if isinstance(target, Character):
                        await target.send(msg)

    # --- Messaging ---
    caster_name = caster.name.capitalize()
    target_name = target.name.capitalize()
    msg_self = ability_data.get('apply_msg_self')
    msg_target = ability_data.get('apply_msg_target')
    msg_room = ability_data.get('apply_msg_room')
    
    if msg_self and caster == target:
        await caster.send(msg_self.format(caster_name=caster_name, target_name=target_name))
    elif msg_target and isinstance(target, Character):
        await target.send(msg_target.format(caster_name=caster_name, target_name=target_name))
        await caster.send(f"You apply {effect_name} to {target_name}.")

    if msg_room and target.location:
        await target.location.broadcast(f"\r\n{msg_room.format(caster_name=caster_name, target_name=target_name)}\r\n", exclude={caster, target})

async def resolve_consumable_effect(character: Character, item_template: Dict[str, Any], world: 'World') -> bool:
    """Applies the effect of a consumable item (FOOD/DRINK)."""
    try:
        stats = json.loads(item_template.get('stats', '{}') or '{}')
    except json.JSONDecodeError:
        stats = {}

    effect_name = stats.get("effect")
    amount = stats.get("amount")
    item_name = item_template.get('name', 'the item')

    if not effect_name:
        await character.send(f"The {item_name} doesn't seem to do anything.")
        return True

    if effect_name == "heal_hp" and isinstance(amount, (int, float)):
        if character.hp >= character.max_hp:
            await character.send("You are already at full health.")
            return False
        actual_healed = min(amount, character.max_hp - character.hp)
        character.hp += actual_healed
        await character.send(f"You consume {item_name}, healing {int(actual_healed)} hit points.")
        return True
    
    await character.send(f"You consume {item_name}, but nothing seems to happen.")
    return True