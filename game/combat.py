# game/combat.py
"""
Handles combat calculations and resolution.
"""
import random
import logging
import math
import time
from typing import TYPE_CHECKING, Optional, Union, Dict, Any, Tuple, List # Added Union

# --- Runtime Imports ---
# Import classes needed for isinstance() checks and logic
from .character import Character
from .mob import Mob
from .item import Item
from .world import World
from . import utils


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

        if dropped_coinage > 0:
            # For V1, just notify room. Add actual coin items later?
            log.info("%s dropped %d coinage.", target.name.capitalize(), dropped_coinage)
            # Add to room? Need coin item or just log for now.
            # target.location.items.append(COIN_ITEM_ID?) # Needs design
            # For simplicity now, maybe award directly to attacker?
            if isinstance(attacker, Character):
                log.debug("Awarding %d coinage directly to %s.", dropped_coinage, attacker.name)
                # TODO: Check purse limit later
                attacker.coinage += dropped_coinage
                await attacker.send(f"You loot {dropped_coinage} talons from the corpse.")

        if dropped_item_ids:
            item_names = []
            for item_id in dropped_item_ids:
                # Add item template ID to the room's item list
                target.location.items.append(item_id)
                # Try to get name for message
                template = world.get_item_template(item_id) # Mob needs world ref? Pass it in. Or Room needs world ref. Pass world to handle_defeat.
                item_names.append(template['name'] if template else f"Item #{item_id}")
            log.info("%s dropped items: %s", target.name.capitalize(), item_names)
            # Announce item drops to room (excluding attacker for now?)
            await target.location.broadcast(f"\r\n{target.name.capitalize()}'s corpse drops: {', '.join(item_names)}.\r\n", exclude={attacker})

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
            target.is_fighting = False
            target.target = None
            # Calculate death timer based on Vitality score
            vit_score = target.stats.get('vitality', 10)
            timer_duration = float(vit_score) * 2 # Example: 1 second per vit point
            target.death_timer_ends_at = time.monotonic() + timer_duration

            log.info("Character %s is now DYING (Timer: %.1f s).", target.name, timer_duration)

            # Drop Coinage (calculate 10%)
            coinage_to_drop = int(target.coinage * 0.10)
            if coinage_to_drop > 0:
                target.coinage -= coinage_to_drop
                # TODO: Create coin item/pile on ground? Log for now.
                log.info("%s drops %d coinage upon dying!", target.name, coinage_to_drop)
                await target.location.broadcast(f"\r\n{target.name} drops some coins as they fall!\r\n", exclude={target})

            # Send messages
            await target.send("\r\n*** You are DYING! ***\r\n")
            await target.location.broadcast(f"\r\n{target.name} collapses to the ground, dying!\r\n", exclude={target})

            # Decrement spiritual tether later (Phase 4)
            # log.info("%s loses spiritual tether.", target.name)

        else:
            log.debug("handle_defeat called on already non-ALIVE character %s.", target.name)

    else:
        log.error("handle_defeat called with invalid target type: %r", target)

def determine_loot(loot_table: Dict[str, Any]) -> Tuple[int, List[int]]:
    """Calculates loot based on mob's loot table."""
    dropped_coinage = 0
    dropped_item_ids = []

    # Coinage
    max_coinage = loot_table.get("coinage_max", 0)
    if max_coinage > 0:
        dropped_coinage = random.randint(0, max_coinage) # Drop 0 to max

    # Items
    item_list = loot_table.get("items", [])
    if item_list:
        for item_info in item_list:
            template_id = item_info.get("template_id")
            chance = item_info.get("chance", 0.0)
            if template_id and isinstance(chance, (float, int)) and random.random() < chance:
                dropped_item_ids.append(template_id)

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
    world: World
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

    # 8. Apply Damage (uses final_damage)
    target.hp -= final_damage
    target.hp = max(0, target.hp)

    # 9. Send Messages (uses local vars: hit_desc, target_name, attk_name, final_damage, crit_indicator)
    hit_desc = "hit"; crit_indicator = ""
    if is_crit: hit_desc = "CRITICALLY HIT"; crit_indicator = " CRITICAL!"
    attacker_pronoun_subj, _, attacker_pronoun_poss, _, _ = utils.get_pronouns(getattr(attacker, 'sex', None))
    # ... (construct dmg_msg_attacker, dmg_msg_target, dmg_msg_room using local vars) ...
    dmg_msg_attacker = f"You {hit_desc} {target_name} with your {attk_name} for {final_damage} damage!{crit_indicator}"
    attacker_possessive = attacker_pronoun_poss
    dmg_msg_target = f"{attacker_name} {hit_desc.upper()}S you with {attacker_possessive} {attk_name} for {final_damage} damage!{crit_indicator}"
    dmg_msg_target += f" ({target.hp}/{target.max_hp} HP)"
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