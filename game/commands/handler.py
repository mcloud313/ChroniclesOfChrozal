# game/commands/handler.py
"""
Handles parsing player input and dispatching commands.
"""

import logging
from typing import Dict, Callable, Awaitable, Tuple, Optional

# Import necessary game objects (adjust paths if needed based on final structure)
# Use TYPE_CHECKING for circular dependencies if they arise later
from ..character import Character
from ..world import World
import aiosqlite # Needed for db_conn type hint
from . import general as general_cmds
from . import movement as movement_cmds
from . import admin as admin_cmds

log = logging.getLogger(__name__)

# Type alias for async command functions
# Takes Character, World, db_conn, and the arguments string
# Returns True if connection should continue, False if quit/disconnect
CommandHandlerFunc = Callable[[Character, World, aiosqlite.Connection, str], Awaitable[bool]]

# --- Command Map ---
# Maps command strings (and aliases) to their handler functions.
# We will populate this dictionary AFTER defining the command functions below
# and in other command modules
COMMAND_MAP: Dict[str, CommandHandlerFunc] = {
    # General Commands
    "look": general_cmds.cmd_look,
    "l": general_cmds.cmd_look, # Alias
    "say": general_cmds.cmd_say,
    "'": general_cmds.cmd_say, # Alias
    "quit": general_cmds.cmd_quit,
    "who": general_cmds.cmd_who,
    "help": general_cmds.cmd_help,
    "score": general_cmds.cmd_score,
    "stats": general_cmds.cmd_score, # Alias

    # Movement Commands (Pass direction directly to the handler)
    "north": lambda char, world, db_conn, args: movement_cmds.cmd_move(char, world, db_conn, "north"),
    "n": lambda char, world, db_conn, args: movement_cmds.cmd_move(char, world, db_conn, "north"),
    "south": lambda char, world, db_conn, args: movement_cmds.cmd_move(char, world, db_conn, "south"),
    "s": lambda char, world, db_conn, args: movement_cmds.cmd_move(char, world, db_conn, "south"),
    "east": lambda char, world, db_conn, args: movement_cmds.cmd_move(char, world, db_conn, "east"),
    "e": lambda char, world, db_conn, args: movement_cmds.cmd_move(char, world, db_conn, "east"),
    "west": lambda char, world, db_conn, args: movement_cmds.cmd_move(char, world, db_conn, "west"),
    "w": lambda char, world, db_conn, args: movement_cmds.cmd_move(char, world, db_conn, "west"),
    "up": lambda char, world, db_conn, args: movement_cmds.cmd_move(char, world, db_conn, "up"),
    "u": lambda char, world, db_conn, args: movement_cmds.cmd_move(char, world, db_conn, "up"),
    "down": lambda char, world, db_conn, args: movement_cmds.cmd_move(char, world, db_conn, "down"),
    "d": lambda char, world, db_conn, args: movement_cmds.cmd_move(char, world, db_conn, "down"),
    "go": lambda char, world, db_conn, args: movement_cmds.cmd_move(char, world, db_conn, args.strip()), # Add 'go' using args as direction/exit name
    # Add out, in, etc. if needed later

    "@teleport": admin_cmds.cmd_teleport,
    "@examine": admin_cmds.cmd_examine,
    "@setstat": admin_cmds.cmd_setstat,
    "@dig": admin_cmds.cmd_dig_placeholder, # Placeholder
    "@tunnel": admin_cmds.cmd_tunnel_placeholder, # Placeholder

}

def _parse_input(raw_input: str) -> Tuple[str, str]:
    """
    Normalizes input and splits it into command verb and arguments string.

    Args:
    raw_input: The raw string from the player

    Returns:
    A tuple containing (command_verb, arguments_string).
    Returns ("", "") if input is empty.
    """
    normalized = raw_input.lower().strip()
    if not normalized:
        return "", ""
    
    parts = normalized.split(" ", 1)
    command_verb = parts[0]
    args_str = parts[1] if len(parts) > 1 else ""

    return command_verb, args_str

async def process_command(character: Character, world: World, db_conn: aiosqlite.Connection, raw_input: str) -> bool:
    """
    Parses raw player input and executes the corresponding command function.

    Args:
        character: The Character executing the command.
        world: The game World object.
        db_conn: The active database connection.
        raw_input: The raw string typed by the player

    Returns:
        True if the player's connection should remain active, False if they should disconnect (e.g., quit).
    """
    command_verb, args_str = _parse_input(raw_input)

    if not command_verb:
        return True # Ignore empty input, keep connection active
    
    # Find the command function in our map
    command_func = COMMAND_MAP.get(command_verb)

    if command_func:
        is_admin_cmd = command_verb.startswith('@')
        if is_admin_cmd and not character.is_admin:
            log.warning("Non-admin %s tried to use admin command: %s", character.name, command_verb)
            await character.send("Huh? (Unknown command).")
            return True
        log.info("Executing command '%s' for %s (args: '%s')", command_verb, character.name, args_str)
        
        try:
            # Execute the command function
            should_continue = await command_func(character, world, db_conn, args_str)
            return should_continue
        except Exception:
            # Catch errors within command execution
            log.exception("Error executing command '%s' for %s:", command_verb, character.name, exc_info=True)
            await character.send("Ope! Something went wrong with your command.")
            return True # Keep connection active after internal command error
    else:
        # Unknown command
        log.debug("Unknown command '%s' entered by %s", command_verb, character.name, exc_info=True)
        await character.send("Huh? (Type 'help' for available commands).")
        return True # Keep connection alive