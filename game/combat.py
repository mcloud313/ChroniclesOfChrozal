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

physical_damage_types = [
    ability_defs.DAMAGE_PHYSICAL,
    ability_defs.DAMAGE_SLASH,
    ability_defs.DAMAGE_PIERCE,
    ability_defs.DAMAGE_BLUDGEON,
]

MAGICAL_DAMAGE_TYPES = {
    ability_defs.DAMAGE_FIRE,
    ability_defs.DAMAGE_COLD,
    ability_defs.DAMAGE_LIGHTNING,
    ability_defs.DAMAGE_EARTH,
    ability_defs.DAMAGE_ARCANE,
    ability_defs.DAMAGE_DIVINE,
    ability_defs.DAMAGE_POISON,
    ability_defs.DAMAGE_SONIC,
}

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
    if isinstance(attacker, Character): await attacker.send(f"You have slain {target_name}!")
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
            coin_msg = f"\r\n{dropped_coinage} talons fall from {target_name}!\r\n"
            await target_loc.broadcast(coin_msg, exclude={attacker})
            if isinstance(attacker, Character):
                    await attacker.send(f"You find {utils.format_coinage(dropped_coinage)} on the corpse.")
        else: 
                log.error("Failed to add dropped coinage %d to room %d", dropped_coinage, target_loc.dbid)

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
            log.info("%s has been defeated by %s!", target_name, attacker_name) # Log defeat first
            target.hp = 0 # Ensure HP is 0
            target.status = "DYING"
            target.stance = "Lying"
            target.is_fighting = False
            target.target = None
            target.casting_info = None # Interrupt  casting

            xp_lost_pool = target.xp_pool
            target.xp_pool = 0.0

            # Calculate 10% of XP earned *within the current level*
            xp_at_start_of_level = utils.xp_needed_for_level(target.level - 1) if target.level > 1 else 0
            xp_progress_in_level = target.xp_total - xp_at_start_of_level
            xp_penalty_from_total = 0.0
            if xp_progress_in_level > 0: # Only apply penalty if progress was made
                xp_penalty_from_total = math.floor(xp_progress_in_level * 0.10) # 10% penalty

            # Apply penalty, ensuring not dropping below start of level
            target.xp_total = max(xp_at_start_of_level, target.xp_total - xp_penalty_from_total)

            log.info("Character %s lost %.1f pool XP and %.1f level XP due to dying. New total: %.1f",
                    target.name, xp_lost_pool, xp_penalty_from_total, target.xp_total)
            
            xp_loss_msg = "{rYou feel some of your experience drain away...{x"
            if xp_lost_pool > 0: xp_loss_msg += " {rYour focus shatters, losing unabsorbed experience.{x"
            await target.send(xp_loss_msg)


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
        await attacker.send(f"You gain {int(actual_xp_added)} experience points into your pool.")
    else:
        await attacker.send("Your mind cannot hold any more raw experience right now.")
        return
    # TODO: Distribute XP among party members later

# --- Main Combat Resolution ---

async def resolve_physical_attack(
    attacker: Union[Character, Mob],
    target: Union[Character, Mob],
    attack_source: Optional[Union[Item, Dict[str, Any]]], # Weapon Item or Mob Attack Dict
    world: World,
    ability_mods: Optional[Dict[str, Any]] = None # Optional dict with ability mods
):
    """
    Resolves a single physical attack round, calculates detailed results,
    and sends verbose messages to participants.
    """

    # 1. Checks
    if not attacker.is_alive() or not target.is_alive(): return
    if not hasattr(attacker, 'location') or not hasattr(target, 'location') or attacker.location != target.location:
        log.debug("Resolve Attack: Attacker or Target missing location or not in same room.")
        return

    # 2. Get Attack/Defense Info & Determine Attack Variables
    attacker_name = attacker.name.capitalize()
    target_name = target.name.capitalize()
    attacker_loc = attacker.location # Cache location

    attacker_pronoun_subj, _, attacker_pronoun_poss, _, _ = utils.get_pronouns(getattr(attacker, 'sex', None))

    # --- Attacker Base Stats & Ability Setup ---
    base_attacker_rating = attacker.mar # Base MAR
    weapon_skill_bonus = 0
    relevant_weapon_skill: Optional[str] = None
    weapon: Optional[Item] = None
    attk_name: str = "attack"
    wpn_speed: float = 2.0
    wpn_base_dmg: int = 1
    wpn_rng_dmg: int = 0
    dmg_type: str = ability_defs.DAMAGE_PHYSICAL # Use constant
    base_stat_modifier: int = attacker.might_mod # Default modifier
    bonus_rt_from_ability: float = 0.0 # Bonus RT from ability mods

    # --- Apply Ability Modifiers (if any) ---
    if ability_mods:
        log.debug("Applying ability modifiers: %s", ability_mods)
        mar_mult = ability_mods.get('mar_modifier_mult', 1.0)
        base_attacker_rating = math.floor(base_attacker_rating * mar_mult) # Apply MAR mod BEFORE skill bonus
        rng_mult = ability_mods.get('rng_damage_mult', 1.0)
        # We modify wpn_rng_dmg later when it's determined
        wpn_base_dmg += ability_mods.get('bonus_damage', 0) # Add flat bonus damage
        bonus_rt_from_ability = ability_mods.get('bonus_rt', 0.0) # Store bonus RT

    # Determine specifics based on attacker type and attack_source
    if isinstance(attacker, Mob):
        mob_attack_data = attack_source
        if isinstance(mob_attack_data, dict):
            attk_name = mob_attack_data.get("name", "strike")
            wpn_speed = mob_attack_data.get("speed", 2.0)
            wpn_base_dmg = mob_attack_data.get("damage_base", 1) # Base Dmg set
            wpn_rng_dmg = mob_attack_data.get("damage_rng", 0) # Base RNG set
            dmg_type = mob_attack_data.get("damage_type", ability_defs.DAMAGE_PHYSICAL)
            base_stat_modifier = attacker.might_mod # Mobs use might mod for now
        else: # Mob default unarmed
            attk_name = "hits"; wpn_speed = 2.0; wpn_base_dmg = 1; wpn_rng_dmg = 1; dmg_type = ability_defs.DAMAGE_BLUDGEON; base_stat_modifier = attacker.might_mod
    elif isinstance(attacker, Character):
        if isinstance(attack_source, Item) and attack_source.item_type == "WEAPON":
            weapon = attack_source; attk_name = f"attack with {weapon.name}"; wpn_speed = weapon.speed
            wpn_base_dmg = weapon.damage_base; wpn_rng_dmg = weapon.damage_rng; dmg_type = weapon.damage_type or ability_defs.DAMAGE_BLUDGEON
            if dmg_type == ability_defs.DAMAGE_SLASH: relevant_weapon_skill = "bladed weapons"
            elif dmg_type == ability_defs.DAMAGE_PIERCE: relevant_weapon_skill = "piercing weapons"
            elif dmg_type == ability_defs.DAMAGE_BLUDGEON: relevant_weapon_skill = "bludgeon weapons"
            elif dmg_type == "shot": relevant_weapon_skill = "projectile weapons" # TODO: Ranged Attack Rating?
            base_stat_modifier = attacker.might_mod # Melee uses might
        else: # Unarmed
            attk_name = "punch"; wpn_speed = 1.0; wpn_base_dmg = max(0, math.floor(attacker.might_mod / 2)); wpn_rng_dmg = 3; dmg_type = ability_defs.DAMAGE_BLUDGEON
            relevant_weapon_skill = "martial arts"; base_stat_modifier = 0 # Mod already in base_dmg
    else: log.error(...); return

    # Apply RNG multiplier from ability mods (if any) AFTER getting base RNG
    if ability_mods:
        rng_mult = ability_mods.get('rng_damage_mult', 1.0)
        wpn_rng_dmg = math.floor(wpn_rng_dmg * rng_mult)

    # Calculate weapon skill bonus
    if relevant_weapon_skill and hasattr(attacker, 'get_skill_rank'):
        wep_skill_rank = attacker.get_skill_rank(relevant_weapon_skill)
        weapon_skill_bonus = math.floor(wep_skill_rank / 10)

    # Final attacker rating includes base (potentially modified) + skill bonus
    final_attacker_rating = base_attacker_rating + weapon_skill_bonus

    # --- Target Defenses ---
    base_target_dv = target.dv
    base_target_pds = target.pds
    target_av = 0 # Calculated later if needed
    target_bv = target.barrier_value # Get current barrier value


    # Calculate DV bonuses/penalties
    dodge_bonus = 0; parry_bonus = 0
    if hasattr(target, 'get_skill_rank'):
        dodge_bonus = math.floor(target.get_skill_rank("dodge") / 10)
        parry_bonus = math.floor(target.get_skill_rank("parrying") / 10)
    final_target_dv = base_target_dv + dodge_bonus + parry_bonus



    # Apply stance penalty
    if hasattr(target, 'stance'):
        if target.stance == "Lying": final_target_dv = math.floor(final_target_dv * 0.5)
        elif target.stance == "Sitting": final_target_dv = math.floor(final_target_dv * 0.75)

    base_block_chance: float = 0.0
    shield_skill_bonus_pct: float = 0.0
    shield_item: Optional[Item] = None

    if isinstance(target, Character):
        # Get shield must be called on Character obj, needs world
        shield_item = target.get_shield(world) # Ensure get_shield exists
        if shield_item: #Only calculate if shield exists
            # Get base block chance from shield stats JSON

            base_block_chance = shield_item.block_chance

            # Get Shield skill Bonus
            if hasattr(target, 'get_skill_rank'): # check if target has skills
                shield_skill_rank = target.get_skill_rank("shield usage")
                shield_skill_bonus_pct = math.floor(shield_skill_rank / 10) * 0.01
                if shield_skill_bonus_pct > 0: log.debug("Target %s shield skill bonus: +%.0f%%", target_name, shield_skill_bonus_pct * 100)
    

    effective_block_chance: float = base_block_chance + shield_skill_bonus_pct

    # --- 3. Block Check (Deferred V1) ---
    # effective_block_chance calculated previously based on shield/skill, use here if implementing
    effective_block_chance = max(0.0, min(0.75, effective_block_chance))


    # --- 4. Hit Check ---
    hit_roll = random.randint(1, 20)
    attack_score = final_attacker_rating + hit_roll
    is_hit = False; is_crit = (hit_roll == 20); is_fumble = (hit_roll == 1)
    if is_fumble: is_hit = False
    elif is_crit: is_hit = True
    elif attack_score >= final_target_dv: is_hit = True
    else: is_hit = False

    # --- Build Verbose Hit String ---
    vb_hit_check = f"{{c(Roll:{hit_roll} + MAR:{final_attacker_rating} = {attack_score} vs DV:{final_target_dv}){{x"

    # --- 5. Resolve Miss / Fumble ---
    if not is_hit:
        # Apply Roundtime (includes ability bonus + armor penalty)
        base_rt = wpn_speed + bonus_rt_from_ability
        rt_penalty = 0.0; total_av = 0
        if isinstance(attacker, Character): total_av = attacker.get_total_av(world); rt_penalty = math.floor(total_av / 20) * 1.0
        final_rt = base_rt + rt_penalty
        attacker.roundtime = final_rt

        # Standard Messages
        miss_msg_room = f"{attacker_name} tries to {attk_name} {target_name}, but misses."
        miss_msg_target = f"{attacker_name} tries to {attk_name} you, but {{Kmisses{{x."
        miss_msg_attacker = f"You try to {attk_name} {target_name}, but {{Kmiss.{{x"
        if is_fumble:
            attacker.roundtime = wpn_speed + bonus_rt_from_ability + rt_penalty + 2.0 # Base Miss RT + Fumble Penalty RT
            fumble_effect = random.randint(1, 4) # Choose effect
            fumble_msg_room = f"{attacker_name} {{Rfumbles{{x their attack!"
            fumble_msg_target = f"{attacker_name} {{Rfumbles{{x attacking you!"
            fumble_msg_attacker = f"{{RYou fumble your {attk_name}!{{x"

            if fumble_effect == 1 and isinstance(attacker, Character) and attacker.stance == "Standing":
                attacker.stance = "Lying"
                fumble_msg_attacker += " You stumble and fall prone!"
                fumble_msg_room += f" {attacker_pronoun_subj} falls prone!"
            elif fumble_effect == 2:
                attacker.roundtime += 6.0 # Extra off-balance RT (total 8s + base?) - adjust number as needed
                fumble_msg_attacker += " You lose your balance badly (+6s RT)!"
                fumble_msg_room += f" {attacker_pronoun_subj} stumbles badly!"
            elif fumble_effect == 3 and weapon: # Self-damage only with weapon
                self_dmg = max(1, math.floor(wpn_base_dmg / 2) + wpn_rng_dmg // 4) # Example: 1/2 base + 1/4 rng
                if attacker.hp > self_dmg: # Avoid instant suicide loops
                    attacker.hp -= self_dmg
                    fumble_msg_attacker += f" You strike yourself! ({int(self_dmg)} dmg)" # Show int damage
                    fumble_msg_room += f" {attacker_pronoun_subj} manages to hit themself!"
                else: # Not enough HP to take full fumble damage
                    fumble_msg_attacker += " You nearly strike yourself!"
                    fumble_msg_room += f" {attacker_pronoun_subj} nearly hits themself!"
            elif fumble_effect == 4 and weapon: # Drop weapon only if wielding one
                # Get weapon details BEFORE removing from equipment
                weapon_id = attacker.equipment.get("WIELD_MAIN")
                weapon_name = weapon.name # Use the weapon object we already have
                if weapon_id:
                    del attacker.equipment["WIELD_MAIN"]
                    # Add item to room
                    if attacker.location:
                        added = await attacker.location.add_item(weapon_id, world)
                        if added:
                            fumble_msg_attacker += f" You drop your {weapon_name}!"
                            fumble_msg_room += f" {attacker_pronoun_subj} drops their {weapon_name}!"
                        else: # Failed to add to room? Fallback message
                            fumble_msg_attacker += " You nearly drop your weapon!"
                            log.error("Failed to add dropped fumble weapon %d to room %d", weapon_id, attacker.location.dbid)
                    else: fumble_msg_attacker += " You nearly drop your weapon!" # No location?
                else: # No weapon in slot somehow? Default fumble.
                    fumble_msg_attacker += " You flail wildly!"

            else: # Default fumble if no other effect applies
                fumble_msg_attacker += " You flail uselessly!"
                fumble_msg_room += " What a mistake!"

            # Send fumble messages (verbose check still applies conceptually)
            vb_fumble_hit_check = " " + utils.colorize("{c}") + f"(Roll:{hit_roll})" + utils.colorize("{x}")
            if isinstance(attacker, Character): await attacker.send(fumble_msg_attacker + vb_fumble_hit_check)
            if isinstance(target, Character): await target.send(fumble_msg_target + vb_fumble_hit_check) # Target sees less detail?
            if attacker_loc: await attacker_loc.broadcast(f"\r\n{fumble_msg_room}\r\n", exclude={attacker, target})

        # Send Messages (Appending verbose string)
        if isinstance(attacker, Character): await attacker.send(miss_msg_attacker + f" {vb_hit_check}")
        if isinstance(target, Character): await target.send(miss_msg_target + f" {vb_hit_check}")
        if attacker_loc: await attacker_loc.broadcast(f"\r\n{miss_msg_room}\r\n", exclude={attacker, target})
        if rt_penalty > 0 and isinstance(attacker, Character): await attacker.send(f"{{yYour armor slightly hinders you (+{rt_penalty:.1f}s).{{x")
        return
    
    # --- Step 5b Block Check (Only if the Hit Succeeds) ---
    can_block = False
    shield_item: Optional[Item] = None
    if isinstance(target, Character) and target.stance == "Standing":
        shield_item = target.get_shield(world) # Use helper
        if shield_item:
            can_block = True

    if can_block:
        block_roll = random.random()
        if block_roll < effective_block_chance:
            log.info("%s BLOCKED %s's attack with shield!", target_name, attacker)
            # Apply roundtime to attacker (treat as miss for RT)
            base_rt = wpn_speed + bonus_rt_from_ability
            rt_penalty = 0.0
            if isinstance(attacker, Character):
                total_av = attacker.get_total_av(world); rt_penalty = math.floor(total_av / 20) * 1.0
            final_rt = base_rt + rt_penalty
            attacker.roundtime = final_rt

            # Send messages
            # block_msg_attacker = f"{{y{target_name} blocks your {attk_name} with their shield!{x}"
            # block_msg_target = f"{{gYou block {attacker_name}'s {attk_name} with your shield!{x"
            # block_msg_room = f"{target_name} blocks {attacker_name}'s {attk_name} with their shield."

            block_msg_attacker = utils.colorize("{y}") + f"{target_name} blocks your {attk_name} with their shield!" + utils.colorize("{x}")
            block_msg_target = utils.colorize("{g}") + f"You block {attacker_name}'s {attk_name} with your shield!" + utils.colorize("{x}")
            block_msg_room = f"{target_name} blocks {attacker_name}'s {attk_name} with their shield." # Room message usually uncolored

            if isinstance(attacker, Character): await attacker.send(block_msg_attacker)
            if isinstance(target, Character): await target.send(block_msg_target)
            if attacker_loc: await attacker_loc.broadcast(f"\r\n{block_msg_room}\r\n", exclude={attacker, target})
            # Add armor penalty msg if needed
            if rt_penalty > 0 and isinstance(attacker, Character): await attacker.send(...)

            return # Attack ends here, no damage dealt

    # --- 6. Calculate Damage ---
    rng_roll_result = 0; exploded = False
    if wpn_rng_dmg > 0:
        if is_crit:
            # --- V V V New Crit Damage Logic V V V ---
            log.debug("Crit! Rolling extra dice...")
            # Roll the normal damage dice once
            first_roll = random.randint(1, wpn_rng_dmg)
            # Roll the "extra" set using exploding dice logic
            extra_exploding_roll = roll_exploding_dice(wpn_rng_dmg)
            # Total random damage is the sum
            rng_roll_result = first_roll + extra_exploding_roll
            # Mark as exploded only if the *extra* roll actually exploded
            if extra_exploding_roll > wpn_rng_dmg:
                exploded = True
                log.debug("Crit Exploding Dice Result: %d (First: %d, Extra: %d)", rng_roll_result, first_roll, extra_exploding_roll)
            else:
                log.debug("Crit Normal Dice Result: %d (First: %d, Extra: %d)", rng_roll_result, first_roll, extra_exploding_roll)
            # --- ^ ^ ^ End New Crit Damage Logic ^ ^ ^ ---
        else: # Normal hit
            rng_roll_result = random.randint(1, wpn_rng_dmg)
            exploded = False # No explosion on normal hits

    # Determine stat modifier added to damage (logic remains same)
    stat_modifier_to_add = 0
    # ... (Determine stat_modifier_to_add based on attacker/weapon/ability) ...

    pre_mitigation_damage = max(0, wpn_base_dmg + rng_roll_result + stat_modifier_to_add)

    # Build Verbose Damage String (Update to show breakdown if crit)
    if is_crit:
        vb_damage_calc = f"{{y(Crit Dmg: Base({wpn_base_dmg}) + Roll1(d{wpn_rng_dmg}={first_roll}) + Roll2(d{wpn_rng_dmg}x={extra_exploding_roll}{'{r}*{x' if exploded else ''}) + Mod({stat_modifier_to_add}) = {pre_mitigation_damage}){{x"
    else: # Normal hit verbose string
        vb_damage_calc = f"{{y(Dmg: Base({wpn_base_dmg}) + Roll(d{wpn_rng_dmg}={rng_roll_result}) + Mod({stat_modifier_to_add}) = {pre_mitigation_damage}){{x"

    # --- 7. Mitigation ---
    # PDS
    defense_score_pds = base_target_pds
    after_pds_damage = max(0, pre_mitigation_damage - defense_score_pds)
    mit_pds = pre_mitigation_damage - after_pds_damage

    # Armor Value (AV)
    effective_av = 0
    mit_av = 0
    if dmg_type.lower() in physical_damage_types: # Use defined list
        base_av = 0
        if hasattr(target, 'get_total_av'): base_av = target.get_total_av(world)
        if base_av > 0 and hasattr(target, 'get_skill_rank'):
            armor_training_rank = target.get_skill_rank("armor training")
            av_multiplier = min(1.0, 0.20 + (armor_training_rank * 0.01))
            effective_av = math.floor(base_av * av_multiplier)
        else: effective_av = base_av # Use base AV if target has no skill rank (e.g., Mob)

        after_av_damage = max(0, after_pds_damage - effective_av)
        mit_av = after_pds_damage - after_av_damage
    else: # Non-physical damage bypasses AV
        after_av_damage = after_pds_damage

    # Barrier Value (BV) - Half Effect for Physical
    bv_mitigation = math.floor(target_bv / 2) # target_bv calculated earlier
    final_damage = max(0, after_av_damage - bv_mitigation)
    mit_bv = after_av_damage - final_damage

    # --- Build Verbose Mitigation String ---
    vb_mitigation = f"{{b(Mitigation: PDS({mit_pds}) + Eff.AV({mit_av}) + BV({mit_bv}) = {mit_pds + mit_av + mit_bv}){{x"

    # 8. Apply Damage & Check Concentration
    target.hp -= final_damage
    target.hp = max(0.0, target.hp) # Clamp HP at 0

    # Concentration Check
    if isinstance(target, Character) and final_damage > 0 and target.casting_info:
        spell_key = target.casting_info.get("key")
        spell_data = ability_defs.get_ability_data(spell_key)
        if spell_data and spell_data.get("type", "").upper() == "SPELL":
            # ... (Perform concentration check logic as in [193]) ...
            check_dc_modifier = int(final_damage) # Use integer damage for DC mod
            concentration_success = utils.skill_check(target, "concentration", difficulty_mod=check_dc_modifier)
            if not concentration_success:
                # ... (Clear casting_info, send messages) ...
                pass # Keep logic from [193]

    # 9. Send Messages
    hit_desc = "hit"; crit_indicator = ""
    if is_crit: hit_desc = "{rCRITICALLY HIT"; crit_indicator = " {rCRITICAL!{x"
    

    # --- Standard Messages ---
    std_dmg_msg_attacker = f"You {hit_desc} {target_name} with your {attk_name} for {{y{final_damage}{{x damage!{crit_indicator}"
    std_dmg_msg_target = f"{{R{attacker_name} {hit_desc.upper()}S you with {attacker_pronoun_poss} {attk_name} for {{y{final_damage}{{x damage!{crit_indicator}{{x"
    std_dmg_msg_target += f" {{x({int(target.hp)}/{int(target.max_hp)} HP)"
    std_dmg_msg_room = f"{attacker_name} {hit_desc.upper()}S {target_name} with {attacker_pronoun_poss} {attk_name}!"
    if final_damage > 0: std_dmg_msg_room += f" ({int(final_damage)} dmg)" # Show int damage
    if crit_indicator: std_dmg_msg_room += " {rCRITICAL!{x"

    # --- Build Full Verbose String ---
    verbose_details = f"\n\r   {{cRoll: {vb_hit_check}{{x" \
                    f"\n\r   {{yDmg: {vb_damage_calc}{{x" \
                    f"\n\r   {{bMit: {vb_mitigation}{{x"

    # --- Send Messages (Always Verbose for Participants) ---
    if isinstance(attacker, Character):
        await attacker.send(std_dmg_msg_attacker + verbose_details)
    if isinstance(target, Character):
        await target.send(std_dmg_msg_target + verbose_details)
    # Room message remains concise
    if attacker_loc:
        await attacker_loc.broadcast(f"\r\n{std_dmg_msg_room}\r\n", exclude={attacker, target})

    # 10. Apply Roundtime to Attacker
    base_rt = wpn_speed + bonus_rt_from_ability
    rt_penalty = 0.0; total_av = 0
    if isinstance(attacker, Character): total_av = attacker.get_total_av(world); rt_penalty = math.floor(total_av / 20) * 1.0
    final_rt = base_rt + rt_penalty
    attacker.roundtime = final_rt
    log.debug("Applied %.1fs RT to %s for hit (Base: %.1f, Ability: %.1f, AV Pen: %.1f)", final_rt, attacker.name, wpn_speed, bonus_rt_from_ability, rt_penalty)
    if rt_penalty > 0 and isinstance(attacker, Character):
        await attacker.send(f"{{yYour armor slightly hinders your attack (+{rt_penalty:.1f}s).{{x")

    if isinstance(attacker, Mob):
        log.info("COMBAT SET RT: Mob ID %d (%s) roundtime set to %.2f (wpn_speed=%.1f, bonus_rt=%.1f)",
                attacker.instance_id, attacker.name, final_rt, wpn_speed, bonus_rt_from_ability)
    else: # Log for characters too for completeness
        log.info("COMBAT SET RT: Character %s roundtime set to %.2f (Base: %.1f, AV Pen: %.1f)",
                attacker.name, final_rt, base_rt, rt_penalty)

    # 11. Check Defeat
    if target.hp <= 0:
        await handle_defeat(attacker, target, world)

async def resolve_magical_attack(
    caster: Union[Character, Mob], 
    target: Union[Character, Mob],
    spell_data: Dict[str, Any], # Data for the specific spell
    world: World
):
    """
    Resolves spell damage against a target, calculates detailed results,
    and sends verbose messages to participants.
    """
    log.debug("Resolving magical attack: %s -> %s", caster.name, target.name)
    effect_details = spell_data.get("effect_details", {})
    caster_name = caster.name.capitalize()
    target_name = target.name.capitalize()
    caster_loc = caster.location # Use caster's location for broadcast

    # 1. Get Caster Power & Target Defense

    if isinstance(caster, Character):
        caster_rating = caster.apr if effect_details.get("school") == "Arcane" else caster.dpr # Use APR or DPR based on school

    elif isinstance(caster, Mob):
        # Mobs use APR/DPR based on Int/Aura Mods for now
        caster_rating = caster.apr if effect_details.get("school") == "Arcane" else caster.dpr

    # Calculate target defenses (including potential skill/stance mods if applicable later)
    base_target_dv = target.dv
    dodge_bonus = 0; parry_bonus = 0 # Magic generally not parried, maybe dodged? Add skills later.
    final_target_dv = base_target_dv + dodge_bonus + parry_bonus
    # Apply stance penalty if target is character
    if hasattr(target, 'stance'):
        if target.stance == "Lying": final_target_dv = math.floor(final_target_dv * 0.5)
        elif target.stance == "Sitting": final_target_dv = math.floor(final_target_dv * 0.75)

    base_target_sds = target.sds # Spiritual Defense Score
    target_bv = target.barrier_value # Barrier Value

    # 2. Hit Check (Magic vs Dodge Value)
    always_hits = effect_details.get("always_hits", False)
    hit_roll = random.randint(1, 20)
    attack_score = caster_rating + hit_roll
    is_hit = False; is_crit = (hit_roll == 20); is_fumble = (hit_roll == 1)

    if always_hits: is_hit = True; is_crit = False; is_fumble = False
    elif is_fumble: is_hit = False
    elif is_crit: is_hit = True # Magic can crit? Yes, unless always_hits.
    elif attack_score >= final_target_dv: is_hit = True
    else: is_hit = False

    # Build Verbose Hit String
    spell_display_name = spell_data.get("name", "spell") # Get display name early
    vb_hit_check = f"{{c(Roll:{hit_roll} + Power:{caster_rating} = {attack_score} vs DV:{final_target_dv}){{x"

    # 3. Resolve Miss / Fumble
    if not is_hit:
        # Standard Messages
        miss_msg_room = f"{caster_name}'s {spell_display_name} misses {target_name}."
        miss_msg_target = f"{caster_name}'s {spell_display_name} {{Kmisses{{x you."
        miss_msg_caster = f"Your {spell_display_name} {{Kmisses{{x {target_name}."
        if is_fumble:
            miss_msg_room = f"{caster_name} {{Rfumbles{{x casting {spell_display_name}!"
            miss_msg_target = f"{caster_name} {{Rfumbles{{x casting their spell!"
            miss_msg_caster = f"{{RYou fumble casting {spell_display_name}!{{x"

        # Send Messages (Appending verbose string)
        if isinstance(caster, Character): await caster.send(miss_msg_caster + (f" {vb_hit_check}" if not always_hits else "")) # Don't show roll for always_hits miss? Doesn't make sense. Show always? No, don't show for miss if always_hits.
        if isinstance(target, Character): await target.send(miss_msg_target + (f" {vb_hit_check}" if not always_hits else ""))
        if caster_loc: await caster_loc.broadcast(f"\r\n{miss_msg_room}\r\n", exclude={caster, target})
        # Note: No roundtime applied here; post-cast RT is handled by the resolver in world.py
        return # End resolution

    # 4. Calculate Damage (Crit = Roll normal dice + Roll exploding dice)
    base_dmg = effect_details.get("damage_base", 0)
    rng_dmg = effect_details.get("damage_rng", 0) # This is the dX for the spell

    rng_roll_result = 0 # Initialize to 0
    exploded = False
    first_roll = 0 # Initialize for crit path
    extra_exploding_roll = 0 # Initialize for crit path

    if rng_dmg > 0:
        # Allow crits unless always_hits is true
        if is_crit and not always_hits:
            log.debug("Magic Crit! Rolling extra dice...")
            first_roll = random.randint(1, rng_dmg) # Assign first part
            extra_exploding_roll = roll_exploding_dice(rng_dmg)
            rng_roll_result = first_roll + extra_exploding_roll
            if extra_exploding_roll > rng_dmg: exploded = True
            # --- ^ ^ ^ End New Crit Damage Logic ^ ^ ^ ---
        else: # Normal hit or always_hits spell
            rng_roll_result = random.randint(1, rng_dmg)
            exploded = False

    # Add caster's power modifier
    stat_modifier = 0
    if isinstance(caster, Character): stat_modifier = caster.apr if effect_details.get("school") == "Arcane" else caster.dpr
    elif isinstance(caster, Mob): stat_modifier = caster.int_mod # Default for mobs
    pre_mitigation_damage = max(0, base_dmg + rng_roll_result + stat_modifier)

    if is_crit and not always_hits:
        explode_indicator = '{r}*{x' if exploded else ''
        vb_damage_calc_magic = f"{{y(Crit Dmg: Base({base_dmg}) + Roll1(d{rng_dmg}={first_roll}) + Roll2(d{rng_dmg}x={extra_exploding_roll}{explode_indicator}) + Mod({stat_modifier}) = {pre_mitigation_damage}){{x"
    else:
        vb_damage_calc_magic = f"{{y(Dmg: Base({base_dmg}) + Roll(d{rng_dmg}={rng_roll_result}) + Mod({stat_modifier}) = {pre_mitigation_damage}){{x"

    # 5. Mitigation (SDS + BV)
    mit_sds = mit_bv = 0 # Initialize mitigation amounts
    # TODO: Check damage_type vs resistances/vulnerabilities later
    after_sds_damage = max(0, pre_mitigation_damage - base_target_sds)
    mit_sds = pre_mitigation_damage - after_sds_damage

    final_damage = max(0, after_sds_damage - target_bv) # Full Barrier Value vs Magic
    mit_bv = after_sds_damage - final_damage

    # Build Verbose Mitigation String
    vb_mitigation = f"{{b(Mitigation: SDS({mit_sds}) + BV({mit_bv}) = {mit_sds + mit_bv}){{x"

    # 6. Apply Damage & Check Concentration/Meditation
    target.hp -= final_damage
    target.hp = max(0.0, target.hp)

    # Break Meditation on damage
    if isinstance(target, Character) and target.status == "MEDITATING":
        log.info("Character %s meditation broken by magic damage.", target.name)
        target.status = "ALIVE"
        await target.send("{RThe magical assault disrupts your meditation!{x")

    # Concentration Check (if target is Character, took damage, was casting a spell)
    if isinstance(target, Character) and final_damage > 0 and target.casting_info:
        casting_spell_key = target.casting_info.get("key")
        casting_spell_data = ability_defs.get_ability_data(casting_spell_key)
        if casting_spell_data and casting_spell_data.get("type", "").upper() == "SPELL":
            log.debug(...) # Concentration check debug log
            check_dc_modifier = int(final_damage)
            concentration_success = utils.skill_check(target, "concentration", difficulty_mod=check_dc_modifier)
            if not concentration_success:
                log.info(...) # Fizzle log
                target.casting_info = None
                await target.send("{RYour concentration is broken! Your spell fizzles!{x")
                if target.location: await target.location.broadcast(...) # Waver message
            else:
                log.debug(...) # Success log

    # 7. Send Messages
    if is_crit:
        hit_desc = "{rCRITICALLY HITS{x"
        crit_indicator = " {rCRITICAL!{x"

    # Standard Messages
    # Removed Double S here
    std_dmg_msg_caster = f"Your {spell_display_name} {hit_desc} {target_name} for {{y{int(final_damage)}{{x damage!{crit_indicator}" # Show int damage
    std_dmg_msg_target = f"{{R{caster_name}'s {spell_display_name} {hit_desc.upper()} you for {{y{int(final_damage)}{{x damage!{crit_indicator}{{x"
    std_dmg_msg_target += f" {{x({int(target.hp)}/{int(target.max_hp)} HP)"
    std_dmg_msg_room = f"{caster_name}'s {spell_display_name} {hit_desc.upper()}S {target_name}!"
    if final_damage > 0: std_dmg_msg_room += f" ({int(final_damage)} dmg)"
    if crit_indicator: std_dmg_msg_room += " {rCRITICAL!{x"

    # Build Full Verbose String
    verbose_details = ""
    # Don't show roll details for always_hits spells like Magic Missile
    if not always_hits:
        verbose_details += f"\n\r   {{cRoll: {vb_hit_check}{{x"
        verbose_details += f"\n\r   {{yDmg: {vb_damage_calc_magic}{{x"
        verbose_details += f"\n\r   {{bMit: {vb_mitigation}{{x"

    # Send Messages (Always Verbose for Participants)
    if isinstance(caster, Character): await caster.send(std_dmg_msg_caster + verbose_details)
    if isinstance(target, Character): await target.send(std_dmg_msg_target + verbose_details)
    if caster_loc: await caster_loc.broadcast(f"\r\n{std_dmg_msg_room}\r\n", exclude={caster, target})


    if isinstance(caster, Mob):
        #Get speed from mob's attack data (passed as spell data)
        attack_speed = spell_data.get("speed", 3.0)
        final_rt = attack_speed

        caster.roundtime = final_rt
        log.info("COMBAT SET RT (Magic): Mob ID %d (%s) roundtime set to %.2f (speed=%.1f)",
                caster.instance_id, caster.name, final_rt, attack_speed)


    # 8. Check Defeat
    if target.hp <= 0:
        await handle_defeat(caster, target, world)

    # Note: Post-cast roundtime is applied by the World.update_roundtimes function after this returns.


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
    heal_msg_caster = f"You heal {target.name} for {int(actual_healed)} hit points."
    heal_msg_target = f"{caster.name.capitalize()} heals you for {int(actual_healed)} hit points."
    heal_msg_room = f"{caster.name.capitalize()} heals {target.name}."

    if caster == target: heal_msg_caster = f"You heal yourself for {int(actual_healed)} hit points."

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