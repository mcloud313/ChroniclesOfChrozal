# game/combat.py
"""
Handles combat calculations and resolution.
"""
import random
import logging
import math
import time
import json
from typing import TYPE_CHECKING, Optional, Union, Dict, Any, Tuple, List

from .character import Character
from .mob import Mob
from .item import Item
from . import utils
from .definitions import abilities as ability_defs

# FIX: This is the circular import fix.
# We only import World for type hinting, not at runtime.
if TYPE_CHECKING:
    from .world import World


MAGICAL_DAMAGE_TYPES = {
    ability_defs.DAMAGE_FIRE, ability_defs.DAMAGE_COLD, ability_defs.DAMAGE_LIGHTNING,
    ability_defs.DAMAGE_EARTH, ability_defs.DAMAGE_ARCANE, ability_defs.DAMAGE_DIVINE,
    ability_defs.DAMAGE_POISON, ability_defs.DAMAGE_SONIC,
}

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
    ability_mods: Optional[Dict[str, Any]] = None,
    damage_multiplier: float = 1.0
):
    """
    Resolves a single physical attack round with detailed calculations and messaging.
    """
    # --- 1. Initial Checks ---
    if not attacker.is_alive() or not target.is_alive() or attacker.location != target.location:
        return

    # --- 2. Gather Attacker & Target Info ---
    attacker_name = attacker.name.capitalize()
    target_name = target.name.capitalize()
    attacker_loc = attacker.location
    
    # --- 3. Determine Attack Variables ---
    base_attacker_rating = attacker.mar
    relevant_weapon_skill: Optional[str] = None
    weapon: Optional[Item] = None
    attk_name = "attack"
    wpn_speed = 2.0
    wpn_base_dmg, wpn_rng_dmg = 1, 0
    dmg_type = ability_defs.DAMAGE_PHYSICAL
    base_stat_modifier = attacker.might_mod

    # Apply ability modifiers if this is a special attack
    if ability_mods:
        base_attacker_rating = math.floor(base_attacker_rating * ability_mods.get('mar_modifier_mult', 1.0))

    if isinstance(attacker, Character):
        if isinstance(attack_source, Item) and attack_source.item_type == "WEAPON":
            weapon = attack_source
            attk_name = f"attack with {weapon.name}"
            wpn_speed, wpn_base_dmg, wpn_rng_dmg, dmg_type = weapon.speed, weapon.damage_base, weapon.damage_rng, weapon.damage_type or "physical"
            if dmg_type == "slash": relevant_weapon_skill = "bladed weapons"
            elif dmg_type == "pierce": relevant_weapon_skill = "piercing weapons"
            elif dmg_type == "bludgeon": relevant_weapon_skill = "bludgeon weapons"
        else: # Unarmed
            attk_name, relevant_weapon_skill, wpn_base_dmg, wpn_rng_dmg = "punch", "martial arts", 1, 2
    elif isinstance(attacker, Mob) and isinstance(attack_source, dict):
        attk_name = attack_source.get("name", "strike")
        wpn_speed = attack_source.get("speed", 2.0)
        wpn_base_dmg, wpn_rng_dmg = attack_source.get("damage_base", 1), attack_source.get("damage_rng", 0)

    # --- 4. Hit Check ---
    weapon_skill_bonus = math.floor(attacker.get_skill_rank(relevant_weapon_skill) / 10) if relevant_weapon_skill else 0
    final_attacker_rating = base_attacker_rating + weapon_skill_bonus
    final_target_dv = target.dv

    hit_roll = random.randint(1, 20)
    is_crit, is_fumble = (hit_roll == 20), (hit_roll == 1)
    is_hit = is_crit or (not is_fumble and (final_attacker_rating + hit_roll) >= final_target_dv)

    # --- 5. Resolve Miss or Fumble ---
    if not is_hit:
        attacker.roundtime = wpn_speed + rt_penalty + attacker.slow_penalty
        await attacker.send(f"You try to {attk_name} {target_name}, but miss.")
        if isinstance(target, Character):
            await target.send(f"{attacker_name} tries to {attk_name} you, but misses.")
        await attacker_loc.broadcast(f"\r\n{attacker_name} misses {target_name}.\r\n", exclude={attacker, target})
        return

    # --- 6. Resolve Block (if hit) ---
    if isinstance(target, Character) and (shield := target.get_shield()):
        shield_skill_rank = target.get_skill_rank("shield usage")
        block_chance = shield.block_chance + (math.floor(shield_skill_rank / 10) * 0.01)
        if random.random() < block_chance:
            attacker.roundtime = wpn_speed + rt_penalty + attacker.slow_penalty 
            await attacker.send(f"{{y{target_name} blocks your {attk_name} with their shield!{{x")
            await target.send(f"{{gYou block {attacker_name}'s {attk_name} with your shield!{{x")
            await attacker_loc.broadcast(f"\r\n{target_name} blocks {attacker_name}'s attack.\r\n", exclude={attacker, target})
            return
        
    # --- 6a. Attacker weapon durability
    if isinstance(attacker, Character) and isinstance(attack_source, Item) and attack_source.item_type == "WEAPON":
        if random.random() < 0.10: # 10% chance
            attack_source.condition -= 1
            # update the database
            await world.db_manager.update_item_condition(attack_source.id, attack_source.condition)

            if attack_source.condition <= 0:
                await attacker.send(f"{{RYour {attack_source.name} shatters into pieces!{{x")
                # Remove from memory
                del attacker._equipped_items[attack_source.wear_location[0]] # Assumes single wield slot
                del world._all_item_instances[attack_source.id]
                # remove from database
                await world.db_manager.delete_item_instance(attack_source.id)
            elif attack_source.condition <= 10:
                await attacker.send(f"{{yYour {attack_source.name} is badly damaged.{{x")

    # --- 7. Calculate Damage ---
    rng_roll_result = random.randint(1, wpn_rng_dmg) if wpn_rng_dmg > 0 else 0
    if is_crit:
        rng_roll_result += roll_exploding_dice(wpn_rng_dmg)
    
    pre_mitigation_damage = max(0, wpn_base_dmg + rng_roll_result + base_stat_modifier)
    
    pre_mitigation_damage = int(pre_mitigation_damage * damage_multiplier)
    
    # --- 8. Mitigate Damage ---
    mit_pds = target.pds
    mit_av = target.get_total_av()
    mit_bv = math.floor(target.barrier_value / 2)
    
    final_damage = max(0, pre_mitigation_damage - mit_pds - mit_av - mit_bv)

    # --- 8a. Target armor durability
    if isinstance(target, Character):
        # Get all equipped armor pieces
        armor_pieces = [item for item in target._equipped_items.values() if item.item_type == "ARMOR"]
        if armor_pieces and random.random() < 0.10: # 10% chance
            # Choose a random piece of armor to damage
            armor_hit = random.choice(armor_pieces)
            armor_hit.condition -= 1
            # Update the database
            await world.db_manager.update_item_condition(armor_hit.id, armor_hit.condition)

            if armor_hit.condition <= 0:
                await target.send(f"{{RYour {armor_hit.name} is destroyed by the blow!{{x")
                # Remove from memory
                del target._equipped_items[armor_hit.wear_location] # Assumes single slot
                del world._all_item_instances[armor_hit.id]
                # Remove from database
                await world.db_manager.delete_item_instance(armor_hit.id)
            elif armor_hit.condition <= 10:
                await target.send(f"{{yYour {armor_hit.name} was damaged.{{x")

    #8b. Apply resistances/vulnerabilities ----
    resistance = target.resistances.get(dmg_type, 0.0)
    if resistance != 0:
        multiplier = 1.0 - (resistance / 100.0)
        final_damage = int(final_damage * multiplier)


    # --- 9. Apply Damage & Send Messages ---
    target.hp = max(0.0, target.hp - final_damage)
    
    hit_desc = "{rCRITICALLY HIT{x" if is_crit else "hit"
    if isinstance(attacker, Character):
        await attacker.send(f"You {hit_desc} {target_name} for {{y{int(final_damage)}{{x damage!")
    if isinstance(target, Character):
        await target.send(f"{{R{attacker_name} {hit_desc.upper()}S you for {{y{int(final_damage)}{{x damage!{{x ({int(target.hp)}/{int(target.max_hp)} HP)")
    if attacker_loc:
        await attacker_loc.broadcast(f"\r\n{attacker_name} {hit_desc}s {target_name}!\r\n", exclude={attacker, target})

    if isinstance(target, Character) and target.status == "MEDITATING" and final_damage > 0:
        target.status = "ALIVE"
        await target.send("{RThe force of the blow shatters your concentration!{x")
        if attacker_loc:
            await attacker_loc.broadcast(f"\r\n{target_name} is snapped out of their meditative trance by the attack!\r\n", exclude={target})

    # --- 10. Apply Roundtime ---
    rt_penalty = 0.0
    if isinstance(attacker, Character):
        rt_penalty = attacker.get_total_av() * 0.05
    attacker.roundtime = wpn_speed + rt_penalty + attacker.slow_penalty
    
    # --- 11. Check for Defeat ---
    if target.hp <= 0:
        await handle_defeat(attacker, target, world)

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

    # --- 1. Get Power and Defense ---
    caster_rating = caster.apr if effect_details.get("school") == "Arcane" else caster.dpr
    final_target_dv = target.dv

    # --- 2. Hit Check ---
    hit_roll = random.randint(1, 20)
    is_crit, is_fumble = (hit_roll == 20), (hit_roll == 1)
    is_hit = is_crit or (not is_fumble and (caster_rating + hit_roll) >= final_target_dv)

    # --- 3. Resolve Miss ---
    if not is_hit:
        await caster.send(f"Your {spell_data['name']} misses {target_name}.")
        return

    # --- 4. Calculate Damage ---
    base_dmg = effect_details.get("damage_base", 0)
    rng_dmg = effect_details.get("damage_rng", 0)
    rng_roll_result = random.randint(1, rng_dmg) if rng_dmg > 0 else 0
    if is_crit:
        rng_roll_result += roll_exploding_dice(rng_dmg)
    
    stat_modifier = caster.apr if effect_details.get("school") == "Arcane" else caster.dpr
    pre_mitigation_damage = max(0, base_dmg + rng_roll_result + stat_modifier)

    # --- 5. Mitigate Damage ---
    mit_sds = target.sds
    mit_bv = target.barrier_value
    final_damage = max(0, pre_mitigation_damage - mit_sds - mit_bv)

    dmg_type = effect_details.get("damage_type")
    if dmg_type:
        resistance = target.resistances.get(dmg_type, 0.0)
        if resistance != 0:
            multiplier = 1.0 - (resistance / 100.0)
            final_damage = int(final_damage * multiplier)

    # --- 6. Apply Damage & Send Messages ---
    target.hp = max(0.0, target.hp - final_damage)
    
    hit_desc = "{rCRITICALLY HITS{x" if is_crit else "hits"
    if isinstance(caster, Character):
        await caster.send(f"Your {spell_data['name']} {hit_desc} {target_name} for {{y{int(final_damage)}{{x damage!")
    if isinstance(target, Character):
        await target.send(f"{{R{caster_name}'s {spell_data['name']} {hit_desc} you for {{y{int(final_damage)}{{x damage!{{x ({int(target.hp)}/{int(target.max_hp)} HP)")
    if caster.location:
        await caster.location.broadcast(f"\r\n{caster_name}'s {spell_data['name']} {hit_desc} {target_name}!\r\n", exclude={caster, target})

    if isinstance(target, Character) and target.status == "MEDITATING" and final_damage > 0:
        target.status = "ALIVE"
        await target.send("{RThe magical assault disrupts your meditation!{x")
        if caster.location:
            await caster.location.broadcast(f"\r\n{target_name} is snapped out of their meditative trance by the attack!\r\n", exclude={target})

    # --- 7. Check for Defeat ---
    if target.hp <= 0:
        await handle_defeat(caster, target, world)

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

    # --- 1. Find Target ---
    target: Optional[Union[Character, Mob]] = None
    if target_type_str == "SELF":
        target = caster
    elif target_type_str in ("CHAR", "CHAR_OR_MOB") and isinstance(target_ref, int):
        target = world.get_active_character(target_ref)
    
    if not target and target_type_str in ("MOB", "CHAR_OR_MOB") and isinstance(target_ref, int):
        if caster.location:
            target = next((m for m in caster.location.mobs if m.instance_id == target_ref), None)

    # --- 2. Validate Target ---
    required_target_type = ability_data.get("target_type")
    if required_target_type != ability_defs.TARGET_NONE and (
        target is None or not target.is_alive() or (target != caster and target.location != caster.location)
    ):
        await caster.send("Your target is no longer valid.")
        return

    # --- 3. Resolve Effect ---
    log.debug("Resolving effect '%s' for %s. Caster: %s, Target: %s",
              effect_type, ability_key, caster.name, getattr(target, 'name', 'None'))

    if effect_type == ability_defs.EFFECT_DAMAGE:
        await resolve_magical_attack(caster, target, ability_data, world)
    
    elif effect_type == ability_defs.EFFECT_HEAL:
        await apply_heal(caster, target, effect_details, world)
    
    elif effect_type in (ability_defs.EFFECT_BUFF, ability_defs.EFFECT_DEBUFF):
        await apply_effect(caster, target, effect_details, ability_data, world)
    
    elif effect_type == ability_defs.EFFECT_MODIFIED_ATTACK:
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

        await handle_defeat(EffectAttacker(), target, world)

async def handle_defeat(attacker: Union[Character, Mob], target: Union[Character, Mob], world: 'World'):
    """Handles logic for when a target's HP reaches 0, with group reward sharing."""
    attacker_name = getattr(attacker, 'name', 'Something').capitalize()
    target_name = getattr(target, 'name', 'Something').capitalize()
    target_loc = getattr(target, 'location', None)

    log.info("%s has defeated %s!", attacker_name, target_name)

    # --- Mob Defeat Logic ---
    if isinstance(target, Mob):
        if isinstance(attacker, Character):
            await attacker.send(f"You have slain {target_name}!")
        if target_loc:
            await target_loc.broadcast(f"\r\n{attacker_name} has slain {target_name}!\r\n", exclude={attacker})
        
        target.die()
        
        dropped_coinage, dropped_item_ids = determine_loot(target.loot_table)
        base_xp = 50
        xp_gain = max(1, target.level * base_xp + random.randint(-base_xp // 2, base_xp // 2))
        killer = attacker if isinstance(attacker, Character) else None

        # Check if this was a group kill with other members present
        is_group_kill = False
        if killer and killer.group:
            present_members = [m for m in killer.group.members if m.location == killer.location and m.is_alive()]
            if len(present_members) > 1:
                is_group_kill = True

        # --- Group Kill Logic ---
        if is_group_kill:
            group_xp_total = int(xp_gain * 0.80) # 80% XP penalty/bonus for groups
            xp_per_member = group_xp_total // len(present_members)
            
            coins_per_member = dropped_coinage // len(present_members)
            remainder_coins = dropped_coinage % len(present_members)
            
            await killer.group.broadcast(f"{{yYour group receives {group_xp_total} XP and {utils.format_coinage(dropped_coinage)}!{{x")
            
            for member in present_members:
                await award_xp_to_character(member, xp_per_member)
                member.coinage += coins_per_member
            
            killer.group.leader.coinage += remainder_coins

        # --- Solo Kill Logic ---
        elif killer:
            await award_xp_to_character(killer, xp_gain)
            if dropped_coinage > 0 and target_loc:
                await target_loc.add_coinage(dropped_coinage, world)
                await target_loc.broadcast(f"\r\n{utils.format_coinage(dropped_coinage)} falls from {target_name}!\r\n")

        # --- Item Drop Logic (Shared by Solo and Group) ---
        if dropped_item_ids and target_loc:
            dropped_item_names = []
            for template_id in dropped_item_ids:
                # Create a new unique instance of the item in the room
                instance_data = await world.db_manager.create_item_instance(template_id, room_id=target_loc.dbid)
                if instance_data:
                    template = world.get_item_template(template_id)
                    item_obj = Item(instance_data, template)

                    # Add the new item to the world's in memory state
                    world._all_item_instances[item_obj.id] = item_obj
                    target_loc.item_instance_ids.append(item_obj.id)
                    dropped_item_names.append(template['name'])
            if dropped_item_names:
                await target_loc.broadcast(f"\r\n{target_name}'s corpse drops: {', '.join(dropped_item_names)}.\r\n")

    # --- Character Defeat Logic ---
    elif isinstance(target, Character) and target.status == "ALIVE":
        target.hp, target.status, target.stance = 0, "DYING", "Lying"
        target.is_fighting, target.target, target.casting_info = False, None, None

        target.xp_pool = 0.0
        xp_at_start_of_level = utils.xp_needed_for_level(target.level - 1) if target.level > 1 else 0
        xp_progress = target.xp_total - xp_at_start_of_level
        xp_penalty = math.floor(xp_progress * 0.10)
        target.xp_total = max(xp_at_start_of_level, target.xp_total - xp_penalty)
        
        await target.send("{rYou feel some of your experience drain away...{x")

        timer_duration = float(target.stats.get('vitality', 10))
        target.death_timer_ends_at = time.monotonic() + timer_duration
        
        coinage_to_drop = int(target.coinage * 0.10)
        if coinage_to_drop > 0 and target_loc:
            target.coinage -= coinage_to_drop
            await target_loc.add_coinage(coinage_to_drop, world)
            await target_loc.broadcast(f"\r\nSome coins fall from {target.name} as they collapse!\r\n", exclude={target})

        await target.send("\r\n{r*** YOU ARE DYING! ***{x")
        if target_loc:
            await target_loc.broadcast(f"\r\n{target_name} collapses to the ground, dying!\r\n", exclude={target})

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
    """Applies healing to a target."""
    if not target.is_alive():
        await caster.send(f"{target.name.capitalize()} cannot be healed now.")
        return

    heal_amount = effect_details.get("heal_base", 0) + random.randint(0, effect_details.get("heal_rng", 0))
    if heal_amount <= 0: return

    actual_healed = min(heal_amount, target.max_hp - target.hp)
    target.hp += actual_healed

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
        "stat": stat,
        "type": effect_details.get('type'),
        "caster_id": caster.dbid
    }
    log.info("Applied effect '%s' to %s for %.1f seconds.", effect_name, target.name, duration)

    # Check for and apply instant effects like stun
    if effect_details.get('type') == 'stun':
        stun_duration = effect_details.get('potency', 0.0)
        target.roundtime += stun_duration
        if isinstance(target, Character):
            await target.send("{RYou are stunned!{x")
        if target.location:
            await target.location.broadcast(f"\r\n{target.name.capitalize()} is stunned!\r\n", exclude={target})

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