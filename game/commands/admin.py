# game/commands/admin.py
"""
Admin-only commands for server management and testing.
All command functions must be async and accept (character, world, db_conn, args_str).
Command verbs should start with '@'.
"""
import asyncio
import logging
import functools
import math
from typing import TYPE_CHECKING, Optional, Dict, Any, List, Union
import json # for pretty printing stats/skills

from .. import database
from .. import utils # For reverse exit etc.
from ..room import Room # Needed to create new Room object in memory

# Avoid circular imports with type checking
if TYPE_CHECKING:
    from ..character import Character
    from ..world import World
    import aiosqlite

log = logging.getLogger(__name__)

#---Room creation---
VALID_ROOM_FLAGS = {"NODE", "RESPAWN", "INDOORS", "OUTDOORS", "WET", "DARK", "HOLY", "QUIET", "ROUGH_TERRAIN", "WINDY", "HEIGHTS", "SHOP"}

async def cmd_teleport(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Admin command: Teleports the admin to a specified room ID."""
    if not args_str or not args_str.isdigit():
        await character.send("Usage: @teleport <room_id>")
        return True

    target_room_id = int(args_str)
    target_room = world.get_room(target_room_id)

    if not target_room:
        await character.send(f"Room ID {target_room_id} does not exist.")
        return True

    if character.location == target_room:
        await character.send("You are already there!")
        return True

    # Use _perform_move logic (ensure it's imported or accessible)
    # Need the _perform_move helper from movement.py, maybe move it to utils?
    # For now, duplicate essential logic:
    current_room = character.location
    char_name = character.name

    await character.send(f"Teleporting to Room {target_room_id}...")

    # Announce departure
    if current_room:
        departure_msg = f"\r\n{char_name} vanishes in a puff of smoke.\r\n"
        await current_room.broadcast(departure_msg, exclude={character})
        current_room.remove_character(character)

    # Update character's location
    character.update_location(target_room)

    # Add character to new room
    target_room.add_character(character)

    # Announce arrival
    arrival_msg = f"\r\n{char_name} appears in a flash of light.\r\n"
    await target_room.broadcast(arrival_msg, exclude={character})

    # Send 'look' output of new room
    look_string = target_room.get_look_string(character, world)
    await character.send(look_string)
    # Also send ground items/coins
    ground_items_output = []
    # ... (copy ground item/coin listing logic from _perform_move / cmd_look) ...
    if ground_items_output: await character.send(...)

    character.roundtime = 0 # No RT for admin teleport
    return True

async def cmd_roomstat(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Admin command: Shows detailed stats for the current or specified room."""

    target_room_id = None
    room_to_stat = None

    if not args_str:
        if character.location:
            room_to_stat = character.location
            target_room_id = character.location.dbid
        else: await character.send("You aren't in a room."); return True
    elif args_str.isdigit():
        target_room_id = int(args_str)
        room_to_stat = world.get_room(target_room_id)
        if not room_to_stat: await character.send(f"Room {target_room_id} not found."); return True
    else:
        await character.send("Usage: @roomstat [room_id]")
        return True

    # Fetch detailed data if needed (current object might be slightly out of sync?)
    # For now, use the in-memory object
    area_name = world.get_area_name(room_to_stat.area_id)
    output = [f"\r\n--- Room Stats for [{room_to_stat.dbid}] {room_to_stat.name} ---"]
    output.append(f" Area       : [{room_to_stat.area_id}] {area_name}")
    output.append(f" Description: {room_to_stat.description}")
    output.append(f" Flags      : {sorted(list(room_to_stat.flags))}")
    output.append(f" Exits      : {json.dumps(room_to_stat.exits)}") # Show raw JSON for exits
    output.append(f" Spawners   : {json.dumps(room_to_stat.spawners)}") # Show raw JSON for spawners
    output.append(f" Coinage    : {room_to_stat.coinage}")
    # Items requires template lookup
    item_names = []
    for item_tid in room_to_stat.items:
        template = utils.get_item_template_from_world(world, item_tid)
        item_names.append(template['name'] if template else f"Item#{item_tid}")
    output.append(f" Items      : {item_names if item_names else 'None'}")
    # Objects requires name lookup
    object_names = [obj.get('name', 'Unknown') for obj in room_to_stat.objects]
    output.append(f" Objects    : {object_names if object_names else 'None'}")
    output.append("------------------------------------------")

    await character.send("\r\n".join(output))
    return True

async def cmd_roomlist(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Admin command: Lists rooms, optionally filtered by area ID."""

    target_area_id = None
    if args_str and args_str.isdigit():
        target_area_id = int(args_str)
        area_name = world.get_area_name(target_area_id)
        if not area_name: await character.send(f"Area ID {target_area_id} not found."); return True
        header = f"--- Rooms in Area [{target_area_id}] {area_name} ---"
        room_data = await database.get_rooms_in_area(db_conn, target_area_id)
    else:
        header = "--- All Rooms ---"
        room_data = await database.get_all_rooms_basic(db_conn) # Gets ID, Name, AreaID, AreaName

    if room_data is None:
        await character.send("Error retrieving room list from database.")
        return True
    if not room_data:
        await character.send("No rooms found" + (f" in area {target_area_id}." if target_area_id else "."))
        return True

    output = [header]
    for row in room_data:
        area_display = f" (Area: {row['area_name']})" if 'area_name' in row.keys() else "" # Only show if from all rooms
        output.append(f" [{row['id']: >4}] {row['name']}{area_display}")
    output.append("-------------------------")

    await character.send("\r\n".join(output))
    return True

async def cmd_setdesc(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Admin command: Sets the description for the current room."""
    if not character.location: await character.send("You aren't in a room."); return True
    if not args_str: await character.send("Usage: @setdesc <new room description>"); return True

    new_desc = args_str.strip()
    room_id = character.location.dbid

    success = await database.update_room_basic(db_conn, room_id, "description", new_desc)
    if success:
        character.location.description = new_desc # Update in-memory object
        await character.send("Room description updated.")
    else:
        await character.send("Failed to update room description in database.")
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
                    output += f" Desc: {target_mob.description}\r\n"
                    output += f" Type: {getattr(target_mob, 'mob_type', 'N/A')}\r\n" # Use getattr for safety
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

async def cmd_dig(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Admin command: Creates a new room and links exits. Usage: @dig <direction> <New Room Name>"""
    if not character.location: await character.send("You must be in a room to dig."); return True

    parts = args_str.split(" ", 1)
    if len(parts) < 2:
        await character.send("Usage: @dig <direction> <New Room Name>")
        return True

    direction = parts[0].lower()
    new_room_name = parts[1].strip().title()
    current_room = character.location

    # Validate direction
    if direction not in utils.VALID_DIRECTIONS: # Assume utils.VALID_DIRECTIONS exists
        await character.send(f"Invalid direction '{direction}'. Use north, south, etc."); return True
    if direction in current_room.exits:
        await character.send(f"An exit already exists to the {direction}. Use @delexit first."); return True
    reverse_dir = utils.get_opposite_direction(direction) # Assume utils.get_reverse_exit exists
    if not reverse_dir:
        await character.send(f"Cannot determine reverse direction for {direction}."); return True # Should not happen

    # Create new room in DB
    new_room_id = await database.create_room(db_conn, current_room.area_id, new_room_name, f"An empty room dug by {character.name}.")
    if not new_room_id:
        await character.send("Failed to create new room in database!"); return True

    # Create new room object in memory
    # Fetch full data to initialize Room object correctly
    new_room_data = await database.get_room_data(db_conn, new_room_id)
    if not new_room_data:
        log.error("Failed to fetch newly created room %d data!", new_room_id); await character.send("Error loading new room."); return True
    new_room = Room(new_room_data) # Create Room object
    world.rooms[new_room_id] = new_room # Add to world cache
    log.info("Admin %s created Room %d ('%s') in Area %d", character.name, new_room_id, new_room_name, current_room.area_id)

    # Link exits (DB and Memory)
    # Current room -> New room
    current_room.exits[direction] = new_room_id
    await database.update_room_json_field(db_conn, current_room.dbid, "exits", json.dumps(current_room.exits))
    await character.send(f"Exit {direction} added to current room -> [{new_room_id}]")

    # New room -> Current room
    new_room.exits[reverse_dir] = current_room.dbid
    await database.update_room_json_field(db_conn, new_room_id, "exits", json.dumps(new_room.exits))
    await character.send(f"Reverse exit {reverse_dir} added to new room [{new_room_id}] -> [{current_room.dbid}]")

    # Teleport builder to new room
    await character.send("Digging complete! Moving you to the new room...")
    await cmd_teleport(character, world, db_conn, str(new_room_id)) # Reuse teleport logic

    return True

async def cmd_setexit(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Admin command: Creates/modifies an exit. Usage: @setexit <dir> <target_id> [skill <name> dc <val> ...]"""
    if not character.location: await character.send("You aren't in a room."); return True
    if not args_str: await character.send("Usage: @setexit <direction> <target_room_id> [options]"); return True

    parts = args_str.split()
    direction = parts[0].lower()
    if direction not in utils.VALID_DIRECTIONS: await character.send("Invalid direction."); return True

    if len(parts) < 2 or not parts[1].isdigit(): await character.send("Usage: @setexit <direction> <target_room_id> ..."); return True
    target_room_id = int(parts[1])
    target_room = world.get_room(target_room_id)
    if not target_room: await character.send(f"Target room ID {target_room_id} does not exist."); return True

    # --- Parse options for skill check ---
    exit_data: Union[int, Dict] = target_room_id # Default to simple exit
    skill_check_data = {}
    try:
        if "skill" in args_str.lower():
            skill_index = parts.index("skill")
            if skill_index + 3 <= len(parts) and parts[skill_index+2].lower() == "dc" and parts[skill_index+3].isdigit():
                skill_check_data["skill"] = parts[skill_index+1].lower()
                skill_check_data["dc"] = int(parts[skill_index+3])
                # Optional fail damage/messages
                if "fail_dmg" in parts: dmg_idx=parts.index("fail_dmg"); skill_check_data["fail_damage"] = int(parts[dmg_idx+1])
                if "fail_msg" in parts: msg_idx=parts.index("fail_msg"); skill_check_data["fail_msg"] = " ".join(parts[msg_idx+1:]) # Simple join rest
                # Add success_msg parsing similarly
                exit_data = {"target": target_room_id, "skill_check": skill_check_data}
                await character.send("Complex exit created/updated.")
            else: await character.send("Invalid skill check syntax. Use: skill <name> dc <number> [options]"); return True
    except (ValueError, IndexError): await character.send("Error parsing skill check options."); return True

    # Update current room exits
    current_room = character.location
    current_room.exits[direction] = exit_data
    success = await database.update_room_json_field(db_conn, current_room.dbid, "exits", json.dumps(current_room.exits))

    if not success: await character.send("Failed to update exit in database!"); return True

    # --- Link Back ---
    reverse_dir = utils.get_opposite_direction(direction)
    if reverse_dir:
        try:
            target_exits = json.loads(target_room.exits_str or '{}') # Reload from DB string maybe? Use memory for now.
            target_exits = target_room.exits.copy()
            # Simple reverse link for now, don't copy skill check back automatically
            target_exits[reverse_dir] = current_room.dbid
            target_room.exits = target_exits # Update memory
            await database.update_room_json_field(db_conn, target_room_id, "exits", json.dumps(target_exits)) # Update DB
            await character.send(f"Exit {direction} -> {target_room_id} set. Reverse link {reverse_dir} -> {current_room.dbid} added/updated.")
        except Exception as e:
            log.error("Failed to set reverse exit %s in room %d: %s", reverse_dir, target_room_id, e)
            await character.send(f"Exit {direction} set, but failed to set reverse link in room {target_room_id}.")
    else: await character.send(f"Exit {direction} set. Could not determine reverse direction.")

    return True

async def cmd_delexit(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Admin command: Deletes an exit from the current room and optionally the reverse."""
    if not character.location: await character.send("You aren't in a room."); return True
    direction = args_str.strip().lower()
    if not direction: await character.send("Usage: @delexit <direction>"); return True

    current_room = character.location
    if direction not in current_room.exits:
        await character.send(f"No exit found in direction '{direction}'."); return True

    exit_data = current_room.exits[direction]
    target_room_id = exit_data if isinstance(exit_data, int) else exit_data.get('target')

    # Remove exit from current room
    del current_room.exits[direction]
    success = await database.update_room_json_field(db_conn, current_room.dbid, "exits", json.dumps(current_room.exits))
    if not success: await character.send(f"Failed to remove exit {direction} from database!"); return True

    await character.send(f"Exit '{direction}' removed.")

    # --- Unlink Back ---
    reverse_dir = utils.get_opposite_direction(direction)
    if reverse_dir and target_room_id:
        target_room = world.get_room(target_room_id)
        if target_room and reverse_dir in target_room.exits and target_room.exits[reverse_dir] == current_room.dbid:
            del target_room.exits[reverse_dir]
            await database.update_room_json_field(db_conn, target_room_id, "exits", json.dumps(target_room.exits))
            await character.send(f"Reverse exit '{reverse_dir}' removed from room {target_room_id}.")
        elif target_room and reverse_dir in target_room.exits:
            await character.send(f"Note: Reverse exit '{reverse_dir}' in room {target_room_id} did not point back here.")
        elif target_room:
            await character.send(f"Note: Reverse exit '{reverse_dir}' not found in room {target_room_id}.")

    return True

async def cmd_tunnel_placeholder(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """@tunnel ...: Placeholder for exit creation."""
    log.info("Admin %s used @tunnel command (placeholder). Args: %s", character.name, args_str)
    await character.send("Exit tunneling not implemented yet.")
    return True

async def cmd_roomset(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Admin Command: Sets properties of the current room.
    Usage: @roomset <name|description|area_id|flags> <value>
        @roomset flags <+|-><FLAG_NAME>
    """
    if not character.location:
        await character.send("You are not currently in a room.")
        return True

    current_room = character.location
    parts = args_str.split(" ", 1) # Split field from value

    if len(parts) < 2:
        await character.send("Usage: @roomset <field> <value>")
        await character.send("Fields: name, description, area_id, flags")
        return True

    field = parts[0].lower()
    value_str = parts[1].strip()

    if not value_str:
        await character.send(f"You must provide a value for field '{field}'.")
        return True

    updated = False
    rowcount = None

    # --- Handle different fields ---
    if field == "name":
        # TODO: Add validation for name length/characters?
        current_room.name = value_str # Update memory
        rowcount = await database.update_room_field(db_conn, current_room.dbid, "name", value_str)
        if rowcount == 1: updated = True

    elif field == "description":
        current_room.description = value_str # Update memory
        rowcount = await database.update_room_field(db_conn, current_room.dbid, "description", value_str)
        if rowcount == 1: updated = True

    elif field == "area_id":
        try:
            new_area_id = int(value_str)
            # Check if target area exists
            target_area_data = world.get_area(new_area_id) # Check cache
            log.info("Attempting to set room %d area to %d. Target area exists: %s",
                    current_room.dbid, new_area_id, bool(target_area_data))

            if world.get_area(new_area_id):
                current_room.area_id = new_area_id # Update memory
                rowcount = await database.update_room_field(db_conn, current_room.dbid, "area_id", new_area_id)
                if rowcount == 1: updated = True
            else:
                await character.send(f"Area ID {new_area_id} does not exist.")
                return True
        except ValueError:
            await character.send("{rInvalid Area ID. Must be a number.{x")
            return True

    elif field == "flags":
        if not (value_str.startswith('+') or value_str.startswith('-')):
            await character.send("Usage: @roomset flags <+|-><FLAG_NAME>")
            return True

        action = value_str[0]
        flag_name = value_str[1:].strip().upper() # Get flag name, uppercase

        if flag_name not in VALID_ROOM_FLAGS:
            await character.send(f"Invalid flag '{flag_name}'. Valid flags are: {', '.join(VALID_ROOM_FLAGS)}")
            return True

        if action == '+':
            if flag_name in current_room.flags:
                await character.send(f"Room already has flag '{flag_name}'.")
                return True
            current_room.flags.add(flag_name) # Update memory
            await character.send(f"Flag '{flag_name}' added.")
            updated = True
        else: # action == '-'
            if flag_name not in current_room.flags:
                await character.send(f"Room does not have flag '{flag_name}'.")
                return True
            current_room.flags.discard(flag_name) # Update memory
            await character.send(f"Flag '{flag_name}' removed.")
            updated = True

        # If updated, save the new flags set to the DB
        if updated:
            flags_json = json.dumps(sorted(list(current_room.flags)))
            rowcount = await database.update_room_field(db_conn, current_room.dbid, "flags", flags_json)
            if rowcount != 1: updated = False # DB save failed

    else:
        await character.send(f"Invalid field '{field}'. Valid fields: name, description, area_id, flags.")
        return True

    # --- Send final feedback ---
    if updated:
        await character.send(f"Room {current_room.dbid} field '{field}' updated successfully.")
    else:
        await character.send(f"Failed to update room field '{field}' (check logs).")

    return True

async def cmd_roomdelete(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Admin Command: Deletes a room after safety checks. Usage: @roomdelete <room_id>"""
    if not args_str.strip().isdigit():
        await character.send("Usage: @roomdelete <room_id_to_delete>")
        return True

    try:
        room_id_to_delete = int(args_str.strip())
    except ValueError:
        await character.send("{rInvalid Room ID.{x")
        return True

    # --- Safety Checks ---
    if room_id_to_delete == 1: # Default Void/Start Room
        await character.send("{rCannot delete the default Void room (ID 1).{x")
        return True

    target_room = world.get_room(room_id_to_delete) # Check in-memory first
    if not target_room:
        # Verify it doesn't exist in DB either before confirming deletion
        db_room = await database.get_room_data(db_conn, room_id_to_delete)
        if not db_room:
            await character.send(f"Room ID {room_id_to_delete} does not exist.")
            return True
        else: # Exists in DB but not memory - potentially problematic, warn user
            await character.send(f"yWarning: Room {room_id_to_delete} exists in DB but not loaded in world memory.")
            # Allow deletion attempt anyway? Let's proceed but be careful.
            target_room = Room(dict(db_room)) # Create temp object for checks

    if target_room.characters:
        await character.send(f"Cannot delete Room {room_id_to_delete}: Contains players!")
        return True
    if target_room.mobs:
        await character.send(f"Cannot delete Room {room_id_to_delete}: Contains mobs! Use @purge first?")
        return True
    # Check items/coins by querying DB directly as cache might be out of date
    items = await database.load_items_for_room(db_conn, room_id_to_delete)
    coins = await database.load_coinage_for_room(db_conn, room_id_to_delete)
    if items or (coins is not None and coins > 0):
        await character.send(f"Cannot delete Room {room_id_to_delete}: Contains items or coins! Use @purge first?")
        return True
    objects = await database.load_objects_for_room(db_conn, room_id_to_delete)
    if objects:
        await character.send(f"Cannot delete Room {room_id_to_delete}: Contains room objects! Use @odelete first.")
        return True

    # Check for incoming exits (expensive check, iterate all rooms)
    incoming_exits_found = []
    for room_id, room in world.rooms.items():
        if room_id == room_id_to_delete: continue # Skip self
        for direction, exit_target_data in room.exits.items():
            exit_target_id = None
            if isinstance(exit_target_data, int): exit_target_id = exit_target_data
            elif isinstance(exit_target_data, dict): exit_target_id = exit_target_data.get('target')

            if exit_target_id == room_id_to_delete:
                incoming_exits_found.append(f"Room {room_id} ('{room.name}') -> {direction}")

    if incoming_exits_found:
        await character.send(f"Cannot delete Room {room_id_to_delete}. The following exits point TO it:")
        for exit_info in incoming_exits_found: await character.send(f" - {exit_info}")
        await character.send("Please use @delexit in those rooms first.")
        return True

    # --- All safety checks passed, proceed with deletion ---
    log.warning("ADMIN ACTION: %s attempting to delete Room ID %d ('%s')",
                character.name, room_id_to_delete, target_room.name)

    rowcount = await database.delete_room(db_conn, room_id_to_delete)

    if rowcount == 1:
        # Remove from world cache
        if room_id_to_delete in world.rooms:
            del world.rooms[room_id_to_delete]
        await character.send(f"Room ID {room_id_to_delete} ('{target_room.name}') deleted successfully.")
    elif rowcount == 0: # Should not happen if load worked
        await character.send(f"Failed to delete Room ID {room_id_to_delete} (not found during delete).")
    else: # None or other error
        await character.send("{rDatabase error deleting room.{x")

    return True

#---Area creation---
async def cmd_areacreate(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Admin Command: Creates a new area."""
    area_name_input = args_str.strip().title()
    if not area_name_input:
        await character.send("Usage: @areacreate <New Area Name>")
        return True

    area_name = area_name_input.title() # Apply capitalization here

    new_area_row = await database.create_area(db_conn, area_name) # Get the full row back

    if new_area_row:
        new_id = new_area_row['id']
        # --- V V V Update World Cache V V V ---
        world.areas[new_id] = dict(new_area_row) # Add new area to in-memory dict
        log.info("Added new area %d ('%s') to world cache.", new_id, area_name)
        # --- ^ ^ ^ ---
        await character.send(f"Area '{area_name}' created with ID {new_id}.")
    else:
        await character.send("{rFailed to create area (check logs, maybe name exists?).{x")
    return True

async def cmd_arealist(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Admin Command: Lists all areas."""
    areas = await database.load_all_areas(db_conn)
    if areas is None:
        await character.send("{rError fetching areas from database.{x")
        return True
    if not areas:
        await character.send("No areas found.")
        return True

    output = ["\r\n--- Areas ---"]
    for area_row in areas:
        output.append(f" [{area_row['id']: >3}] {area_row['name']}")
    output.append("-------------")
    await character.send("\r\n".join(output))
    return True

async def cmd_areaset(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Admin Command: Sets properties of an area. Usage: @areaset <id> <name|description> <value>"""
    parts = args_str.split(" ", 2)
    if len(parts) < 3:
        await character.send("Usage: @areaset <area_id> <name|description> <new value>")
        return True

    try:
        area_id = int(parts[0])
    except ValueError:
        await character.send("{rInvalid Area ID.{x")
        return True

    field = parts[1].lower()
    value = parts[2].strip()

    if field not in ["name", "description"]:
        await character.send("{rInvalid field. Can only set 'name' or 'description'.{x")
        return True
    if not value:
        await character.send(f"Cannot set {field} to an empty value.")
        return True

    # TODO: Add validation for value length?

    rowcount = await database.update_area_field(db_conn, area_id, field, value)
    if rowcount is not None and rowcount > 0:
        await character.send(f"Area ID {area_id} {field} updated.")
        # TODO: Update in-memory world.areas cache if needed
    elif rowcount == 0:
        await character.send(f"rArea ID {area_id} not found.")
    else:
        await character.send("{rDatabase error updating area.{x")
    return True

async def cmd_areainfo(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Admin Command: Shows details for an area. Usage: @areainfo [area_id]"""
    area_id_to_show = None
    if args_str.strip().isdigit():
        area_id_to_show = int(args_str.strip())
    elif not args_str.strip():
        if character.location:
            area_id_to_show = character.location.area_id
        else:
            await character.send("You are not in a location to check area info.")
            return True
    else:
        await character.send("Usage: @areainfo [area_id]")
        return True

    if area_id_to_show is None: # Should only happen if location was None
        await character.send("Could not determine area ID.")
        return True

    area_data = await database.load_area_data(db_conn, area_id_to_show)
    if not area_data:
        await character.send(f"Area ID {area_id_to_show} not found.")
        return True

    output = [f"\r\n--- Area Info [ID: {area_data['id']}] ---"]
    output.append(f"Name       : {area_data['name']}")
    output.append(f"Description: {area_data['description']}")
    output.append(f"Created At : {area_data['created_at']}")
    output.append("-----------------------------")
    await character.send("\r\n".join(output))
    return True

async def cmd_areadelete(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Admin Command: Deletes an area IF IT CONTAINS NO ROOMS."""
    if not args_str.strip().isdigit():
        await character.send("Usage: @areadelete <area_id>")
        return True

    area_id_to_delete = int(args_str.strip())

    # Check if area exists and if it's empty
    area_data = await database.load_area_data(db_conn, area_id_to_delete)
    if not area_data:
        await character.send(f"Area ID {area_id_to_delete} not found.")
        return True

    room_count = await database.get_room_count_for_area(db_conn, area_id_to_delete)
    if room_count > 0:
        await character.send(f"rCannot delete Area ID {area_id_to_delete} ('{area_data['name']}'). It still contains {room_count} rooms!")
        return True

    # Area exists and is empty, proceed with deletion
    rowcount = await database.delete_area(db_conn, area_id_to_delete)
    if rowcount == 1:
        await character.send(f"Area ID {area_id_to_delete} ('{area_data['name']}') deleted.")
        # TODO: Remove from world.areas cache?
    elif rowcount == 0: # Should not happen if load_area_data worked
        await character.send(f"Failed to delete Area ID {area_id_to_delete} (not found during delete).")
    else: # None or other error
        await character.send("{rDatabase error deleting area.{x")

    return True

#---Item creation---
async def cmd_icreate(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Admin Command: Creates a basic item template.
    Usage: @icreate <Name> <Type> <Description>
    Example: @icreate "a basic helm" ARMOR "A simple metal helmet."
    Use @iset to add stats, flags, etc.
    """
    parts = args_str.split(" ", 2) # Split into name, type, description
    if len(parts) < 3:
        await character.send("Usage: @icreate <Name> <Type> <Description>")
        await character.send("Types: WEAPON, ARMOR, SHIELD, CONTAINER, CONSUMABLE, FOOD, DRINK, TOOL, KEY, LIGHT, REAGENT, TREASURE, GENERAL, AMMO")
        return True

    name, item_type, description = parts[0].strip(), parts[1].strip().upper(), parts[2].strip()

    if not name or not item_type or not description:
        await character.send("Name, Type, and Description cannot be empty.")
        return True

    # Basic type validation (can be expanded)
    valid_types = {"WEAPON", "ARMOR", "SHIELD", "CONTAINER", "CONSUMABLE", "FOOD", "DRINK", "TOOL", "KEY", "LIGHT", "REAGENT", "TREASURE", "GENERAL", "AMMO"}
    if item_type not in valid_types:
        await character.send(f"Invalid item type '{item_type}'. Valid types are: {', '.join(valid_types)}")
        return True

    new_item_row = await database.create_item_template(db_conn, name, item_type, description)

    if new_item_row:
        new_id = new_item_row['id']
        # Add to world cache immediately
        world.item_templates[new_id] = dict(new_item_row) # Store as dict
        await character.send(f"Item Template '{name}' created with ID {new_id}.")
        await character.send("Use {y@iset{x to add stats, flags, etc.")
    else:
        await character.send("{rFailed to create item template (check logs, maybe name exists?).{x")
    return True

async def cmd_ilist(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Admin Command: Lists item templates. Usage: @ilist [search_term]"""
    search_term = args_str.strip() if args_str else None
    templates = await database.load_all_item_templates(db_conn, search_term) # Use modified loader

    if templates is None: await character.send("{rError fetching item templates.{x"); return True
    if not templates: await character.send("No matching item templates found."); return True

    output = ["\r\n--- Item Templates ---"]
    for tpl in templates:
        output.append(f" [{tpl['id']: >3}] {tpl['name']} ({tpl['type']})")
    output.append("--------------------")
    await character.send("\r\n".join(output))
    return True

async def cmd_istat(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Admin Command: Shows details for an item template. Usage: @istat <template_id>"""
    if not args_str.strip().isdigit():
        await character.send("Usage: @istat <template_id>")
        return True
    template_id = int(args_str.strip())

    template = world.get_item_template(template_id) # Check cache first
    if not template:
        template_row = await database.load_item_template(db_conn, template_id) # Try DB
        if template_row: template = dict(template_row) # Convert row

    if not template:
        await character.send(f"Item Template ID {template_id} not found.")
        return True

    output = [f"\r\n--- Item Template [ID: {template['id']}] ---"]
    output.append(f"Name       : {template.get('name', 'N/A')}")
    output.append(f"Type       : {template.get('type', 'N/A')}")
    output.append(f"Damage Type: {template.get('damage_type', 'N/A')}")
    output.append(f"Description: {template.get('description', '')}")
    output.append(f"Stats JSON : {template.get('stats', '{}')}")
    output.append(f"Flags JSON : {template.get('flags', '[]')}")
    output.append("-------------------------------")
    await character.send("\r\n".join(output))
    return True

async def cmd_iset(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Admin Command: Sets properties of an item template.
    Usage: @iset <template_id> <field> <value>
    Fields: name, description, type, stats, flags, damage_type
    Note: For stats/flags, value MUST be valid JSON string.
    Example: @iset 10 stats '{{\"value\": 50, \"weight\": 2}}'
            @iset 10 flags '[\"MAGICAL\"]'
    """
    parts = args_str.split(" ", 2)
    if len(parts) < 3:
        await character.send("Usage: @iset <template_id> <field> <value>")
        await character.send("Fields: name, description, type, stats, flags, damage_type")
        await character.send("Note: 'stats' value must be valid JSON like '{\"key\": val}'")
        await character.send("Note: 'flags' value must be valid JSON like '[\"FLAG\"]'")
        return True

    try:
        template_id = int(parts[0])
    except ValueError: await character.send("{rInvalid Template ID.{x"); return True

    field = parts[1].lower()
    value = parts[2].strip() # Keep value as string for now

    valid_fields = ["name", "description", "type", "stats", "flags", "damage_type"]
    if field not in valid_fields:
        await character.send(f"Invalid field '{field}'. Valid: {', '.join(valid_fields)}")
        return True
    if not value and field not in ['damage_type']: # Allow empty damage_type to clear it
        await character.send(f"Cannot set {field} to an empty value.")
        return True
    if field == 'damage_type' and not value:
        value = None # Set damage type to NULL

    # Special validation for JSON fields
    if field in ["stats", "flags"]:
        try:
            json.loads(value) # Validate JSON structure
            if field == "stats" and not isinstance(json.loads(value), dict): raise TypeError("Stats must be a JSON object {{}}")
            if field == "flags" and not isinstance(json.loads(value), list): raise TypeError("Flags must be a JSON list []")
        except (json.JSONDecodeError, TypeError) as e:
            await character.send(f"Invalid JSON format for {field}: {e}")
            return True

    updated_row = await database.update_item_template_field(db_conn, template_id, field, value)

    if updated_row:
        world.item_templates[template_id] = dict(updated_row) # Update cache
        await character.send(f"Item Template {template_id} field '{field}' updated.")
    else:
        await character.send(f"Failed to update Item Template {template_id} (not found or DB error).")
    return True

async def cmd_icopy(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Admin Command: Copies an item template. Usage: @icopy <source_id> <New Name>"""
    parts = args_str.split(" ", 1)
    if len(parts) < 2 or not parts[0].isdigit():
        await character.send("Usage: @icopy <source_template_id> <New Item Name>")
        return True

    source_id = int(parts[0])
    new_name = parts[1].strip()

    if not new_name:
        await character.send("You must provide a new name for the copied item.")
        return True

    new_item_row = await database.copy_item_template(db_conn, source_id, new_name)

    if new_item_row:
        new_id = new_item_row['id']
        world.item_templates[new_id] = dict(new_item_row) # Add to cache
        await character.send(f"Item Template {source_id} copied to new template '{new_name}' (ID: {new_id}).")
    else:
        await character.send(f"Failed to copy Item Template {source_id} (not found or DB error).")
    return True

async def cmd_idelete(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Admin Command: Deletes an item template. Usage: @idelete <template_id>"""
    if not args_str.strip().isdigit():
        await character.send("Usage: @idelete <template_id>")
        return True
    template_id = int(args_str.strip())

    # Check if template exists (optional, delete will just return 0 if not)
    template = world.get_item_template(template_id) # Check cache
    if not template: template = await database.load_item_template(db_conn, template_id)
    if not template: await character.send(f"Item Template ID {template_id} not found."); return True

    # Warning!
    await character.send(f"WARNING: Deleting Item Template {template_id} ('{template['name']}') cannot be undone!")
    await character.send("{rThis does NOT currently check if items exist in rooms, inventories, or loot tables!{x")
    await character.send(f"Type '@idelete {template_id} confirm' to proceed.")
    # Add confirmation step later - for now, just delete directly after warning for simplicity
    # Need handler state for confirmation. Let's skip confirm for V1 builder tools.

    log.warning("ADMIN ACTION: %s attempting to delete Item Template ID %d ('%s'). Usage checks skipped!",
                character.name, template_id, template['name'])

    rowcount = await database.delete_item_template(db_conn, template_id)

    if rowcount == 1:
        # Remove from world cache
        if template_id in world.item_templates:
            del world.item_templates[template_id]
        await character.send(f"Item Template {template_id} ('{template['name']}') deleted.")
    elif rowcount == 0:
        await character.send(f"Failed to delete Item Template {template_id} (already gone?).")
    else: # None or other error
        await character.send("{rDatabase error deleting item template.{x")

    return True
#---Mob creation---
async def cmd_mcreate(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Admin Command: Creates a basic mob template.
    Usage: @mcreate <Name> [Level] [Description]
    Example: @mcreate "Cave Bat" 2 "A fluttering menace."
    Use @mset to configure stats, attacks, loot, etc.
    """
    parts = args_str.split(" ", 2)
    name = parts[0].strip().title() if len(parts) > 0 else None
    level = 1
    description = "A creature."

    if not name:
        await character.send("Usage: #@mcreate <Name> [Level] [Description]")
        return True
    
    if len(parts) > 1 and parts[1].isdigit():
        level = int(parts[1])
        if len(parts) > 2: description = parts[2].strip()
    elif len(parts) > 1: # assume level wasn't specified, second part is in desc
        description = parts[1].strip()

    level = max(1, level) # Ensure level is at least 1

    new_mob_row = await database.create_mob_template(db_conn, name, level, description)
    if new_mob_row:
        new_id = new_mob_row['id']
        # Add/Update world cache
        world.mob_templates[new_id] = dict(new_mob_row)
        await character.send(f"Mob Template '{name}' created with Id {new_id}.")
        await character.send("Use @mset to configure details (stats, attacks, loot, flags, etc).")
    else:
        await character.send("Failed to create mob template (check logs, maybe name exists?).")
    return True

async def cmd_mlist(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Admin Command: Lists mob templates. Usage: @mlist [search_term]"""
    search_term = args_str.strip() if args_str else None
    templates = await database.get_mob_templates(db_conn, search_term)
    if templates is None: await character.send("Error fetching mob templates."); return True
    if not templates: await character.send("No matching mob templates found."); return True

    output = ["\r\n--- Mob Templates ---"]
    for tpl in templates:
        output.append(f" [{tpl['id']: >3}] {tpl['name']} (Lvl {tpl['level']})")
    output.append("-------------------")
    await character.send("\r\n".join(output))
    return True

async def cmd_mstat(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Admin Command: Shows details for a mob template. Usage: @mstart <template_id>"""
    if not args_str.strip().isdigit(): await character.send("Usage: @mstart <template_id>"); return True
    template_id = int(args_str.strip())

    template = world.get_mob_template(template_id) # Check cache first
    if not template: template = await database.load_mob_template(db_conn, template_id) # Try DB
    if not template: await character.send(f"Mob Template ID {template_id} not found."); return True

    # Convert Row to dict if needed for consistent access
    if not isinstance(template, dict): template = dict(template)

    output = [f"\r\n--- Mob Template [ID: {template['id']}] ---"]
    output.append(f"Name       : {template.get('name', 'N/A')}")
    output.append(f"Level      : {template.get('level', '?')}")
    output.append(f"Mob Type   : {template.get('mob_type', 'None')}")
    output.append(f"Max HP     : {template.get('max_hp', '?')}")
    output.append(f"Respawn(s) : {template.get('respawn_delay_seconds', '?')}")
    output.append(f"Move %     : {template.get('movement_chance', 0.0):.1%}")
    output.append(f"Description: {template.get('description', '')}")
    output.append(f"Stats JSON : {template.get('stats', '{}')}")
    output.append(f"AttacksJSON: {template.get('attacks', '[]')}")
    output.append(f"Loot JSON  : {template.get('loot', '{}')}")
    output.append(f"Flags JSON : {template.get('flags', '[]')}")
    output.append(f"VarianceJSN: {template.get('variance', '{}')}")
    output.append("-----------------------------")
    await character.send("\r\n".join(output))
    return True

async def cmd_mset(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Admin Command: Sets properties of a mob template.
    Usage: @mset <template_id> <field> <value>
    Fields: name, description, mob_type, level, max_hp, respawn_delay_seconds,
            movement_chance, stats, attacks, loot, flags, variance
    Note: JSON fields (stats, attacks, loot, flags, variance) require valid JSON string values.
    Example: @mset 1 stats '{\"might\": 12, \"vitality\": 15}'
            @mset 1 flags '[\"AGGRESSIVE\", \"SENTINEL\"]'
    """
    parts = args_str.split(" ", 2)
    if len(parts) < 3:
        await character.send("Usage: @mset <template_id> <field> <value>")
        await character.send("Fields: name, description, mob_type, level, max_hp, respawn_delay_seconds, movement_chance, stats, attacks, loot, flags, variance")
        await character.send("Note: JSON fields need valid JSON string: '{\"key\": val}', '[\"val\"]'")
        return True

    try: template_id = int(parts[0])
    except ValueError: await character.send("{rInvalid Template ID.{x"); return True

    field = parts[1].lower()
    value = parts[2].strip() # Keep as string for now, DB helper handles conversion

    valid_fields = [ # List from DB helper
        "name", "description", "mob_type", "level", "stats", "max_hp",
        "attacks", "loot", "flags", "respawn_delay_seconds", "variance",
        "movement_chance"
    ]
    if field not in valid_fields:
        await character.send(f"Invalid field '{field}'. Valid: {', '.join(valid_fields)}")
        return True
    if not value:
        await character.send(f"Cannot set {field} to an empty value.")
        return True

    updated_row = await database.update_mob_template_field(db_conn, template_id, field, value)

    if updated_row:
        # Update world cache
        world.mob_templates[template_id] = dict(updated_row)
        await character.send(f"Mob Template {template_id} field '{field}' updated.")
        await character.send("{yNote: Changes to stats/attacks affect newly spawned mobs.{x")
    else:
        await character.send(f"Failed to update Mob Template {template_id} (not found or DB error/invalid value).")
    return True

async def cmd_mcopy(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Admin Command: Copies a mob template. Usage: @mcopy <source_id> <New Name>"""
    parts = args_str.split(" ", 1)
    if len(parts) < 2 or not parts[0].isdigit():
        await character.send("Usage: @mcopy <source_template_id> <New Mob Name>")
        return True

    source_id = int(parts[0])
    new_name = parts[1].strip().title() # Capitalize new name

    if not new_name:
        await character.send("You must provide a new name for the copied mob.")
        return True

    new_mob_row = await database.copy_mob_template(db_conn, source_id, new_name)

    if new_mob_row:
        new_id = new_mob_row['id']
        world.mob_templates[new_id] = dict(new_mob_row) # Add to cache
        await character.send(f"Mob Template {source_id} copied to new template '{new_name}' (ID: {new_id}).")
    else:
        await character.send(f"Failed to copy Mob Template {source_id} (not found or DB error).")
    return True

async def cmd_mdelete(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Admin Command: Deletes a mob template. Usage: @mdelete <template_id>"""
    if not args_str.strip().isdigit(): await character.send("Usage: @mdelete <template_id>"); return True
    template_id = int(args_str.strip())

    # Check if template exists (optional check)
    template = world.get_mob_template(template_id)
    if not template: template = await database.load_mob_template(db_conn, template_id)
    if not template: await character.send(f"Mob Template ID {template_id} not found."); return True

    template_name = template['name'] # Get name for messages before deleting

    # Warning!
    await character.send(f"WARNING: Deleting Mob Template {template_id} ('{template_name}')!")
    await character.send("{rThis does NOT currently check if spawners use this template! Doing so may cause errors.{x")
    # Add confirmation step later
    # await character.send(f"Type '@mdelete {template_id} confirm' to proceed.")
    # return True

    log.warning("ADMIN ACTION: %s attempting to delete Mob Template ID %d ('%s'). Spawner usage check skipped!",
                character.name, template_id, template_name)

    rowcount = await database.delete_mob_template(db_conn, template_id)

    if rowcount == 1:
        if template_id in world.mob_templates: del world.mob_templates[template_id] # Remove from cache
        await character.send(f"Mob Template {template_id} ('{template_name}') deleted.")
    elif rowcount == 0: await character.send(f"Failed to delete Mob Template {template_id} (already gone?).")
    else: await character.send("{rDatabase error deleting mob template.{x")

    return True