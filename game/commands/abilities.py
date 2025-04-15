# game/commands/abilities.py
"""
Commands related to using character abilities.
"""
import math
import logging
import time
import aiosqlite
from typing import TYPE_CHECKING, Optional, Union

# Import necessary game components and definitions
from ..definitions import abilities as ability_defs
from ..mob import Mob
from ..character import Character

if TYPE_CHECKING:
    from ..world import World

log = logging.getLogger(__name__)

async def cmd_use(character: Character, world: 'World', db_conn: aiosqlite.Connection, args_str: str) -> bool:
    """HAndles the 'use <ability_name> [target_name]' command."""

    if not args_str:
        await character.send("Use which ability?")
        return True
    
    parts = args_str.split(" ", 1)
    ability_key_input = parts[0].lower()
    target_name_input = parts[1].strip() if len(parts) > 1 else None

    # 1. Find ability data
    ability_data = ability_defs.get_ability_data(ability_key_input)

    if not ability_data or ability_data.get("type", "SPELL").upper() != "ABILITY":
        await character.send(f"You don't know any ability called '{ability_key_input}'.")
        return True
    
    ability_key = ability_key_input
    display_name = ability_data.get("name", ability_key)

    # 2. Check Requirements
    if not character.knows_ability(ability_key):
        await character.send(f"You don't know the ability '{display_name}'.")
        return True
    
    if character.level < ability_data.get("level_req", 1):
        await character.send(f"You are not experienced enough to use {display_name} (Requires level {ability_data['level_req']}).")
        return True
    
    # Abilities might have 0 cost, but check anyway
    essence_cost = ability_data.get("cost", 0)
    if character.essence < essence_cost:
        await character.send(f"You don't have enough essence to use {display_name} (Requires {essence_cost}, Have {character.essence}).")
        return True
    
    if character.casting_info:
        await character.send("You are already preparing another action!")
        return True
    

    # 3. Validate Target (Similar logic to cmd_cast)
    target_type = ability_data.get("target_type", ability_defs.TARGET_NONE)
    target_obj: Optional[Union[Character, Mob]] = None
    target_id = None
    target_obj_type_str = None

    if target_type == ability_defs.TARGET_SELF: target_obj = character; target_id = "self"; target_obj_type_str = "SELF"
    elif target_type == ability_defs.TARGET_NONE: target_obj = None; target_id = None; target_obj_type_str = "NONE"
    else: # Requires target name
        if not target_name_input:
            await character.send(f"Who or what do you want to use {display_name} on?")
            return True
        target_name_lower = target_name_input.lower()
        found_target = None
        if target_type in [ability_defs.TARGET_CHAR, ability_defs.TARGET_CHAR_OR_MOB]:
            target_char = character.location.get_character_by_name(target_name_lower)
            if target_char.is_alive(): found_target = target_char; target_obj_type_str = "CHAR"
            else: await character.send(f"{target_char.name} is already defeated."); return True
        if not found_target and target_type in [ability_defs.TARGET_MOB, ability_defs.TARGET_CHAR_OR_MOB]:
            target_mob = character.location.get_mob_by_name(target_name_lower)
            if target_mob:
                if target_mob.is_alive(): found_target = target_mob; target_obj_type_str = "MOB"
                else: await character.send(f"{target_mob.name} is already defeated."); return True
        if not found_target: 
            await character.sned(f"You don't see '{target_name_input}' here to target.")
            return True
        target_obj = found_target
        target_id = target_obj.dbid if isinstance(target_obj, Character) else target_obj.instance_id

    # 4. Instant Ability Execution
    cast_time = ability_data.get("cast_time", 0.0)
    if cast_time > 0:
        # This implies it *should* have been a spell - maybe error or use casting logic?
        # For now, log warning and treat as instant for abilities.
        log.warning("Ability '%s' has non-zero cast_time defined but is type ABILITY. Treating as instant.", ability_key)

    await character.send(f"You use {display_name}!") # Activate instantly

    # 5 Deduct Cost
    if essence_cost > 0:
        character.essence -= essence_cost
        # Optional: send cost message? Maybe only if > 0?

    # 6. Resolve Effect Immediately
    effect_type = ability_data.get("effect_type")
    effect_details = ability_data.get("effect_details", {})
    post_use_roundtime = ability_data.get("roundtime", 1.5) # Get Recover RT

    log.debug("Resolving instant ability: %s, Effect: %s", ability_key, effect_type)

    if effect_type == ability_defs.EFFECT_MODIFIED_ATTACK:
        # Example: Power Strike / Backstab
        # Perform modified attack check, if hit, roll stun chance
        log.warning("STUN_ATTEMPT effect resolution not fully implemented yet for %s", ability_key) # Placeholder
        # Need to call resolve_physical_attack with MAR penalty, then check stun chance & apply effect/RT to target

    elif effect_type == ability_defs.EFFECT_BUFF:
        # Example: Quick Reflexes
        # Apply buff effect directly to character/target
        log.warning("BUFF effect resolution not fully implemented yet for %s", ability_key) # Placeholder
        # Need buff system: character.effects[effect_name] = {"ends_at": time.monotonic() + duration, ...}

    elif effect_type == ability_defs.EFFECT_HEAL: # If any abilities heal
        # Apply heal effect
        log.warning("HEAL effect resolution not fully implemented yet for %s", ability_key)
        # Need combat_logic.apply_heal(target_obj, base, rng)

    else:
        log.warning("Unhandled instant ability effect type '%s' for %s", effect_type, ability_key)

    # 7. Apply Post-Use Roundtime (Recovery)
    # Add armor penalty here too!
    base_rt = post_use_roundtime
    rt_penalty = 0.0
    total_av = character.get_total_av(world)
    rt_penalty = math.floor(total_av / 20) * 1.0
    final_rt = base_rt + rt_penalty
    character.roundtime = final_rt
    log.debug("Applied %.1fs roundtime to %s for ability use (Base: %.1f, AV Pen: %.1f)",
            final_rt, character.name, base_rt, rt_penalty)
    if rt_penalty > 0:
        await character.send(f"Your armor slightly hinders your action (+{rt_penalty:.1f}s).")

    return True
