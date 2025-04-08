# game/commands/general.py
"""
General player commands like look, say, quit, who help.
"""
import logging
from typing import TYPE_CHECKING
from .. import utils

# Avoid circular imports with type checking
if TYPE_CHECKING:
    from ..character import Character
    from ..world import World
    import aiosqlite

log = logging.getLogger(__name__)

# --- Command Functions ---
# Note: These functions match the CommandHandlerFunc signature

async def cmd_look(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Handles the 'look' command (looking at room or target character)."""

    if not character.location:
        await character.send("You are floating in an endless void... somehow.")
        log.warning("Character %s tried to look but has no location.", character.name)
        return True # Keep connection active
    
    target_name = args_str.strip()

    # --- Look at Room (No arguments) ---
    if not target_name:
        look_desc = character.location.get_look_string(character)
        await character.send(look_desc)
        return True
    
    # --- Look at Target (Character) ---
    target = character.location.get_character_by_name(target_name)

    # Handle target not found
    if target is None:
        # TODO: Later, check for items/objects in the room here too
        await character.send(f"You don't see anyone or anything named '{target_name}' here.")
        return True
    
    # Handle looking at self - show room description (standard MUD behavior)
    if target == character:
        look_desc = character.location.get_look_string(character)
        await character.send(look_desc)
        return True
    
    # --- Format Target Character's Description ---
    try:
        # Get Race/Class Names
        target_race_name = world.get_race_name(target.race_id)
        target_class_name = world.get_class_name(target.class_id)

        # Get Pronouns
        pronoun_subj, _, _, verb_is, _ = utils.get_pronouns(target.sex)

        output = "\r\n"
        # Display the generated description stored on the character
        output += target.description # Assumes target.description is loaded from DB
        output += "\r\n"
        # Add basic info line
        output += f"({target_race_name} {target_class_name}, Level {target.level})\r\n"
        # Add equipment placeholder
        output += f"{pronoun_subj} {verb_is} wearing:\r\n Nothing." # Placeholder
        # TODO: Add wielded item placeholder later

        await character.send(output)
    
    except Exception:
        log.exception("Error generating look description for target %s:", target.name, exc_info=True)
        await character.send("You look at them, but your vision blurs momentarily.")

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

async def cmd_score(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Handles the 'score/stats' command."""

    # --- Gather Data ---
    char_name = character.name
    char_sex = character.sex
    # Get race/class names safely using world lookup
    race_name = world.get_race_name(character.race_id)
    class_name = world.get_class_name(character.class_id)
    level = character.level
    hp = character.hp
    max_hp = character.max_hp
    essence = character.essence
    max_essence = character.max_essence
    xp_pool = character.xp_pool # unspent banked XP
    xp_total = character.xp_total # xp earned this level
    xp_needed = utils.xp_to_next_level(level)

    # Attribute and Modifiers
    stats = character.stats # The dict like {'might': 15, ....}
    attributes_display = []
    stat_order = ["might", "vitality", "agility", "intellect", "aura", "persona"]
    modifiers = {} # Store modifiers for reuse
    for stat_name in stat_order:
        value = stats.get(stat_name, 10) # Get value, default 10
        modifier = utils.calculate_modifier(value)
        modifiers[stat_name] = modifier # Store modifier
        mod_sign = "+" if modifier >= 0 else "" # Add plus sign for positive/zero
        attributes_display.append(f" {stat_name.capitalize():<10}: {value:>2} [{mod_sign}{modifier}]")

    # Derived Stats
    might_val = stats.get("might", 10)
    max_carry_weight = might_val * 2

    # Coinage (Deferred until Phase 3)
    # coinage = character.coinage # Need this attribute added later
    # formatted_coinage = utils.format_coinage(coinage) # Need this util later

    # --- Format Output ---
    # Using f-strings with padding for alignment
    output = "\r\n" + "=" * 40 + "\r\n"
    output += f" Name : {char_name:<28} Sex: {char_sex}\r\n"
    output += f" Race : {race_name:<28} Class: {class_name}\r\n"
    output += f" Level: {level:<31}\r\n"
    output += "=" * 40 + "\r\n"
    output += f" HP   : {hp:>4}/{max_hp:<28} Carry: ??/{max_carry_weight} lbs\r\n" # Add current weight later
    output += f" Essn : {essence:>4}/{max_essence:<31}\r\n"
    # Display XP Needed for *next* level, show current progress
    output += f" XP   : {xp_total:>4}/{xp_needed:<28} Pool: {xp_pool}\r\n"
    output += " --- Attributes ---                 \r\n" # Adjusted spacing
    # Display 3 attributes per line
    output += f"{attributes_display[0]} {attributes_display[1]}\r\n"
    output += f"{attributes_display[2]} {attributes_display[3]}\r\n"
    output += f"{attributes_display[4]} {attributes_display[5]}\r\n"
    # Coinage display deferred
    # output += f" Coin : {formatted_coinage}\r\n"
    output += "=" * 40 + "\r\n"

    await character.send(output)
    return True # Keep connection active

