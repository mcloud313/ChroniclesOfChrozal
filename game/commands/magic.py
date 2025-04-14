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

    if not args_str:
        await character.send("Cast which spell?")
        # Maybe list known spells? For now, just basic message.
        # known = ", ".join(s.title() for s in character.known_spells) or "None"
        # await character.send(f"Known Spells: {known})
        return True
    
    parts = args_str.split(" ", 1)
    spell_key_input = parts[0].lower()
    target_name_input = parts[1].strip() if len(parts) > 1 else None

    # 1 Find Spell Data
    spell_data = ability_defs.get_ability_data(spell_key_input)

    if not spell_data or spell_data.get("type", "ABILITY").upper() != "SPELL":
        await character.send(f"You don't know any spell called '{spell_key_input}'.")
        return True
    
    spell_key = spell_key_input # Internal name is the lowercase key
    display_name = spell_data.get("name", spell_key)

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
    target_type = spell_data.get("target_type", ability_defs.TARGET_NONE)
    target_obj: Optional[Union[Character, Mob]] = None # Use Union if needed
    target_id = None # store ID for Casting_Info
    target_obj_type_str = None # store type for casting info

    if target_type == ability_defs.TARGET_SELF:
        target_obj = character
        target_id = "self" # Special Identifier
        target_obj_type_str = "SELF"
    elif target_type == ability_defs.TARGET_NONE:
        target_obj = None
        target_id = None
        target_obj_type_str = "NONE"
    else: # Requires a target name
        if not target_name_input:
            await character.send(f"Who or what do you want to cast {display_name} on?")
            return True
        target_name_lower = target_name_input.lower()

        # Find target (prioritize Characters if ambiguous, then Mobs)
        found_target = None
        if target_type in [ability_defs.TARGET_CHAR, ability_defs.TARGET_CHAR_OR_MOB]:
            target_char = character.location.get_character_by_name(target_name_lower)
            # Allow targeting self if the type allows CHAR OR SELF (handle SELF above)
            if target_char and (target_char != character or target_type == ability_defs.TARGET_SELF):
                if target_char.is_alive(): found_target = target_char; target_obj_type_str = "CHAR"
                else: await character.send(f"{target_char.name} is already defeated.") 
                return True
            
            if not found_target and target_type in [ability_defs.TARGET_MOB, ability_defs.TARGET_CHAR_OR_MOB]:
                target_mob = character.location.get_mob_by_name(target_name_lower)
                if target_mob:
                    if target_mob.is_alive(): found_target = target_mob; target_obj_type_str = "MOB"
                    else: await character.send(f"{target_mob.name} is already defeated."); return True

                    if not found_target:
                        await character.send(f"You don't see '{target_name_input}' here to target.")
                        return True
                    
                    target_obj = found_target
                    # Use DB ID for characters, Instance ID for mobs for persistent reference
                    target_id = target_obj.dbid if isinstance(target_obj, Character) else target_obj.instance_id
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