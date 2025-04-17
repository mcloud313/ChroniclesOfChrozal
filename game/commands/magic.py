# game/commands/magic.py
"""
Commands related to spellcasting.
"""
import logging
import time
from typing import TYPE_CHECKING, Optional, Union
import aiosqlite

# Import necessary game components and definitions
from ..definitions import abilities as ability_defs
from ..mob import Mob
from ..character import Character

if TYPE_CHECKING:
    from ..world import World
    

log = logging.getLogger(__name__)

async def cmd_cast(character: Character, world: 'World', db_conn: aiosqlite.Connection, args_str: str) -> bool:
    """Handles the 'cast <spell_name> [target_name]' command."""

    if character.stance != "Standing":
        await character.send("You must be standing to cast.")
        return True

    if not args_str:
        await character.send("Cast which spell?")
        # Maybe list known spells? For now, just basic message.
        # known = ", ".join(s.title() for s in character.known_spells) or "None"
        # await character.send(f"Known Spells: {known})
        return True
    
    normalized_input = args_str.strip().lower()
    found_key: Optional[str] = None
    target_name_input: Optional[str] = None

    # Find the longest known spell key that matches the start of the input
    longest_match_len = 0
    for spell_key in ability_defs.ABILITIES_DATA.keys():
        # Only consider spells for the cast command
        if ability_defs.ABILITIES_DATA[spell_key].get("type", "").upper() != "SPELL":
            continue

        # Check if input starts with the key + a space, or is exactly the key
        if normalized_input == spell_key:
            if len(spell_key) > longest_match_len:
                found_key = spell_key
                longest_match_len = len(spell_key)
                target_name_input = None # No target specified
        elif normalized_input.startswith(spell_key + " "):
            if len(spell_key) > longest_match_len:
                found_key = spell_key
                longest_match_len = len(spell_key)
                # Target is whatever comes after spell key and space
                target_name_input = args_str.strip()[len(spell_key):].strip()

    if not found_key:
        # Try using the first word only, in case it's a single-word spell missed above
        first_word = normalized_input.split(" ", 1)[0]
        if ability_defs.get_ability_data(first_word) and ability_defs.ABILITIES_DATA[first_word].get("type", "").upper() == "SPELL":
            found_key = first_word
            target_name_input = args_str.strip()[len(first_word):].strip() if " " in args_str else None
        else:
            await character.send(f"Unrecognized spell. Did you mean one you know?")
            return True
        
    spell_key = found_key
    spell_data = ability_defs.get_ability_data(spell_key)
    display_name = spell_data.get("name", spell_key)
    log.debug("Parsed cast command: Spell='%s', Target Input='%s'", spell_key, target_name_input)

    # 2 Check Requirements
    if not character.knows_spell(spell_key):
        # This check might be redundant if get_Abilioty_data covers all known, but good safety
        await character.send(f"You don't know the spell '{display_name}'.")
        return True
    
    if character.level < spell_data.get("level_req", 1):
        await character.send(f"You are not experienced enough to cast {display_name} (Requires Level {spell_data['level_req']}).")
        
    essence_cost = spell_data.get("cost", 0)
    if character.essence < essence_cost:
        await character.send(f"You don't have enough essence to cast {display_name} (Requires {essence_cost}, Have {character.essence}).")
        return True
    
    # 3. Validate Target
    
    target_type = spell_data.get("target_type", ability_defs.TARGET_NONE) # Use ability_data or spell_data
    target_obj: Optional[Union[Character, Mob]] = None
    target_id = None
    target_obj_type_str = None
    found_target = False # Flag to track if we successfully found a valid target

    if target_type == ability_defs.TARGET_SELF:
        target_obj = character
        target_id = "self"
        target_obj_type_str = "SELF"
        found_target = True # Self is always valid if caster alive (checked by handler)
    elif target_type == ability_defs.TARGET_NONE:
        target_obj = None
        target_id = None
        target_obj_type_str = "NONE"
        found_target = True # No target needed is valid
    elif not target_name_input: 
        effect_type = spell_data.get("effect_type")
        can_target_self = target_type in [ability_defs.TARGET_CHAR, ability_defs.TARGET_CHAR_OR_MOB]
        is_beneficial = effect_type in [ability_defs.EFFECT_HEAL, ability_defs.EFFECT_BUFF]

        if can_target_self and is_beneficial:
            target_obj = character
            target_id = "self"
            target_obj_type_str = "SELF"
            found_target = True
            log.debug("No target specified for beneficial spell %s, defaulting to self.", spell_key)
    else: # Requires a target name in the room
        if not target_name_input:
            await character.send(f"Who or what do you want to {display_name} on?") # Use ability_key_input or spell_key_input
            return True
        target_name_lower = target_name_input.lower()

        temp_target = None # Use temporary variable
        # Check Characters first if applicable
        if target_type in [ability_defs.TARGET_CHAR, ability_defs.TARGET_CHAR_OR_MOB]:
            target_char = character.location.get_character_by_name(target_name_lower)
            # Allow targeting self only if explicitly TARGET_SELF (handled above)
            if target_char and target_char != character:
                if target_char.is_alive():
                    temp_target = target_char
                    target_obj_type_str = "CHAR"
                else:
                    await character.send(f"{target_char.name} is already defeated.")
                    return True # Stop if target found but dead

        # Check Mobs if no character found OR if type allows Mob
        if not temp_target and target_type in [ability_defs.TARGET_MOB, ability_defs.TARGET_CHAR_OR_MOB]:
            target_mob = character.location.get_mob_by_name(target_name_lower)
            if target_mob:
                if target_mob.is_alive():
                    temp_target = target_mob
                    target_obj_type_str = "MOB"
                else:
                    await character.send(f"{target_mob.name.capitalize()} is already defeated.")
                    return True # Stop if target found but dead

        # Now check if we found a valid target overall
        if temp_target:
            target_obj = temp_target
            target_id = target_obj.dbid if isinstance(target_obj, Character) else target_obj.instance_id
            found_target = True
        else:
            await character.send(f"You don't see '{target_name_input}' here to target.") # Corrected sned -> send
            return True

    # 4. Initiate casting sequence
    cast_time = spell_data.get("cast_time", 0.0)

    # Set the casting info state on the character
    character.casting_info = {
        "key": spell_key,
        "name": display_name,
        "target_id": target_id,
        "target_type": target_obj_type_str, # Store MOB or CHAR if applicable
        "cast_tyime": cast_time, # Store original cast time if needed
        # Finish_time not stored, rely on roundtime hitting 0
    }
    log.debug("Character %s starting cast: %s", character.name, character.casting_info)

    # Send feedback message
    target_display = f" on {target_obj.name}" if target_obj and target_obj != character else (" on yourself" if target_obj == character else "")
    await character.send(f"You begin casting {display_name}{target_display}...")

    # Apply casting time as roundtime (blocks other actions)
    character.roundtime = cast_time

    # Effect resolution happens later via ticker/roundtime check

    return True