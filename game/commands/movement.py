#game/commands/movement.py
"""
Movement commands.
"""

import logging
from typing import TYPE_CHECKING, Optional

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
    look_string = target_room.get_look_string(character)
    await character.send(look_string)

    #TODO: Apply roundtime for movement later (Phase 3 Task 3)
    # character.roundtime 1.0 # Example

# --- Command Function ---

async def cmd_move(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', direction: str) -> bool:
    """Handles all cardinal/ordinal directional movement commands."""

    if not character.location:
        log.warning("Character %s tried to move but has no location.", character.name)
        await character.send("You cannot seem to move from the void.")
        return True # Stay connected

    # Normalize direction just in case
    direction = direction.lower()

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

    if not exit_name:
        await character.send("Go where? (e.g., go hole, go doorway)")
        return True
    
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