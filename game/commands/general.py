# game/commands/general.py
"""
General player commands like look, say, quit, who help.
"""
import logging
from typing import TYPE_CHECKING

# Avoid circular imports with type checking
if TYPE_CHECKING:
    from ..character import Character
    from ..world import World
    import aiosqlite

log = logging.getLogger(__name__)

# --- Command Functions ---
# Note: These functions match the CommandHandlerFunc signature

async def cmd_look(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Handles the 'look' command."""
    # TODO: Handle 'look <target>' later
    if args_str:
        await character.send("Just 'look' for now.")
        return True
    if not character.location:
        await character.send("You are floating in an endless void... somehow.")
        log.warning("Character %s tried to look but has no location.", character.name)
        return True
    
    # Get the description from the room and send it
    look_desc = character.location.get_look_string(character)
    await character.send(look_desc)
    return True # Keep connection active

async def cmd_say(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Handles the 'say' command."""
    if not args_str:
        await character.send("Say what?")
        return True
    
    if not character.location:
        log.warning("Character %s tried to say but has no location.", character.name)
        await character.send("You try to speak, but no sound comes out.")
        return True
    
    # Send message to self
    await character.send(f"You say: {args_str}")
    # Broadcast to the room
    message = f"{character.first_name} says: {args_str}" # Use first name for broadcasts
    character.location.broadcast(message + "\r\n", exclude={character}) # Add newline for broadcast
    return True

async def cmd_quit(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Handles the 'quit' command."""
    await character.send("Farewell!")
    log.info("Character %s is quitting.", character.name)
    await character.save(db_conn) # Save character state
    return False

async def cmd_who(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Handles the 'who' command"""
    active_chars = world.get_active_characters_list()
    if not active_chars:
        await character.send("You appear to be all alone in the world...")
        return True
    
    output = "\r\n--- Currently Online ---\r\n"
    # TODO: Add Title/Class/Race info later
    for char in sorted(active_chars, key=lambda c: c.name):
        # Simple name list for now
        output += f"{char.name}\r\n"
    output += "--------------------------\r\n"
    output += f"Total players: {len(active_chars)}\r\n"

    await character.send(output)
    return True

async def cmd_help(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Handles the 'help' command."""
    # TODO: Implement a proper help system later (e.g., help <command>)
    output = "\r\n--- Basic Commands ---\r\n"
    output += " look              - Look around the room.\r\n"
    output += " north, south      - Move in a direction (aliases: n, s, etc.).\r\n"
    output += " east, west        - \r\n"
    output += " up, down          - \r\n"
    output += " say <message>   - Speak to others in the room.\r\n"
    output += " who               - List players currently online.\r\n"
    output += " help              - Show this help message.\r\n"
    output += " quit              - Leave the game.\r\n"
    output += "----------------------\r\n"

    await character.send(output)
    return True

