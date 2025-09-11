# game/commands/magic.py
"""
Commands related to spellcasting.
"""
import logging
import random
from typing import TYPE_CHECKING, Optional, Union
import aiosqlite  # <-- FIX: Added missing import

from ..definitions import abilities as ability_defs
from ..mob import Mob
from ..character import Character

if TYPE_CHECKING:
    from ..world import World

log = logging.getLogger(__name__)


async def cmd_cast(character: Character, world: 'World', args_str: str) -> bool:
    """Handles the 'cast <spell_name> [target_name]' command."""
    if character.stance != "Standing":
        await character.send("You must be standing to cast spells.")
        return True

    if not args_str:
        await character.send("Cast which spell?")
        return True
    
    # --- 1. Parse Spell and Target ---
    normalized_input = args_str.strip().lower()
    found_key: Optional[str] = None
    target_name_input: Optional[str] = None

    longest_match_len = 0
    for spell_key, data in ability_defs.ABILITIES_DATA.items():
        if data.get("type", "").upper() != "SPELL":
            continue

        if normalized_input.startswith(spell_key):
            if len(spell_key) > longest_match_len:
                longest_match_len = len(spell_key)
                found_key = spell_key
                target_name_input = args_str.strip()[len(spell_key):].strip()

    if not found_key:
        await character.send("You don't know any spell by that name.")
        return True
        
    spell_key = found_key
    spell_data = ability_defs.get_ability_data(spell_key)
    display_name = spell_data.get("name", spell_key)
    log.debug("Parsed cast command: Spell='%s', Target Input='%s'", spell_key, target_name_input)

    # --- 2. Check Requirements ---
    if not character.knows_spell(spell_key):
        await character.send(f"You don't know the spell '{display_name}'.")
        return True
    
    if character.level < spell_data.get("level_req", 1):
        await character.send(f"You are not experienced enough to cast {display_name}.")
        return True
        
    spell_cost = spell_data.get("cost", 0)
    if character.essence < spell_cost:
        await character.send(f"You don't have enough essence to cast {display_name}.")
        return True
    
    # --- Armor Spell Failure Check
    failure_chance = character.total_spell_failure
    if failure_chance > 0 and (random.random() * 100) < failure_chance:
        await character.send(f"{{RYour armor restricts your movement, causing your {display_name} spell to fizzle!{{x")
        # The spell still costs essence and time on failure.
        character.essence -= spell_cost
        character.roundtime = spell_data.get("cast_time", 0.0)
        return True
    
    # --- 3. Validate Target ---
    required_target_type = spell_data.get("target_type", ability_defs.TARGET_NONE)
    target_obj: Optional[Union[Character, Mob]] = None
    target_id: Optional[Union[int, str]] = None
    target_obj_type_str: Optional[str] = None

    if required_target_type == ability_defs.TARGET_SELF:
        target_obj, target_id, target_obj_type_str = character, "self", "SELF"
    elif required_target_type == ability_defs.TARGET_NONE:
        target_obj, target_id, target_obj_type_str = None, None, "NONE"
    elif not target_name_input:
        is_beneficial = spell_data.get("effect_type") in [ability_defs.EFFECT_HEAL, ability_defs.EFFECT_BUFF]
        if is_beneficial:
            target_obj, target_id, target_obj_type_str = character, "self", "SELF"
        else:
            await character.send(f"Who or what do you want to cast {display_name} on?")
            return True
    else:
        target_char = character.location.get_character_by_name(target_name_input)
        target_mob = character.location.get_mob_by_name(target_name_input)

        if target_char and target_char.is_alive():
            target_obj, target_obj_type_str = target_char, "CHAR"
        elif target_mob and target_mob.is_alive():
            target_obj, target_obj_type_str = target_mob, "MOB"
        
        if not target_obj:
            await character.send(f"You don't see '{target_name_input}' here to target.")
            return True

        target_id = target_obj.dbid if isinstance(target_obj, Character) else target_obj.instance_id

    # --- 4. Initiate Casting Sequence ---
    cast_time = spell_data.get("cast_time", 0.0)

    character.casting_info = {
        "key": spell_key,
        "name": display_name,
        "target_id": target_id,
        "target_type": target_obj_type_str,
        "cast_time": cast_time,
    }
    log.debug("Character %s starting cast: %s", character.name, character.casting_info)

    target_display = ""
    if target_obj:
        target_display = f" on yourself" if target_obj == character else f" on {target_obj.name}"
    
    await character.send(f"You begin casting {display_name}{target_display}...")
    character.roundtime = cast_time

    return True