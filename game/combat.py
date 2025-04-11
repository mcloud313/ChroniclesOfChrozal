# game/combat.py
"""
Handles combat calculations and resolution.
"""
import random
import logging
import math # For floor in exploding dice? No, just loop
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
    total = 0
    while True:
        roll = random.randint(1, max_roll)
        total += roll
        if roll < max_roll:
            break
        # If roll was max, loop continues and adds another roll
        log.debug("Exploding die! (Rolled %d)", max_roll)
    return total

async def handle_defeat(attacker: Union['Character', 'Mob'], target: Union['Character', 'Mob'], world: 'World'):
    """Handles logic when a target's HP reaches 0."""
    log.info("%s has defeated %s!", getattr(attacker,'name','Something'), getattr(target,'name','Something'))

    # --- If Mob is defeated ---
    if isinstance(target, Mob):
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
                template = target.world.get_item_template(item_id) # Mob needs world ref? Pass it in. Or Room needs world ref. Pass world to handle_defeat.
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
            # TODO: Implement death timer start later (Phase 4)
            # target.death_timer_ends_at = time.monotonic() + target.vit_mod # Example

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

    attacker.xp_pool += xp_gain
    log.info("%s gains %d XP pool from defeating %s.", attacker.name, xp_gain, defeated_mob.name)
    await attacker.send(f"You gain {xp_gain} experience points.")
    # TODO: Distribute XP among party members later

# --- Main Combat Resolution ---
async def resolve_physical_attack(
    attacker: Union['Character', 'Mob'],
    target: Union['Character', 'Mob'],
    # Use the more generic name 'attack_source' to handle mob attack dicts
    attack_source: Optional[Union[Item, Dict[str, Any]]],
    world: 'World' 
    """Resolves a single physical attack round."""):

    # 1. Checks
    if not attacker.is_alive() or not target.is_alive(): return
    if not hasattr(attacker, 'location') or not hasattr(target, 'location') or attacker.location != target.location:
        # Clear target if one moved away during processing? Less likely without yield points here.
        log.debug("Resolve Attack: Attacker or Target missing location or not in same room.")
        return
    # roundtime check happens in command handler

    # 2. Get Attack/Defense Info & Determine Attack Variables
    attacker_rating = attacker.mar # Assume Melee Attack Rating for now
    attacker_name = attacker.name.capitalize()
    target_name = target.name.capitalize() # Use capitalize for consistency
    target_loc = attacker.location # Cache location

    # Define local variables for attack properties with defaults
    weapon: Optional[Item] = None # Will hold Item object if char uses weapon
    attk_name = "attack"
    wpn_speed = 2.0
    wpn_base_dmg = 1
    wpn_rng_dmg = 0
    dmg_type = "physical"
    stat_modifier = attacker.might_mod # Default to Might for physical

    # Determine specifics based on attacker type and attack_source
    if isinstance(attacker, Mob):
        # --- Mob Attack ---
        mob_attack_data = attack_source # attack_source should be the dict from mob.choose_attack()
        if isinstance(mob_attack_data, dict):
            attk_name = mob_attack_data.get("name", "strike")
            wpn_speed = mob_attack_data.get("speed", 2.0)
            wpn_base_dmg = mob_attack_data.get("damage_base", 1)
            wpn_rng_dmg = mob_attack_data.get("damage_rng", 0)
            # dmg_type = mob_attack_data.get("damage_type", "physical") # TODO: Add damage_type to mob attacks later
            # stat_modifier = ? # TODO: Base mob damage on stats later? Use template stats for now.
        else: # Mob default unarmed
            attk_name = "hits" # Verb fits better
            wpn_speed = 2.0; wpn_base_dmg = 1; wpn_rng_dmg = 1; dmg_type = "bludgeon"
        # weapon variable remains None for mobs

    elif isinstance(attacker, Character):
        # --- Character Attack ---
        if isinstance(attack_source, Item) and attack_source.item_type == "WEAPON":
            # Character attack with weapon
            weapon = attack_source # Assign Item object to local weapon var
            attk_name = f"attack with {weapon.name}" # More descriptive
            wpn_speed = weapon.speed
            wpn_base_dmg = weapon.damage_base
            wpn_rng_dmg = weapon.damage_rng
            dmg_type = weapon.damage_type or "bludgeon" # Default physical type
            # stat_modifier remains attacker.might_mod (for melee)
        else:
            # Character unarmed attack
            attk_name = "punch"
            wpn_speed = 2.0; wpn_base_dmg = 1; wpn_rng_dmg = 1; dmg_type = "bludgeon"
            # weapon variable remains None

    else: # Should not happen
        log.error("resolve_physical_attack: Invalid attacker type %s", type(attacker))
        return

    # --- Target --- (remains the same)
    target_dv = target.dv
    target_pds = target.pds
    # target_sds = target.sds # For magic later
    target_av = 0 # Placeholder for V1

    # 3. Block Check (Deferred V1)

    # 4. Hit Check (remains the same)
    hit_roll = random.randint(1, 20)
    # ... (calculate attack_score, is_hit, is_crit, is_fumble) ...
    attack_score = attacker_rating + hit_roll
    is_hit = False
    is_crit = (hit_roll == 20)
    is_fumble = (hit_roll == 1)
    if is_fumble: is_hit = False
    elif is_crit: is_hit = True
    elif attack_score >= target_dv: is_hit = True
    else: is_hit = False

    # 5. Resolve Miss / Fumble (uses local vars now)
    if not is_hit:
        attacker.roundtime = wpn_speed # Apply roundtime
        # Construct messages using local variables like attk_name
        miss_msg_attacker = f"You try to {attk_name} {target_name}, but miss."
        miss_msg_target = f"{attacker_name} tries to {attk_name} you, but misses."
        miss_msg_room = f"{attacker_name} tries to {attk_name} {target_name}, but misses."
        if is_fumble:
            miss_msg_attacker = f"You fumble your attempt to {attk_name} {target_name}!"
            # ... (other fumble messages) ...
            miss_msg_target = f"{attacker_name} fumbles while trying to {attk_name} you!"
            miss_msg_room = f"{attacker_name} fumbles while trying to {attk_name} {target_name}!"


        if isinstance(attacker, Character): await attacker.send(miss_msg_attacker)
        if isinstance(target, Character): await target.send(miss_msg_target)
        # Use attacker.location for broadcast
        if attacker.location: await attacker.location.broadcast(f"\r\n{miss_msg_room}\r\n", exclude={attacker, target})
        return # End combat round

    # 6. Calculate Damage (uses local vars now)
    total_random_damage = 0
    if wpn_rng_dmg > 0:
        if is_crit:
            total_random_damage = roll_exploding_dice(wpn_rng_dmg)
        else:
            total_random_damage = random.randint(1, wpn_rng_dmg)

    pre_mitigation_damage = max(0, wpn_base_dmg + total_random_damage + stat_modifier)

    # 7. Mitigation (remains the same, uses target_pds, target_av=0)
    defense_score = target_pds
    mitigated_damage1 = max(0, pre_mitigation_damage - defense_score)
    final_damage = max(0, mitigated_damage1 - target_av) # AV is 0 for V1

    # 8. Apply Damage (remains the same)
    target.hp -= final_damage
    target.hp = max(0, target.hp)

    # 9. Send Messages (uses local vars now)
    hit_desc = "hit"
    crit_indicator = ""
    if is_crit:
        hit_desc = "CRITICAlly HIT"
        crit_indicator = " CRITICAL!"
    attacker_pronoun_subj, _, attacker_pronoun_poss, _, _ = utils.get_pronouns(getattr(attacker, 'sex', None))

    # Message for Attacker
    dmg_msg_attacker = f"You {hit_desc} {target_name} with your {attk_name} for {final_damage} damage!{crit_indicator}"

    # Message for Target
    # Using attacker's first name for possessive might be simpler if name property reliable
    # attacker_possessive = attacker.name + "'s" # Simple possessive
    attacker_possessive = attacker_pronoun_poss # Use calculated possessive pronoun
    dmg_msg_target = f"{attacker_name} {hit_desc.upper()}S you with {attacker_possessive} {attk_name} for {final_damage} damage!{crit_indicator}"
    # Optional: Add target HP remaining
    dmg_msg_target += f" ({target.hp}/{target.max_hp} HP)"


    # Message for Room (Uses attacker_pronoun_poss)
    dmg_msg_room = f"{attacker_name} {hit_desc.upper()}S {target_name} with {attacker_pronoun_poss} {attk_name} for {final_damage} damage!"
    # --- ^ ^ ^ End Message Formatting ^ ^ ^ ---

    # Send the messages
    if isinstance(attacker, Character): await attacker.send(dmg_msg_attacker)
    if isinstance(target, Character): await target.send(dmg_msg_target)
    if attacker.location: await attacker.location.broadcast(f"\r\n{dmg_msg_room}\r\n", exclude={attacker, target})

    # 10. Apply Roundtime to Attacker (uses local wpn_speed)
    attacker.roundtime = wpn_speed

    # 11. Check Defeat (passes world correctly now)
    if target.hp <= 0: # Use <= 0 for safety
        await handle_defeat(attacker, target, world)