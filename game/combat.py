# game/combat.py
"""
Handles combat calculations and resolution.
"""
import random
import logging
import math
import time
import json
from typing import TYPE_CHECKING, Optional, Union, Dict, Any, Tuple, List # Added Union

# --- Runtime Imports ---
# Import classes needed for isinstance() checks and logic
from .character import Character
from .mob import Mob
from .item import Item
from .world import World
from . import utils
from .definitions import abilities as ability_defs


log = logging.getLogger(__name__)

# Placeholder functions - implementations below
# async def resolve_physical_attack(attacker: Union['Character', 'Mob'], target: Union['Character', 'Mob'], weapon: Optional['Item']): pass
# def roll_exploding_dice(max_roll: int) -> int: pass
# async def handle_defeat(attacker: Union['Character', 'Mob'], target: Union['Character', 'Mob']): pass
# def determine_loot(loot_table: Dict[str, Any]) -> Tuple[int, List[int]]: pass
# async def award_xp(attacker: Union['Character', 'Mob'], defeated_mob: 'Mob'): pass

def roll_exploding_dice(max_roll: int) -> int:
    """Rolls d(max_roll), exploding on max result."""
    if max_roll <= 0: return 0
    total = 0; rolls = 0; max_explosions = 10
    while rolls < max_explosions:
        roll = random.randint(1, max_roll)
        total += roll
        if roll < max_roll: break
        rolls += 1; log.debug("Exploding die! (Rolled %d)", max_roll)
    if rolls == max_explosions: log.warning(...)
    return total

async def handle_defeat(attacker: Union['Character', 'Mob'], target: Union['Character', 'Mob'], world: 'World'):
    """Handles logic when a target's HP reaches 0."""
    attacker_name = getattr(attacker, 'name', 'Something').capitalize()
    target_name = getattr(target, 'name', 'Something').capitalize() # Capitalize names for messages
    target_loc = getattr(target, 'location', None)
    log.info("%s has defeated %s!", attacker_name, target_name)

    # --- If Mob is defeated ---
    if isinstance(target, Mob):
        slain_msg = f"\r\n{attacker_name} has slain {target_name}!\r\n"
        if target_loc:
            await target_loc.broadcast(slain_msg, exclude={attacker})
        target.die() # Set hp=0, time_of_death, clear target

        #Calculate and place loot/coinage in room
        dropped_coinage, dropped_item_ids = determine_loot(target.loot_table)

        if dropped_coinage > 0 and target_loc:
            log.info("%s corpse drops %d coinage in Room %d.", target_name.capitalize(), dropped_coinage, target_loc.dbid)
            coinage_added = await target_loc.add_coinage(dropped_coinage, world)
            # --- ^ ^ ^ ---
            if coinage_added: await target_loc.broadcast(...) # Announce only if added successfully
            else: log.error("Failed to add dropped coinage %d to room %d", dropped_coinage, target_loc.dbid)

        if dropped_item_ids and target_loc:
            dropped_item_names = []
            for item_id in dropped_item_ids:
                # Add item to room cache AND database
                item_added = await target_loc.add_item(item_id, world) 
                if item_added:
                    template = world.get_item_template(item_id)
                    dropped_item_names.append(template['name'] if template else f"Item #{item_id}")
                else:
                    log.error("Failed to add dropped item %d to room %d", item_id, target_loc.dbid)
            if dropped_item_names:
                log.info("%s dropped items: %s in room %s", target_name.capitalize(), dropped_item_names, target_loc.dbid)
                drop_msg = f"\r\n{target_name.capitalize()}'s corpse drops: {', '.join(dropped_item_names)}.\r\n"
                await target_loc.broadcast(drop_msg, exclude={attacker}) # Announce item drop

        # Award XP (simple V1: only attacker gets pool XP)
        if isinstance(attacker, Character):
            await award_xp(attacker, target)

        # Remove mob object from room's active set (it's dead, waiting for respawn)
        # Respawn logic in Room.check_respawn handles bringing it back
        # target.location.remove_mob(target) # Keep the dead object for respawn timer

    # --- If Character is defeated ---
    elif isinstance(target, Character):
        if target.status == "ALIVE": # Only trigger dying sequence once
            target.hp = 0 # Ensure HP is 0
            target.status = "DYING"
            target.stance = "Lying"
            target.is_fighting = False
            target.target = None
            # Calculate death timer based on Vitality score
            vit_score = target.stats.get('vitality', 10)
            timer_duration = float(vit_score) * 2 # Example: 1 second per vit point
            target.death_timer_ends_at = time.monotonic() + timer_duration

            log.info("Character %s is now DYING (Timer: %.1f s).", target.name, timer_duration)

            # Drop Coinage (calculate 10%)
            coinage_to_drop = int(target.coinage * 0.10)
            if coinage_to_drop > 0 and target_loc:
                target.coinage -= coinage_to_drop
                log.info("%s drops %d coinage upon dying!", target.name, coinage_to_drop)
                await target_loc.add_coinage(coinage_to_drop, world) # Requires db_conn!
                await target_loc.broadcast(f"\r\nSome coins fall from {target.name} as they collapse!\r\n", exclude={target})

            # Send messages
            await target.send("\r\n*** You are DYING! ***\r\n")
            await target.location.broadcast(f"\r\n{target.name} collapses to the ground, dying!\r\n", exclude={target})

            # Decrement spiritual tether later (Phase 4)
            # log.info("%s loses spiritual tether.", target.name)

        else:
            log.warning("handle_defeat called on already non-ALIVE character %s.", target.name)

    else:
        log.error("handle_defeat called with invalid target type: %r", target)

def determine_loot(loot_table: Dict[str, Any]) -> Tuple[int, List[int]]:
    """
    Calculates loot based ONLY on the provided loot_table dictionary.

    Args:
        loot_table: The loot dictionary loaded from the mob template
                    (e.g., {"coinage_max": 5, "items": [{"template_id": 7, "chance": 0.1}]})

    Returns:
        Tuple containing (dropped_coinage, list_of_dropped_item_template_ids)
    """
    dropped_coinage = 0
    dropped_item_ids = []

    # --- Standard Loot Table Items ---
    # This section correctly handles ALL item drops defined in the DB JSON
    item_list = loot_table.get("items", [])
    if isinstance(item_list, list):
        for item_info in item_list:
            # Double check item_info structure before accessing keys
            if isinstance(item_info, dict):
                template_id = item_info.get("template_id")
                chance = item_info.get("chance", 0.0)
                # Ensure template_id is valid int and chance is valid number
                if template_id and isinstance(template_id, int) and \
                isinstance(chance, (float, int)) and 0.0 <= chance <= 1.0:
                    if random.random() < chance:
                        dropped_item_ids.append(template_id)
                else:
                    log.warning("Invalid item entry in loot table: %r", item_info)
            else:
                log.warning("Non-dict entry found in items list within loot table: %r", item_info)

    # --- Coinage (from loot table) ---
    max_coinage = loot_table.get("coinage_max", 0)
    # Add type check for safety
    if isinstance(max_coinage, int) and max_coinage > 0:
        dropped_coinage = random.randint(0, max_coinage)
    log.debug("Determine Loot Results: Coinage=%d, ItemIDs=%s", dropped_coinage, dropped_item_ids) # ADD THIS
    return dropped_coinage, dropped_item_ids

async def award_xp(attacker: 'Character', defeated_mob: 'Mob'):
    """Awards XP to the attacker's XP Pool (simple V1)."""
    # Basic formula: mob level * base amount? Add randomness?
    base_xp = 50 # Example base
    xp_gain = defeated_mob.level * base_xp + random.randint(-base_xp//2, base_xp//2)
    xp_gain = max(1, xp_gain) # Ensure at least 1 XP

    intellect = attacker.stats.get("intellect", 10) # Default 10 int
    xp_pool_cap = intellect * 100
    current_pool = attacker.xp_pool

    space_available = max(0, xp_pool_cap - current_pool)
    actual_xp_added = min(xp_gain, space_available)
    xp_lost = xp_gain - actual_xp_added

    if actual_xp_added > 0:
        attacker.xp_pool += actual_xp_added
        await attacker.send(f"You gain {actual_xp_added} experience points into your pool.")
    else:
        await attacker.send("Your mind cannot hold any more raw experience right now.")
        return
    # TODO: Distribute XP among party members later

# --- Main Combat Resolution ---
async def resolve_physical_attack(
    attacker: Union[Character, Mob],
    target: Union[Character, Mob],
    attack_source: Optional[Union[Item, Dict[str, Any]]],
    world: World,
    ability_mods: Optional[Dict[str, Any]] = None
):
    """Resolves a single physical attack round."""

    # 1. Checks (Remain the same)
    if not attacker.is_alive() or not target.is_alive(): return
    if not hasattr(attacker, 'location') or not hasattr(target, 'location') or attacker.location != target.location:
        log.debug("Resolve Attack: Attacker or Target missing location or not in same room.")
        return

    # 2. Get Attack/Defense Info & Apply Skills
    attacker_name = attacker.name.capitalize()
    target_name = target.name.capitalize()

    # --- Attacker Setup ---
    base_attacker_rating = attacker.mar # Base Melee Attack Rating
    relevant_weapon_skill: Optional[str] = None
    weapon: Optional[Item] = None
    # Default attack values (unarmed/mob default)
    attk_name: str = "attack"
    wpn_speed: float = 2.0
    wpn_base_dmg: int = 1
    wpn_rng_dmg: int = 0
    dmg_type: str = "physical"
    stat_modifier: int = attacker.might_mod # Default modifier

    bonus_rt_from_abilit = 0.0
    if ability_mods:
        log.debug("Applying ability modifiers: %s", ability_mods)
        mar_mult = ability_mods.get('mar_modifier_mult', 1.0)
        base_attacker_rating = math.floor(base_attacker_rating * mar_mult)
        rng_mult = ability_mods.get('rng_damage_mult', 1.0)
        wpn_rng_dmg = math.floor(wpn_rng_dmg * rng_mult)
        wpn_base_dmg += ability_mods.get('bonus_damage', 0)
        bonus_rt_from_ability = ability_mods.get('bonus_rt', 0.0)

    # Determine specifics based on attacker type and attack_source
    if isinstance(attacker, Mob):
        mob_attack_data = attack_source # attack_source should be the dict
        if isinstance(mob_attack_data, dict):
            attk_name = mob_attack_data.get("name", "strike")
            wpn_speed = mob_attack_data.get("speed", 2.0)
            wpn_base_dmg = mob_attack_data.get("damage_base", 1)
            wpn_rng_dmg = mob_attack_data.get("damage_rng", 0)
            # dmg_type = mob_attack_data.get("damage_type", "physical") # TODO Later
            # stat_modifier = attacker.might_mod # Or use mob stats later
        else: # Mob default unarmed
            attk_name = "hits"
            wpn_speed = 2.0; wpn_base_dmg = 1; wpn_rng_dmg = 1; dmg_type = "bludgeon"

    elif isinstance(attacker, Character):
        if isinstance(attack_source, Item) and attack_source.item_type == "WEAPON":
            # Character attack with weapon
            weapon = attack_source
            attk_name = f"attack with {weapon.name}"
            wpn_speed = weapon.speed
            wpn_base_dmg = weapon.damage_base
            wpn_rng_dmg = weapon.damage_rng
            dmg_type = weapon.damage_type or "bludgeon"
            # Determine skill based on damage type
            if dmg_type == "slash": relevant_weapon_skill = "bladed weapons"
            elif dmg_type == "pierce": relevant_weapon_skill = "piercing weapons"
            elif dmg_type == "bludgeon": relevant_weapon_skill = "bludgeon weapons"
            elif dmg_type == "shot": relevant_weapon_skill = "projectile weapons" # If ranged added later
            stat_modifier = attacker.might_mod # Use Might mod for melee weapons
        else:
            # Character unarmed attack
            attk_name = "punch"
            wpn_speed = 1.0 # Make unarmed slightly faster maybe?
            wpn_base_dmg = math.floor(attacker.might_mod / 2) # Base uses half mod
            wpn_base_dmg = max(0, wpn_base_dmg)
            wpn_rng_dmg = 3 # d3 random damage
            dmg_type = "bludgeon"
            relevant_weapon_skill = "martial arts"
            stat_modifier = 0 # Stat mod already incorporated into base for unarmed

    else: # Should not happen
        log.error("resolve_physical_attack: Invalid attacker type %s", type(attacker))
        return

    # Calculate weapon skill bonus
    weapon_skill_bonus = 0
    if relevant_weapon_skill and hasattr(attacker, 'get_skill_rank'):
        wep_skill_rank = attacker.get_skill_rank(relevant_weapon_skill)
        weapon_skill_bonus = math.floor(wep_skill_rank / 25)
        if weapon_skill_bonus > 0: log.debug(...) # Keep debug log

    # Final attacker rating
    attacker_rating = base_attacker_rating + weapon_skill_bonus

    # --- Target Defenses (Base + Skill Bonus) ---
    base_target_dv = target.dv
    base_target_pds = target.pds
    target_av = 0 # Base AV from gear (handled by get_total_av)
    base_block_chance = 0.0 # Base block from shield

    # Calculate DV bonuses
    dodge_bonus = 0; parry_bonus = 0
    if hasattr(target, 'get_skill_rank'):
        dodge_rank = target.get_skill_rank("dodge")
        parry_rank = target.get_skill_rank("parrying")
        dodge_bonus = math.floor(dodge_rank / 25)
        parry_bonus = math.floor(parry_rank / 25)
    target_dv = base_target_dv + dodge_bonus + parry_bonus # Final DV
    if dodge_bonus + parry_bonus > 0: log.debug(...) # Keep debug log

    # Calculate Block Chance bonus (effective_block_chance used if Step 3 implemented)
    shield_skill_bonus_pct = 0.0
    shield_item: Optional[Item] = None
    if isinstance(target, Character):
        shield_template_id = target.equipment.get("WIELD_OFF")
        if shield_template_id: shield_item = target.get_item_instance(world, shield_template_id)
        if shield_item and shield_item.item_type.upper() != "SHIELD": shield_item = None

    if shield_item and hasattr(target, 'get_skill_rank'):
        base_block_chance = shield_item._stats_dict.get("block_chance", 0.0)
        shield_skill_rank = target.get_skill_rank("shield usage")
        shield_skill_bonus_pct = math.floor(shield_skill_rank / 25) * 0.01
    effective_block_chance = base_block_chance + shield_skill_bonus_pct
    if shield_skill_bonus_pct > 0: log.debug(...) # Keep debug log


    # 3. Block Check (Deferred V1 - use effective_block_chance here)

    # 4. Hit Check (uses attacker_rating and target_dv calculated above)
    hit_roll = random.randint(1, 20)
    attack_score = attacker_rating + hit_roll
    is_hit = False; is_crit = (hit_roll == 20); is_fumble = (hit_roll == 1)
    if is_fumble: is_hit = False
    elif is_crit: is_hit = True
    elif attack_score >= target_dv: is_hit = True
    else: is_hit = False
    # Add hit/miss debug logs here if desired

    # 5. Resolve Miss / Fumble (uses local wpn_speed, attk_name)
    if not is_hit:
        # --- Apply Roundtime with Armor Penalty ---
        base_rt = wpn_speed
        rt_penalty = 0.0
        if isinstance(attacker, Character):
            total_av = attacker.get_total_av(world) # Requires get_total_av takes world
            rt_penalty = math.floor(total_av / 20) * 1.0
        final_rt = base_rt + rt_penalty
        attacker.roundtime = final_rt
        log.debug("Applied %.1fs RT to %s for miss/fumble (Base: %.1f, AV Pen: %.1f)", final_rt, attacker.name, base_rt, rt_penalty)
        # Send feedback messages (using local attk_name)
        # ... (miss/fumble messages) ...
        if rt_penalty > 0 and isinstance(attacker, Character): await attacker.send(f"Your armor slightly hinders you (+{rt_penalty:.1f}s).") # Added penalty message
        return # End combat round

    # 6. Calculate Damage (uses local wpn_base_dmg, wpn_rng_dmg, stat_modifier)
    total_random_damage = 0
    if wpn_rng_dmg > 0:
        if is_crit: total_random_damage = roll_exploding_dice(wpn_rng_dmg)
        else: total_random_damage = random.randint(1, wpn_rng_dmg)

    pre_mitigation_damage = max(0, wpn_base_dmg + total_random_damage + stat_modifier)

    # 7. Mitigation (uses local target_pds, requires Effective AV calc added)
    defense_score = base_target_pds # Base PDS
    mitigated_damage1 = max(0, pre_mitigation_damage - defense_score)
    final_damage = mitigated_damage1 # Start with damage after PDS soak

    physical_damage_types = ["physical", "slash", "pierce", "bludgeon", "projectile"]

    # Apply Armor Value (AV) - incorporating Armor Training skill effect
    if dmg_type and dmg_type.lower() in physical_damage_types: # physical_damage_types defined earlier
        base_av = 0; effective_av = 0; armor_training_rank = 0
        if hasattr(target, 'get_total_av') and hasattr(target, 'get_skill_rank'):
            try:
                base_av = target.get_total_av(world)
                if base_av > 0:
                    armor_training_rank = target.get_skill_rank("armor training")
                    av_multiplier = min(1.0, 0.20 + (armor_training_rank * 0.01))
                    effective_av = math.floor(base_av * av_multiplier)
                    log.debug("Applying AV: Dmg %d reduced by Eff.AV %d (BaseAV: %d, AT Rank: %d, Mult: %.2f)",
                            mitigated_damage1, effective_av, base_av, armor_training_rank, av_multiplier)
                # else: log.debug("Applying AV: Target has 0 Base AV.")
            except Exception as e: log.exception(...) ; effective_av = 0
        else: log.warning(...) ; effective_av = 0

        final_damage = max(0, mitigated_damage1 - effective_av) # Subtract Effective AV

    bv_mitigation = math.floor(target.barrier_value / 2)
    if bv_mitigation > 0:
        log.debug("Applying BV (Physical): Damage %d reduced by BV %d (Half Effect)", final_damage, bv_mitigation)
        final_damage = max(0, final_damage - bv_mitigation)

    # 8. Apply Damage (uses final_damage)
    target.hp -= final_damage
    target.hp = max(0, target.hp)

    if isinstance(target, Character) and target.status == "MEDITATING":
        log.info("Character %s meditation broken by damage.", target.name)
        target.status = "ALIVE"
        await target.send("{RThe blow shatters your concentration! You stop meditating.{x")

    if isinstance(target, Character) and final_damage > 0 and target.casting_info:
        spell_key = target.casting_info.get("key")
        spell_data = ability_defs.get_ability_data(spell_key)

        #Important: only interrupt SPELLS not instant abilities
        if spell_data and spell_data.get("type", "").upper() == "SPELL":
            log.debug("Character %s was casting spell '%s' while taking %d damage. Checking concentration...",
                    target.name, spell_key, final_damage)
            
            # Perform skill check. Difficulty modifier = damage taken.
            # Higher damage makes concentration harder.
            check_dc_modifier = final_damage
            concentration_success = utils.skill_check(target, "concentration", difficulty_mod=check_dc_modifier)

            if not concentration_success:
                log.info("Character %s failed concentration check (Damage: %d), spell %s fizzles.",
                        target.name, final_damage, spell_key)
                target.casting_info = None
                await target.send("{RYour concentration is broken by the blow! Your spell fizzles!{x") # color later
                if target.location:
                    await target.location.broadcast(f"\r\n{target.name.capitalize()}'s concentration wavers!\r\n", exclude={target})
                else:
                    log.debug("Character %s succeeded concentration check (Damage: %d).", target.name, final_damage)


    # 9. Send Messages (uses local vars: hit_desc, target_name, attk_name, final_damage, crit_indicator)
    hit_desc = "hit"; crit_indicator = ""
    if is_crit: hit_desc = "CRITICALLY HIT"; crit_indicator = " CRITICAL!"
    attacker_pronoun_subj, _, attacker_pronoun_poss, _, _ = utils.get_pronouns(getattr(attacker, 'sex', None))
    # ... (construct dmg_msg_attacker, dmg_msg_target, dmg_msg_room using local vars) ...
    dmg_msg_attacker = f"You {hit_desc} {target_name} with your {attk_name} for {final_damage} damage!{crit_indicator}"
    attacker_possessive = attacker_pronoun_poss
    dmg_msg_target = f"{attacker_name} {hit_desc.upper()}S you with {attacker_possessive} {attk_name} for {final_damage} damage!{crit_indicator}"
    dmg_msg_target += f" ({int(target.hp)}/{target.max_hp} HP)"
    dmg_msg_room = f"{attacker_name} {hit_desc.upper()}S {target_name} with {attacker_pronoun_poss} {attk_name} for {final_damage} damage!"
    # Send messages
    if isinstance(attacker, Character): await attacker.send(dmg_msg_attacker)
    if isinstance(target, Character): await target.send(dmg_msg_target)
    if attacker.location: await attacker.location.broadcast(f"\r\n{dmg_msg_room}\r\n", exclude={attacker, target})

    # 10. Apply Roundtime to Attacker (uses local wpn_speed & applies armor penalty)
    base_rt = wpn_speed
    rt_penalty = 0.0
    if isinstance(attacker, Character):
        total_av = attacker.get_total_av(world)
        rt_penalty = math.floor(total_av / 20) * 1.0
    final_rt = base_rt + rt_penalty
    attacker.roundtime = final_rt
    log.debug(...) # Keep debug log
    if rt_penalty > 0 and isinstance(attacker, Character):
        await attacker.send(f"Your armor slightly hinders your attack (+{rt_penalty:.1f}s).")

    # 11. Check Defeat (passes world correctly now)
    if target.hp <= 0:
        await handle_defeat(attacker, target, world)

async def resolve_magical_attack(
    caster: Character, # Assume caster is always Character for now
    target: Union[Character, Mob],
    spell_data: Dict[str, Any], # Data for the specific spell
    world: World  
):
    """REsolves spell damage against a target."""
    log.debug("Resolving magical attack: %s -> %s", caster.name, target.name)
    effect_details = spell_data.get("effect_details", {})
    caster_name = caster.name.capitalize()
    target_name = target.name.capitalize()
    target_loc = caster.location # Assume same location

    # 1. Get Caster Power & Target Defense
    caster_rating = caster.apr if effect_details.get("school") == "Arcane" else caster.dpr # Use APR or DPR
    target_dv = target.dv
    target_sds = target.sds
    target_bv = target.barrier_value # Use the property

    # 2. Hit Check (Magic vs Dodge Value)
    always_hits = effect_details.get("always_hits", False)
    hit_roll = random.randint(1, 20)
    attack_score = caster_rating + hit_roll
    is_hit = False
    is_crit = (hit_roll == 20)
    is_fumble = (hit_roll == 1) # Magic can fumble? Yes.

    if always_hits: is_hit = True; is_crit = False; is_fumble = False # Magic missile bypasses roll
    elif is_fumble: is_hit = False
    elif is_crit: is_hit = True
    elif attack_score >= target_dv: is_hit = True
    else: is_hit = False

    # 3. Resolve Miss / Fumble
    if not is_hit:
        # Send messages (Use spell display name)
        spell_display_name = spell_data.get("name", "spell")
        miss_msg_caster = f"Your {spell_display_name} misses {target_name}."
        miss_msg_target = f"{caster_name}'s {spell_display_name} misses you."
        miss_msg_room = f"{caster_name}'s {spell_display_name} misses {target_name}."
        if is_fumble: miss_msg_caster = f"You fumble casting {spell_display_name}!" # etc.

        await caster.send(miss_msg_caster)
        if isinstance(target, Character): await target.send(miss_msg_target)
        if target_loc: await target_loc.broadcast(f"\r\n{miss_msg_room}\r\n", exclude={caster, target})
        return # End resolution
    
    # 4. Calculate Damage
    base_dmg = effect_details.get("damage_base", 0)
    rng_dmg = effect_details.get("damage_rng", 0)
    total_random_damage = 0
    if rng_dmg > 0:
        if is_crit and not always_hits: # No exploding dice on auto-hits maybe?
            total_random_damage = roll_exploding_dice(rng_dmg)
        else: total_random_damage = random.randint(1, rng_dmg)

    # Add caster's power modifier? Use APR/DPR directly? Let's add mod for now.
    stat_modifier = caster.apr if effect_details.get("school") == "Arcane" else caster.dpr
    pre_mitigation_damage = max(0, base_dmg + total_random_damage + stat_modifier)

    # 5. Mitigation (SDS + BV)
    # TODO: Check damage_type for resistances/vulnerabilities later
    mitigated_damage1 = max(0, pre_mitigation_damage - target_sds) # Reduce by SDS
    final_damage = max(0, mitigated_damage1 - target_bv) # Reduce by Barrier Value

    # 6. Apply Damage
    target.hp -= final_damage
    target.hp = max(0, target.hp)

    if isinstance(target, Character) and target.status == "MEDITATING":
        log.info("Character %s meditation broken by damage.", target.name)
        target.status = "ALIVE"
        await target.send("{RThe blow shatters your concentration! You stop meditating.{x")

    # If character is currently casting see if they lose their spell due to magical damage.
    if isinstance(target, Character) and final_damage > 0 and target.casting_info:
        spell_key = target.casting_info.get("key")
        spell_data = ability_defs.get_ability_data(spell_key)

        #Important: only interrupt SPELLS not instant abilities
        if spell_data and spell_data.get("type", "").upper() == "SPELL":
            log.debug("Character %s was casting spell '%s' while taking %d damage. Checking concentration...",
                    target.name, spell_key, final_damage)
            
            # Perform skill check. Difficulty modifier = damage taken.
            # Higher damage makes concentration harder.
            check_dc_modifier = final_damage
            concentration_success = utils.skill_check(target, "concentration", difficulty_mod=check_dc_modifier)

            if not concentration_success:
                log.info("Character %s failed concentration check (Damage: %d), spell %s fizzles.",
                        target.name, final_damage, spell_key)
                target.casting_info = None
                await target.send("{RYour concentration is broken by the blow! Your spell fizzles!{x") # color later
                if target.location:
                    await target.location.broadcast(f"\r\n{target.name.capitalize()}'s concentration wavers!\r\n", exclude={target})
                else:
                    log.debug("Character %s succeeded concentration check (Damage: %d).", target.name, final_damage)

    # 7. Send Messages
    hit_desc = "hits"
    crit_indicator = ""
    if is_crit: hit_desc = "CRITICALLY HITS"; crit_indicator = " CRITICAL!"
    spell_display_name = spell_data.get("name", "spell")

    dmg_msg_caster = f"Your {spell_display_name} {hit_desc} {target_name} for {final_damage} damage!{crit_indicator}"
    dmg_msg_target = f"{caster_name}'s {spell_display_name} {hit_desc.upper()}S you for {final_damage} damage!{crit_indicator}"
    dmg_msg_target += f" ({target.hp}/{target.max_hp} HP)"
    dmg_msg_room = f"{caster_name}'s {spell_display_name} {hit_desc.upper()}S {target_name} for {final_damage} damage!"

    await caster.send(dmg_msg_caster)
    if isinstance(target, Character): await target.send(dmg_msg_target)
    if target_loc: await target_loc.broadcast(f"\r\n{dmg_msg_room}\r\n", exclude={caster, target})

    # 8. Check Defeat
    if target.hp <= 0:
        await handle_defeat(caster, target, world)

async def resolve_ability_effect(
    caster: Character, # Caster is always a character for now
    target_ref: Optional[Union[int, str]], # Stored ID (int for mob/char) or "self"
    target_type_str: Optional[str], # Stored type "MOB", "CHAR", "SELF", "NONE"
    ability_data: Dict[str, Any], # Data for the spell/ability used
    world: World 
):
    """Finds the target and calls the specific effect resolution function."""

    effect_type = ability_data.get("effect_type")
    effect_details = ability_data.get("effect_details", {})
    ability_key = ability_data.get("name", "?").lower() # Use internal key if name missing

    # 1. Find Target Object based on saved reference
    target: Optional[Union[Character, Mob]] = None
    if target_type_str == "SELF":
        target = caster
    elif target_type_str == "NONE":
        target = None # no target needed
    elif target_type_str == "CHAR" and isinstance(target_ref, int):
        target = world.get_active_character(target_ref) # Find character by DB ID
    elif target_type_str == "MOB" and isinstance(target_ref, int): 
        # Find mob by instance ID - need to search rooms? Or store location?
        # Search caster's current room for simplicity
        if caster.location:
            for mob in caster.location.mobs:
                if mob.instance_id == target_ref:
                    target = mob; break
    elif target_type_str == "CHAR_OR_MOB" and isinstance(target_ref, int):
        # Try finding character first, then mob
        target = world.get_active_character(target_ref)
        if not target and caster.location:
            for mob in caster.location.mobs:
                if mob.instance_id == target_ref: target = mob; break
    
    # Check if required target exists and is still valid (alive, same room for non-self)
    target_type = ability_data.get("target_type") # Get Required type again
    is_valid_target = False
    if target_type == ability_defs.TARGET_SELF:
        is_valid_target = caster.is_alive() # Can buff/heal self even if dying? Maybe not. Check ALIVE.
    elif target_type == ability_defs.TARGET_NONE:
        is_valid_target = True # No target needed
    elif target is not None and target.is_alive() and target.location == caster.location:
        # Check type match if needed (e.g., spell specifies MOB only)
        if target_type == ability_defs.TARGET_CHAR and isinstance(target, Character): is_valid_target = True
        elif target_type == ability_defs.TARGET_MOB and isinstance(target, Mob): is_valid_target = True
        elif target_type == ability_defs.TARGET_CHAR_OR_MOB: is_valid_target = True
    
    if not is_valid_target and target_type not in [ability_defs.TARGET_NONE, ability_defs.TARGET_AREA]:
        log.debug("Target %s (%s) no longer valid for %s effect.", target_ref, target_type_str, ability_key)
        await caster.send("Your target is no longer valid.")
        return # Spell fizzles, no post cast RT applied by resolver
    
    # 2. Switch based on Effect Type
    log.debug("Resolving effect '%s' for %s. Caster: %s, Target: %s",
            effect_type, ability_key, caster.name, getattr(target, 'name', 'None'))
    
    if effect_type == ability_defs.EFFECT_DAMAGE:
        school = effect_details.get("school", "Physical").upper()
        if school in ["ARCANE", "DIVINE", "FIRE", "COLD", "LIGHTNING", "POISON", "EARTH"]: # Magical Schools
            await resolve_magical_attack(caster, target, ability_data, world)
        else: # Assume physical damage ability
            #call phyiscal attack but pass ability details, no weapon
            await resolve_physical_attack(caster, target, effect_details, world)

    elif effect_type == ability_defs.EFFECT_HEAL:
        await apply_heal(caster, target, effect_details, world)

    elif effect_type == ability_defs.EFFECT_BUFF or effect_type == ability_defs.EFFECT_DEBUFF:
        await apply_effect(caster, target, effect_details, ability_data, world)

    elif effect_type == ability_defs.EFFECT_MODIFIED_ATTACK:
        # Get weapon, pass mods to physical attack
        weapon = None
        if isinstance(caster, Character): # Only characters use abilities needing weapons for now
            weapon_template_id = caster.equipment.get("WIELD_MAIN")
            if weapon_template_id: weapon = caster.get_item_instance(world, weapon_template_id)
            if weapon and weapon.item_type != "WEAPON": weapon = None
        await resolve_physical_attack(caster, target, weapon, world, ability_mods=effect_details)

    elif effect_type == ability_defs.EFFECT_STUN_ATTEMPT:
        # Shield Bash example
        if effect_details.get("requires_shield", False) and isinstance(caster, Character):
            shield_id = caster.equipment.get("WIELD_OFF")
            if not shield_id: await caster.send("You need a shield equipped!"); return
            shield_item = caster.get_item_instance(world, shield_id)
            if not shield_item or shield_item.item_type.upper() != "SHIELD":
                await caster.send("You need a shield equipped!"); return

        # Perform modified attack roll to see if bash connects
        hit_check_success = perform_hit_check(caster, target, effect_details.get("mar_modifier_mult", 1.0))

        if hit_check_success:
            await caster.send(f"You bash {target.name}!") # Hit message
            await target.send(f"{caster.name.capitalize()} bashes you!") # Hit message target
            await caster.location.broadcast(f"\r\n{caster.name.capitalize()} bashes {target.name}!\r\n", exclude={caster, target})

            # Roll for stun chance
            stun_chance = effect_details.get("stun_chance", 0.0)
            if random.random() < stun_chance:
                # Apply stun effect (which adds roundtime)
                stun_effect_details = {
                    "name": effect_details.get("name", "Stunned"),
                    "stat_affected": ability_defs.STAT_ROUNDTIME,
                    "amount": effect_details.get("stun_duration", 3.0), # Amount is RT to add
                    "duration"
                    : effect_details.get("stun_duration", 3.0) + 0.1 # Duration slightly longer
                }
                await apply_effect(caster, target, stun_effect_details, ability_data, world)
                if isinstance(target, Character): await target.send("{RYou are stunned!{x")
                await caster.location.broadcast(f"\r\n{target.name} is stunned by the bash!\r\n", exclude={caster, target})
            # Else: Hit but didn't stun
        else: # Missed the bash attempt
            await caster.send(f"You try to bash {target.name}, but miss.")
            if isinstance(target, Character): await target.send(f"{caster.name.capitalize()} tries to bash you, but misses.")
            await caster.location.broadcast(f"\r\n{caster.name.capitalize()} misses a bash on {target.name}!\r\n", exclude={caster, target})

# --- Placeholder Helper for Hit Check ---
def perform_hit_check(attacker: Union[Character, Mob], target: Union[Character, Mob], mar_mult: float = 1.0) -> bool:
    """ Basic hit check logic (d20 + MAR*mult vs DV). """
    # TODO: Refactor hit logic out of resolve_physical_attack into here?
    base_mar = attacker.mar
    mod_mar = math.floor(base_mar * mar_mult)
    target_dv = target.dv # TODO: Add dodge/parry skill bonuses here too eventually
    hit_roll = random.randint(1, 20)
    if hit_roll == 1: return False # Fumble
    if hit_roll == 20: return True # Crit
    return (mod_mar + hit_roll) >= target_dv

async def apply_heal(
    caster: Character,
    target: Union[Character, Mob], # Can mobs be healed? Yes.
    effect_details: Dict[str, Any],
    world: World
):
    """Applies healing to a target."""
    if not target.is_alive(): # Can't heal the dead (for now)
        if caster == target: await caster.send("You cannot heal yourself in your current state.")
        else: await caster.send(f"{target.name.capitalize()} cannot be healed now.")
        return

    base_heal = effect_details.get("heal_base", 0)
    rng_heal = effect_details.get("heal_rng", 0)
    random_heal = random.randint(1, rng_heal) if rng_heal > 0 else 0
    heal_amount = base_heal + random_heal

    if heal_amount <= 0: return # No actual healing

    actual_healed = min(heal_amount, target.max_hp - target.hp) # Can't heal above max HP
    target.hp += actual_healed

    # Send messages
    heal_msg_caster = f"You heal {target.name} for {actual_healed} hit points."
    heal_msg_target = f"{caster.name.capitalize()} heals you for {actual_healed} hit points."
    heal_msg_room = f"{caster.name.capitalize()} heals {target.name}."

    if caster == target: heal_msg_caster = f"You heal yourself for {actual_healed} hit points."

    await caster.send(heal_msg_caster)
    if target != caster and isinstance(target, Character): await target.send(heal_msg_target)
    if target.location: await target.location.broadcast(f"\r\n{heal_msg_room}\r\n", exclude={caster, target})

async def apply_effect(
    caster: Character, # Or Mob later?
    target: Union[Character, Mob],
    effect_details: Dict[str, Any],
    ability_data: Dict[str, Any],
    world: World
):
    """Applies a temporary BUFF or DEBUFF effect to the target."""
    effect_name = effect_details.get("name", "UnknownEffect")
    duration = effect_details.get("duration", 0.0)
    stat = effect_details.get("stat_affected")
    amount = effect_details.get("amount")

    if not duration > 0 or not stat or amount is None:
        log.error("Invalid effect data for '%s': %s", effect_name, effect_details)
        await caster.send("The effect seems to dissipate harmlessly.")
        return

    # Store effect on target (overwrites existing effect with same name)
    # Ensure target has 'effects' attribute
    if not hasattr(target, 'effects'):
        log.error("Target %s has no 'effects' attribute to apply %s", target.name, effect_name)
        return
    
    caster_name_cap = caster.name.capitalize()
    target_name_cap = target.name.capitalize()

    # Get Message tempplates, provide defaults
    msg_self = ability_data.get('apply_msg_self', "You feel an effect.")
    msg_target = ability_data.get('apply_msg_target', f"{caster_name_cap} applies an effect to you.")
    msg_room = ability_data.get('apply_msg_room', f"{caster_name_cap} applies an effect to {target_name_cap}.")

    #Format messages with actual names
    try:
        msg_self = msg_self.format(caster_name=caster_name_cap, target_name=target_name_cap) if msg_self else None
        msg_target = msg_target.format(caster_name=caster_name_cap, target_name=target_name_cap) if msg_target else None
        msg_room = msg_room.format(caster_name=caster_name_cap, target_name=target_name_cap) if msg_room else None
    except KeyError as e:
        log.warning("apply_effect: Formatting error in message for '%s': Missing key %s", ability_data.get("name", "?"), e)
        # Fallback to generic message if formatting fails
        msg_self = msg_target = msg_room = None

    # Send the message conditionally
    if msg_self and target == caster:
        await caster.send(msg_self)
    elif msg_target and target != caster and isinstance(target, Character):
        await target.send(msg_target)
        # Send different message to caster if they targeted someone else?
        caster_target_msg = ability_data.get('apply_msg_caster_other', f"You apply {effect_name} to {target_name_cap}.")
        try:
            caster_target_msg = caster_target_msg.format(caster_name=caster_name_cap, target_name=target_name_cap)
            await caster.send(caster_target_msg)
        except KeyError as e:
            log.warning("apply_effect: Formatting error in caster_other message for '%s': Missing key %s", ability_data.get("name", "?"), e)

    if msg_room and target.location:
        await target.location.broadcast(f"\r\n{msg_room}\r\n", exclude={caster, target}) # Exclude caster and target still makes sense


    target.effects[effect_name] = {
        "ends_at": time.monotonic() + duration,
        "amount": amount,
        "stat": stat,
        "caster_id": caster.dbid if isinstance(caster, Character) else None # Track caster if needed
    }
    log.info("Applied effect '%s' to %s for %.1f seconds.", effect_name, target.name, duration)
    buff_msg_caster = f"You apply {effect_name} to {target.name}."
    buff_msg_target = f"You feel the effect of {effect_name}."
    buff_msg_room = f"{caster.name.capitalize()} applies an effect to {target.name}."
    if caster == target: buff_msg_caster = f"You apply {effect_name} to yourself."; buff_msg_room=f"{caster.name.capitalize()} applies an effect to themself."

    await caster.send(buff_msg_caster)
    if target != caster and isinstance(target, Character): await target.send(buff_msg_target)
    if target.location: await target.location.broadcast(f"\r\n{buff_msg_room}\r\n", exclude={caster, target})

async def resolve_consumable_effect(
        character: Character,
        item_template: Dict[str, Any],
        world: World
) -> bool:
    """Applies the effect of a consumable item (FOOD/DRINK)"""
    try:
        stats = json.loads(item_template.get('stats', '{}') or '{}')
    except (json.JSONDecodeError, TypeError):
        stats = {}

    effect_name = stats.get("effect")
    amount = stats.get("amount") # Amount might be int or float depending on effect
    item_display_name = item_template.get('name', 'the item')

    log.debug("Resolving consumable effect: Char=%s, Item=%s, Effect=%s, Amount=%s",
            character.name, item_display_name, effect_name, amount)

    if not effect_name:
        await character.send(f"The {item_display_name} doesn't seem to do anything.")
        return False # No effect defined, but item still consumed if caller removes it

    # Handle effects
    if effect_name == "heal_hp":
        if amount is None or not isinstance(amount, (int, float)):
            log.error("Invalid amount for heal_hp effect on item %d", item_template.get('id','?'))
            await character.send("The effect seems faulty.")
            return False
        heal_amount = float(amount)
        if character.hp >= character.max_hp:
            await character.send("You are already at full health.")
            return False # Don't consume if already full? Or allow? Let's not consume.
        actual_healed = min(heal_amount, character.max_hp - character.hp)
        character.hp += actual_healed
        await character.send(f"You consume {item_display_name}, healing {int(actual_healed)} hit points.")
        # TODO: Broadcast "X drinks a potion" / "X eats some bread"?
        return True
    elif effect_name == "heal_essence":
        if amount is None or not isinstance(amount, (int, float)): # ... (validation) ...
            return False
        heal_amount = float(amount)
        if character.essence >= character.max_essence: # ... (check if full) ...
            return False
        actual_healed = min(heal_amount, character.max_essence - character.essence)
        character.essence += actual_healed
        await character.send(f"You consume {item_display_name}, restoring {int(actual_healed)} essence.")
        return True
    elif effect_name == "quench_thirst":
        # TODO: Implement thirst mechanic later
        await character.send(f"You drink from {item_display_name}. It is refreshing.")
        return True
    # Add elif for other effects (buffs, cures, etc.)

    else:
        log.warning("Unhandled consumable effect '%s' for item %d", effect_name, item_template.get('id','?'))
        await character.send(f"You consume {item_display_name}, but nothing seems to happen.")
        return False # Unknown effect, but maybe still consume? Let's say no for now.