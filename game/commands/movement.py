#game/commands/movement.py
"""
Movement commands.
"""
import math
import logging
from typing import TYPE_CHECKING, Optional, Dict, Any
from .. import utils

if TYPE_CHECKING:
    from ..character import Character
    from ..world import World
    import aiosqlite
    from ..room import Room
    

log = logging.getLogger(__name__)

# --- Internal Movement Helper ---
async def _perform_move(character: 'Character', world: 'World', target_room: 'Room', exit_name: str):
    """
    Handles the logic after a valid exit is found: announcements,
    state changes, sending new room look.

    Args:
        character: The character moving.
        world: The game world instance.
        target_room: The destination Room object.
        exit_name: The name of the exit command used (e.g., "north", "hole").
    """
    current_room = character.location
    char_name = character.name # Get name before potential broadcast issues

    if character.status == "MEDITATING":
        character.status = "ALIVE"
        await character.send("You stop meditating as you move.")

    # 1. Announce departure to old room (if character was in a room)
    if current_room:
        departure_msg = f"\r\n{char_name} leaves {exit_name}.\r\n"
        # Use await here for the async broadcast method
        await current_room.broadcast(departure_msg, exclude={character})
        # Remove character from old room
        current_room.remove_character(character)

    # 2. Update character's location reference
    character.update_location(target_room)

    # 3. Add character to new room
    target_room.add_character(character)

    # 4. Announce arrival to new room (excluding self)
    # TODO: Make arrival message depend on how they entered? (e.g. "climbs up from a hole")
    arrival_msg = f"\r\n{char_name} arrives.\r\n"
    await target_room.broadcast(arrival_msg, exclude={character})
    # 5. Send 'look' output of new room to the character
    look_string = target_room.get_look_string(character, world)
    await character.send(look_string)

    ground_items_output = []
    item_counts = {}
    # Access items directly from the target_room object's cache
    for item_id in target_room.items:
        item_counts[item_id] = item_counts.get(item_id, 0) + 1

    for template_id, count in sorted(item_counts.items()):
        # Use world object passed into _perform_move
        template = world.get_item_template(template_id)
        item_name = template['name'] if template else f"Item #{template_id}"
        display_name = item_name
        if count > 1: display_name += f" (x{count})"
        ground_items_output.append(display_name)
    
    # Access coinage directly from the target_room object's cache
    coinage = target_room.coinage
    if coinage > 0:
        ground_items_output.append(utils.format_coinage(coinage)) # Ensure utils imported

    if ground_items_output:
        await character.send("You also see here: " + ", ".join(ground_items_output) + ".")

    base_rt = 1.0 # Base movement roundtime
    total_av = character.get_total_av(world)
    rt_penalty = math.floor(total_av / 20) * 1.0 # +1.0s RT per 20 AV
    final_rt = base_rt + rt_penalty
    character.roundtime = final_rt
    if rt_penalty > 0:
        await character.send(f"Your armor slows your movement (+{rt_penalty:.1f}s).")

# --- Command Function ---

async def cmd_move(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', direction: str) -> bool:
    """Handles all cardinal/ordinal directional movement commands."""

    if not character.location:
        log.warning("Character %s tried to move but has no location.", character.name)
        await character.send("You cannot seem to move from the void.")
        return True # Stay connected

    # Normalize direction just in case
    direction = direction.lower()
    exit_data = character.location.exits.get(direction)

    if exit_data is None:
        await character.send("You can't go that way.")
        return True
    
    target_room_id: Optional[int] = None
    skill_check_data: Optional[Dict[str, Any]] = None

    if isinstance(exit_data, int):
        # Simple exit: value is the target room ID
        target_room_id = exit_data
    elif isinstance(exit_data, dict):
        # Complex exit: value is a dictionary
        target_room_id = exit_data.get('target')
        if not isinstance(target_room_id, int):
            log.error("Room %d exit '%s' dict has invalid target: %r", character.location.dbid, direction, target_room_id)
            await character.send("The way forward seems broken.")
            return True
        skill_check_data = exit_data.get('skill_check') # Get skill check info if present
    else:
        # Invalid data format in exits JSON
        log.error("Room %d exit '%s' has invalid data type: %r", character.location.dbid, direction, exit_data)
        await character.send("The way forward seems confused.")
        return True
    
    if skill_check_data and isinstance(skill_check_data, dict):
        skill_name = skill_check_data.get('skill')
        dc = skill_check_data.get('dc', 10) # Default DC 10 if missing

        if not skill_name:
            log.error("Room %d exit '%s' skill_check missing 'skill' key.", character.location.dbid, direction)
            await character.send("The obstacle seems undefined.")
            return True

        log.debug("Performing skill check: Char=%s, Skill=%s, DC=%d", character.name, skill_name, dc)
        # Use utils.skill_check, passing DC as the difficulty modifier
        success = utils.skill_check(character, skill_name, difficulty_mod=dc)

        character.roundtime = 10.0
        log.debug("Applied 10.0s roundtime to %s for skill check exit attempt.", character.name)

        if not success:
            fail_msg = skill_check_data.get('fail_message', f"You fail the {skill_name} check.")
            fail_damage = skill_check_data.get('fail_damage', 0)
            await character.send(fail_msg)
            if fail_damage > 0:
                character.hp = max(0, character.hp - fail_damage) # Apply damage
                await character.send(f"You take {fail_damage} damage!")
                # TODO: Check for death immediately?
                # if character.hp <= 0: await combat_logic.handle_defeat(...)
            return True # Movement failed
        else:
            success_msg = skill_check_data.get('success_message', f"You succeed the {skill_name} check!")
            await character.send(success_msg)
            # Continue to movement after successful check

    target_room_id = character.location.exits.get(direction)

    if target_room_id is None:
        await character.send("You can't go that way.")
        return True # Stay connected

    target_room = world.get_room(target_room_id)

    if target_room is None:
        log.error("Character %s exit '%s' in room %d points to non-existent room %d!",
                character.name, direction, character.location.dbid, target_room_id)
        await character.send("You try to move that way, but the path seems to crumble into nothingness.")
        return True # Stay connected

    # Call the helper to perform the actual move
    await _perform_move(character, world, target_room, direction)

    return True # Keep connection active

async def cmd_go(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Handles the 'go <target>' command for special exits."""

    if not character.location:
        log.warning("Character %s tried to 'go' but has no location.", character.name)
        await character.send("You cannot seem to go anywhere from the void.")
        return True
    
    exit_name = args_str.strip().lower() # Use the argument as the exit key
    exit_data = character.location.exits.get(exit_name)

    if not exit_name:
        await character.send("Go where? (e.g., go hole, go doorway)")
        return True
    
    target_room_id: Optional[int] = None
    skill_check_data: Optional[Dict[str, Any]] = None

    if isinstance(exit_data, int):
        target_room_id = exit_data
    elif isinstance(exit_data, dict):
        target_room_id = exit_data.get('target')
        if not isinstance(target_room_id, int):
            log.error("Room %d exit '%s' dict invalid target: %r", character.location.dbid, exit_name, target_room_id)
            await character.send("The way forward seems broken.")
            return True
        skill_check_data = exit_data.get('skill_check')
    else:
        log.error("Room %d exit '%s' has invalid data type: %r", character.location.dbid, exit_name, exit_data)
        await character.send("The way forward seems confused.")
        return True

    if skill_check_data and isinstance(skill_check_data, dict):
        skill_name = skill_check_data.get('skill')
        dc = skill_check_data.get('dc', 10)
        if not skill_name:
            log.error("Room %d exit '%s' skill_check missing 'skill' key.", character.location.dbid, exit_name)
            await character.send("The obstacle seems undefined.")
            return True

        log.debug("Performing skill check: Char=%s, Skill=%s, DC=%d", character.name, skill_name, dc)
        success = utils.skill_check(character, skill_name, difficulty_mod=dc)

        character.roundtime = 10.0
        log.debug("Applied 10.0s roundtime to %s for skill check exit attempt.", character.name)

        if not success:
            fail_msg = skill_check_data.get('fail_message', f"You fail the {skill_name} check.")
            fail_damage = skill_check_data.get('fail_damage', 0)
            await character.send(fail_msg)
            if fail_damage > 0:
                character.hp = max(0, character.hp - fail_damage)
                await character.send(f"You take {fail_damage} damage!")
                # TODO: Check for death
            character.roundtime = 2.0
            return True
        else:
            success_msg = skill_check_data.get('success_message', f"You succeed the {skill_name} check!")
            await character.send(success_msg)

    target_room = world.get_room(target_room_id)
    if target_room is None:
        log.error("Exit '%s' in room %d points to non-existent room %d!",
                exit_name, character.location.dbid, target_room_id)
        await character.send(f"You try to go '{exit_name}', but the way is blocked.")
        return True

    await _perform_move(character, world, target_room, exit_name)
    
    target_room_id = character.location.exits.get(exit_name)

    if target_room_id is None:
        await character.send(f"You see no exit like '{exit_name}' here.")
        return True
    
    target_room = world.get_room(target_room_id)

    if target_room is None:
        log.error("Character %s exit '%s' in room %d points to non-existent room %d!",
                character.name, exit_name, character.location.dbid, target_room_id)
        await character.send(f"You try to go '{exit_name}', but the way is blocked.")
        return True
    
    # Call the helper to perform the actual move
    await _perform_move(character, world, target_room, exit_name)

    return True # keep connection alive