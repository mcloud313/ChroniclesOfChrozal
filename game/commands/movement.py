#game/commands/movement.py
"""
Movement commands.
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..character import Character
    from ..world import World
    import aiosqlite

log = logging.getLogger(__name__)

# --- Command Function ---

async def cmd_move(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', direction: str) -> bool:
    """Handles all directional movement commands."""

    if not character.location:
        log.warning("Character %s tried to move but has no location.", character.name)
        await character.send("No matter what way you attempt to propel yourself, you can't seem to move in a direction.")
        return True
    
    # Check if the direction is a valid exit from the current room
    target_room_id = character.location.exits.get(direction.lower())

    if target_room_id is None:
        await character.send("You can't go that way.")
        return True
    
    #Get the target Room object from the world
    target_room = world.get_room(target_room_id)

    if target_room is None:
        log.error("Character %s exit '%s' in room %d points to non-existent room %d!",
                character.name, direction, character.location.dbid, target_room_id)
        await character.send("You try to move that way, but the path seems to crumble into nothingness.")
        # Optional: Maybe remove the bad exit from character.location.exits here? Needs saving.
        return True # Stay connected
    
    # Execute movement
    current_room = character.location
    char_name = character.name # Get name before potential broadcast issues

    # 1. Announce departure to old room (excluding self)
    # Make messages generic, specific directions can be flavor later
    departure_msg = f"\r\n{char_name} leaves {direction}.\r\n"
    current_room.broadcast(departure_msg, exclude={character})

    # 2. Remove character from old room
    current_room.remove_character(character)

    # 3. Update character's location reference
    character.update_location(target_room)

    # 4. Add character to new room
    target_room.add_character(character)

    # 5. Announce arrival to new room (excluding self)
    arrival_msg = f"\r\n{char_name} arrives.\r\n"
    target_room.broadcast(arrival_msg, exclude={character})

    # 6. Send 'look' output of new room to the character
    look_string = target_room.get_look_string(character)
    await character.send(look_string)

    # TODO: Apply roundtime for movement later (Phase 3)
    # character.roundtime = 1.0 Example

    return True
