# game/commands/abilities.py
"""
Commands related to using character abilities.
"""
import logging
from typing import TYPE_CHECKING, Optional, Union

from ..definitions import abilities as ability_defs
from ..mob import Mob
from ..character import Character
from .. import resolver as combat_logic
from .. import utils

if TYPE_CHECKING:
    from ..world import World

log = logging.getLogger(__name__)


async def cmd_use(character: Character, world: 'World', args_str: str) -> bool:
    """Handles the 'use <ability_name> [target_name]' command."""
    if character.stance != "Standing":
        await character.send("You must be standing to use abilities.")
        return True

    if not args_str:
        await character.send("Use which ability?")
        return True
    
    # --- 1. Parse Ability and Target ---
    normalized_input = args_str.strip().lower()
    found_key: Optional[str] = None
    target_name_input: Optional[str] = None

    longest_match_len = 0
    for ability_key, data in world.abilities.items():
        # The database column is 'ability_type', not 'type'
        if data.get("ability_type", "").upper() != "ABILITY":
            continue
        if normalized_input.startswith(ability_key):
            if len(ability_key) > longest_match_len:
                longest_match_len = len(ability_key)
                found_key = ability_key
                target_name_input = args_str.strip()[len(ability_key):].strip()


    if not found_key:
        await character.send("You don't know any ability by that name.")
        return True
        
    ability_key = found_key
    ability_data = ability_defs.get_ability_data(world, ability_key)
    display_name = ability_data.get("name", ability_key)
    effect_details = ability_data.get("effect_details", {})

    # --- 2. Check Requirements ---
    if not character.knows_ability(ability_key):
        await character.send(f"You don't know the ability '{display_name}'.")
        return True
    
    essence_cost = ability_data.get("cost", 0)
    if character.essence < essence_cost:
        await character.send(f"You don't have enough essence to use {display_name}.")
        return True
    
    # --- Special Ability Requirement Checks (e.g., Stealth) ---
    if effect_details.get("requires_stealth") and not character.is_hidden:
        await character.send("You must be hidden to use that ability.")
        return True

    # --- Stance Handling Logic ---
    if effect_details.get("is_stance"):
        stance_effects = effect_details.get("effects_to_apply", [])
        if not stance_effects:
            log.error(f"Stance ability '{ability_key}' has no effects_to_apply.")
            await character.send("That ability seems to be configured incorrectly.")
            return True

        first_effect_name = stance_effects[0].get("name")
        if first_effect_name and first_effect_name in character.effects:
            # --- TOGGLE OFF ---
            for effect_info in stance_effects:
                effect_name = effect_info.get("name")
                if effect_name and effect_name in character.effects:
                    if effect_info.get("stat_affected") == "max_hp":
                        amount = effect_info.get("amount", 0)
                        character.max_hp -= amount
                        character.hp = min(character.hp, character.max_hp)
                    del character.effects[effect_name]
            
            await character.send(f"You relax from your {display_name}.")
            character.roundtime = 1.0
            return True

    # --- 3. Validate Target ---
    required_target_type = ability_data.get("target_type", ability_defs.TARGET_NONE)
    target_obj: Optional[Union[Character, Mob]] = None
    target_id: Optional[Union[int, str]] = None
    target_obj_type_str: Optional[str] = None

    if required_target_type == ability_defs.TARGET_SELF:
        target_obj, target_id, target_obj_type_str = character, "self", "SELF"
    elif required_target_type == ability_defs.TARGET_NONE:
        target_obj, target_id, target_obj_type_str = None, None, "NONE"
    elif not target_name_input:
        is_beneficial = ability_data.get("effect_type") in [ability_defs.EFFECT_HEAL, ability_defs.EFFECT_BUFF]
        if is_beneficial:
            target_obj, target_id, target_obj_type_str = character, "self", "SELF"
        else:
            await character.send(f"Who or what do you want to use {display_name} on?")
            return True
    else:
        target_char = character.location.get_character_by_name(target_name_input)
        target_mob = character.location.get_mob_by_name(target_name_input)

        if target_char and target_char.is_alive():
            effect_type = ability_data.get("effect_type")
            is_offensive = effect_type in [ability_defs.EFFECT_DAMAGE, ability_defs.EFFECT_DEBUFF,
                                           ability_defs.EFFECT_MODIFIED_ATTACK, ability_defs.EFFECT_STUN_ATTEMPT]

            if is_offensive and target_char != character:
                if "SAFE_ZONE" in character.location.flags:
                    await character.send("<R>The guards intervene! You cannot attack other players here.<x>")
                    return True
                if character.group and target_char in character.group.members:
                    await character.send("You can't use hostile abilities on your own group.")
                    return True

            target_obj = target_char
            target_id = target_char.dbid
            target_obj_type_str = "character"

        elif target_mob and target_mob.is_alive():
            target_obj = target_mob
            target_id = target_mob.instance_id
            target_obj_type_str = "mob"
        else:
            await character.send(f"You don't see {target_name_input} here.")
            return True
            
    # --- 4. Execute Ability ---
    # Break stealth if hidden
    if character.is_hidden:
        character.is_hidden = False
        await character.send("You emerge from the shadows...")

    log.debug("Character %s using ability: %s", character.name, ability_key)
    character.essence -= essence_cost
    
    # Handle stances that apply multiple effects
    if effect_details.get("is_stance"):
        for effect in effect_details.get("effects_to_apply", []):
            await combat_logic.apply_effect(character, character, effect, ability_data, world)
    else:
        # Handle all other abilities
        await combat_logic.resolve_ability_effect(
            caster=character,
            target_ref=target_id,
            target_type_str=target_obj_type_str,
            ability_data=ability_data,
            world=world
        )
    
    base_rt = ability_data.get("roundtime", 1.0)
    rt_penalty = character.total_av * 0.05
    character.roundtime = base_rt + rt_penalty + character.slow_penalty
    if rt_penalty > 0:
        await character.send(f"Your armor slightly hinders your action (+{rt_penalty:.1f}s).")

    return True