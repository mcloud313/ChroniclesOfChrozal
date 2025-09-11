# game/commands/handler.py
"""
Handles parsing player input and dispatching commands.
"""
import logging
from typing import Dict, Callable, Awaitable, Tuple
from functools import partial

# Import necessary game objects
from ..character import Character
from ..world import World

# Import command modules
from . import general as general_cmds
from . import movement as movement_cmds
from . import admin as admin_cmds
from . import item as item_cmds
from . import combat as combat_cmds
from . import skill as skill_cmds
from . import magic as magic_cmds
from . import abilities as ability_cmds
from . import trade as trade_cmds
from . import social as social_cmds

log = logging.getLogger(__name__)

# REFACTOR: Removed the database connection from the function signature type
CommandHandlerFunc = Callable[[Character, World, str], Awaitable[bool]]

# --- Command Map ---
COMMAND_MAP: Dict[str, CommandHandlerFunc] = {
    # General Commands
    "look": general_cmds.cmd_look, "l": general_cmds.cmd_look,
    "say": general_cmds.cmd_say, "'": general_cmds.cmd_say,
    "quit": general_cmds.cmd_quit,
    "who": general_cmds.cmd_who,
    "help": general_cmds.cmd_help,
    "score": general_cmds.cmd_score, "stats": general_cmds.cmd_score,
    "skills": general_cmds.cmd_skills,
    "advance": general_cmds.cmd_advance, "level": general_cmds.cmd_advance,
    "meditate": general_cmds.cmd_meditate,
    "emote": general_cmds.cmd_emote, ":": general_cmds.cmd_emote,
    "tell": general_cmds.cmd_tell,
    "sit": general_cmds.cmd_sit,
    "stand": general_cmds.cmd_stand,
    "lie": general_cmds.cmd_lie,

    # Social Commands
    "group": social_cmds.cmd_group,
    "disband": social_cmds.cmd_disband,
    "kick": social_cmds.cmd_kick,
    "leave": social_cmds.cmd_leave,

    # Combat & Ability Commands
    "attack": combat_cmds.cmd_attack, "a": combat_cmds.cmd_attack, "kill": combat_cmds.cmd_attack,
    "cast": magic_cmds.cmd_cast,
    "use": ability_cmds.cmd_use,

    # Item Commands
    "inventory": item_cmds.cmd_inventory, "inv": item_cmds.cmd_inventory, "i": item_cmds.cmd_inventory,
    "wield": item_cmds.cmd_wear,
    "wear": item_cmds.cmd_wear,
    "remove": item_cmds.cmd_remove, "rem": item_cmds.cmd_remove,
    "get": item_cmds.cmd_get, "g": item_cmds.cmd_get, "take": item_cmds.cmd_get,
    "drop": item_cmds.cmd_drop,
    "put": item_cmds.cmd_put,
    "examine": item_cmds.cmd_examine, "exa": item_cmds.cmd_examine,
    "list": trade_cmds.cmd_list,
    "buy": trade_cmds.cmd_list,
    "sell": trade_cmds.cmd_list,
    "give": trade_cmds.cmd_list,
    "accept": trade_cmds.cmd_list,
    "decline": trade_cmds.cmd_list,
    "balance": trade_cmds.cmd_list,
    "deposit": trade_cmds.cmd_list,
    "withdraw": trade_cmds.cmd_withdraw,
    "repair": item_cmds.cmd_repair,
    "drink": item_cmds.cmd_drink,
    "eat": item_cmds.cmd_eat,

    # Skill/Progression Commands
    "spend": skill_cmds.cmd_spend, "invest": skill_cmds.cmd_spend,
    "improve": skill_cmds.cmd_improve,

    # Movement Command
    "go": movement_cmds.cmd_go,

    # Admin Commands (Reduced Set for In-Game Use)
    "@teleport": admin_cmds.cmd_teleport,
    "@examine": admin_cmds.cmd_examine,
    "@setstat": admin_cmds.cmd_setstat,
    "@roomstat": admin_cmds.cmd_roomstat,
}

# Use a loop to add directional commands cleanly
DIRECTIONAL_ALIASES = {
    "north": "north", "n": "north", "south": "south", "s": "south",
    "east": "east", "e": "east", "west": "west", "w": "west",
    "up": "up", "u": "up", "down": "down", "d": "down",
    "northeast": "northeast", "ne": "northeast", "northwest": "northwest", "nw": "northwest",
    "southeast": "southeast", "se": "southeast", "southwest": "southwest", "sw": "southwest",
}

for alias, direction in DIRECTIONAL_ALIASES.items():
    COMMAND_MAP[alias] = partial(movement_cmds.cmd_move, direction=direction)

def _parse_input(raw_input: str) -> Tuple[str, str]:
    """Splits raw input into a command verb and arguments string."""
    stripped_input = raw_input.strip()
    if not stripped_input:
        return "", ""
    parts = stripped_input.split(" ", 1)
    return parts[0].lower(), parts[1] if len(parts) > 1 else ""

async def process_command(character: Character, world: World, raw_input: str) -> bool:
    """Parses raw player input and executes the corresponding command function."""
    command_verb, args_str = _parse_input(raw_input)
    if not command_verb:
        return True

    # --- Pre-command State Checks ---
    if character.status == "DYING" and command_verb != "quit":
        await character.send("You are dying and cannot act!")
        return True
    if character.status == "DEAD" and command_verb != "quit":
        await character.send("You are dead and cannot do that.")
        return True
        
    MEDITATION_ALLOWED_CMDS = {"look", "l", "score", "stats", "skills", "quit", "help", "who", "tell"}
    if character.status == "MEDITATING" and command_verb not in MEDITATION_ALLOWED_CMDS:
        log.debug("Character %s broke meditation with command: %s", character.name, command_verb)
        character.status = "ALIVE"
        await character.send("You stop meditating as you act.")

    if character.roundtime > 0:
        await character.send(f"You are still recovering for {character.roundtime:.1f} seconds.")
        return True

    # --- Find and Execute Command ---
    command_func = COMMAND_MAP.get(command_verb)
    if not command_func:
        await character.send("Huh? (Type 'help' for available commands).")
        return True

    if command_verb.startswith('@') and not character.is_admin:
        await character.send("Huh? (Unknown command).")
        return True

    try:
        log.info("Executing command '%s' for %s (args: '%s')", command_verb, character.name, args_str)
        # REFACTOR: Call the command function with the new, shorter signature
        return await command_func(character, world, args_str)
    except Exception:
        log.exception("Error executing command '%s' for %s:", command_verb, character.name)
        await character.send("Ope! Something went wrong with your command.")
        return True