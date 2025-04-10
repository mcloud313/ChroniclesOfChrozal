# game/commands/admin.py
"""
Admin-only commands for server management and testing.
All command functions must be async and accept (character, world, db_conn, args_str).
Command verbs should start with '@'.
"""

import logging
from typing import TYPE_CHECKING
import json # for pretty printing stats/skills

# Avoid circular imports with type checking
if TYPE_CHECKING:
    from ..character import Character
    from ..world import World
    import aiosqlite

from .. import utils # For calculate_modifier
from .. import database # For examine

log = logging.getLogger(__name__)

# --- Admin Command Functions ---

async def cmd_teleport(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connction', args_str: str) -> bool:
    """@teleport <room_id>: Instantly moves character to target room ID."""
    if not args_str or not args_str.isdigit():
        await character.send("Usage: @teleport <room_id>")
        return True

    target_room_id = int(args_str)
    target_room = world.get_room(target_room_id)

    if target_room is None:
        await character.send(f"Error: Room ID {target_room_id} does not exist.")
        return True

    if not character.location:
        log.warning("Admin %s tried to teleport but has no location!", character.name)
        # Try placing them directly
    else:
        # Announce departure (optional for teleport)
        # character.location.broadcast(f"\r\n{character.name} vanishes in a puff of logic!\r\n", exclude={character})
        # Remove from old room
        character.location.remove_character(character)

    # Update location
    character.update_location(target_room)
    target_room.add_character(character)

    await character.send(f"You instantly teleport to {target_room.name} [{target_room.dbid}].")
    # Send look output of new room
    look_string = target_room.get_look_string(character)
    await character.send(look_string)
    return True

async def cmd_examine(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """@examine <type> <id/name>: Shows debug info about world objects."""
    parts = args_str.lower().split(" ", 1)
    if len(parts) != 2:
        await character.send("Usage: @examine <player|char|room|area|race|class> <username|id>")
        return True

    obj_type, identifier = parts

    output = f"--- Examining {obj_type} '{identifier}' ---\r\n"
    found = False

    try:
        if obj_type == "player":
            data = await database.load_player_account(db_conn, identifier)
            if data:
                output += json.dumps(dict(data), indent=2) # Pretty print DB row
                found = True
        elif obj_type == "char":
            if identifier.isdigit():
                char_id = int(identifier)
                # Check active characters first
                target_char = world.get_active_character(char_id)
                if target_char:
                    output += repr(target_char) + "\r\n"
                    output += f" PlayerID: {target_char.player_id}, Admin: {target_char.is_admin}\r\n"
                    output += f" Loc: {target_char.location_id} ({getattr(target_char.location, 'name', 'None')})\r\n"
                    output += f" HP: {target_char.hp}/{target_char.max_hp}, Ess: {target_char.essence}/{target_char.max_essence}\r\n"
                    output += f" XP Pool: {target_char.xp_pool}, XP Total: {target_char.xp_total}\r\n"
                    output += f" Stats: {json.dumps(target_char.stats)}\r\n"
                    output += f" Skills: {json.dumps(target_char.skills)}\r\n"
                    found = True
                else: # Check DB if not active
                    data = await database.load_character_data(db_conn, char_id)
                    if data:
                        output += json.dumps(dict(data), indent=2)
                        found = True
            else:
                await character.send("Please use character ID for @examine char.")

        elif obj_type == "room":
            if identifier.isdigit():
                room_id = int(identifier)
                room = world.get_room(room_id)
                if room:
                    output += repr(room) + "\r\n"
                    output += f" Desc: {room.description}\r\n"
                    output += f" Exits: {json.dumps(room.exits)}\r\n"
                    output += f" Flags: {json.dumps(list(room.flags))}\r\n"
                    output += f" Chars: {[c.name for c in room.characters]}\r\n"
                    # Add Mobs later
                    found = True

        elif obj_type == "area":
            if identifier.isdigit():
                area_id = int(identifier)
                area_data = world.get_area(area_id)
                if area_data:
                    output += json.dumps(dict(area_data), indent=2)
                    found = True
        # Add race/class examination later if needed
        elif obj_type == "mob":
            if identifier.isdigit():
                mob_instance_id = int(identifier) # Note: This is instance ID, not template ID
                target_mob = None
                # Search current room first (most common case)
                if character.location:
                    for mob in character.location.mobs:
                        if mob.instance_id == mob_instance_id:
                            target_mob = mob
                            break
                # TODO: Could add searching all world mobs later if needed

                if target_mob:
                    output += f"Found Mob Instance {mob_instance_id} in Room {getattr(target_mob.location, 'dbid', '?')}:\r\n"
                    output += f" Name: {target_mob.name}\r\n"
                    output += f" Template ID: {target_mob.template_id}\r\n"
                    output += f" HP: {target_mob.hp}/{target_mob.max_hp}\r\n"
                    output += f" Level: {target_mob.level}\r\n"
                    output += f" Stats: {json.dumps(target_mob.stats)}\r\n"
                    output += f" Flags: {list(target_mob.flags)}\r\n"
                    output += f" Target: {getattr(target_mob.target, 'name', 'None')}\r\n"
                    output += f" Fighting: {target_mob.is_fighting}\r\n"
                    output += f" Roundtime: {target_mob.roundtime:.1f}\r\n"
                    output += f" Dead Since: {target_mob.time_of_death}\r\n"
                    found = True
            else:
                # TODO: Implement finding mob by name later?
                await character.send("Use mob instance ID (a number) for @examine mob for now.")

        elif obj_type == "item_template" or obj_type == "itemtemplate":
            if identifier.isdigit():
                template_id = int(identifier)
                template_data = world.get_item_template(template_id) # Get from world cache
                if template_data:
                    output += f"Item Template ID: {template_id}\r\n"
                    # Pretty print the raw row data
                    output += json.dumps(dict(template_data), indent=2)
                    found = True
            else:
                await character.send("Use item template ID (a number) for @examine item_template.")
    except Exception as e:
        log.exception("Error during @examine: %s", e)
        output += f"\r\nError processing examine: {e}"

    if not found:
        output += "Object not found or type invalid."

    await character.send(output)
    return True

async def cmd_setstat(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """@setstat <stat_name> <value>: Sets a character's base stat (admin only)."""
    parts = args_str.lower().split()
    if len(parts) != 2:
        await character.send("Usage: @setstat <might|vitality|agility|intellect|aura|persona> <value>")
        return True

    stat_name, value_str = parts
    valid_stats = ["might", "vitality", "agility", "intellect", "aura", "persona"]

    if stat_name not in valid_stats:
        await character.send(f"Invalid stat name. Use one of: {', '.join(valid_stats)}")
        return True

    try:
        value = int(value_str)
        # Optional: Add range check (e.g., 1-50?)
        if value < 1: value = 1

        # Update the character object's stat dictionary
        character.stats[stat_name] = value
        log.info("Admin %s set %s's %s to %d (in memory).",
                character.name, character.name, stat_name, value)

        # Recalculate derived attributes like HP/Essence immediately
        character.calculate_initial_derived_attributes() # Renaming this later might be good
        await character.send(f"Set {stat_name.capitalize()} to {value}. Max HP/Essence recalculated.")
        await character.send(f"(Note: Stat change only saved on next quit/autosave unless @save used).")

    except ValueError:
        await character.send("Invalid value. Must be an integer.")
        return True

    return True

async def cmd_dig_placeholder(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """@dig <name>...: Placeholder for room creation."""
    log.info("Admin %s used @dig command (placeholder). Args: %s", character.name, args_str)
    await character.send("Room digging not implemented yet.")
    return True

async def cmd_tunnel_placeholder(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """@tunnel ...: Placeholder for exit creation."""
    log.info("Admin %s used @tunnel command (placeholder). Args: %s", character.name, args_str)
    await character.send("Exit tunneling not implemented yet.")
    return True