# game/commands/admin.py
"""
Admin-only commands for server management and testing.
All command functions must be async and accept (character, world, db_conn, args_str).
Command verbs should start with '@'.
"""
import asyncio
import logging
from typing import TYPE_CHECKING, Optional, Dict, Any, List, Set, Union
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

# --- Admin Command Functions ---

def _check_admin(character: 'Character') -> bool:
    """Helper to check admin status and send feedback."""
    if not character.is_admin:
        asyncio.create_task(character.send("You do not have permission to use this command."))
        return False
    return True

async def cmd_teleport(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Admin command: Teleports the admin to a specified room ID."""
    if not _check_admin(character): return True
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

    await character.send(f"{{YTeleporting to Room {target_room_id}...{{x")

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
    if not _check_admin(character): return True

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
    if not _check_admin(character): return True

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
    if not _check_admin(character): return True
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
    if not _check_admin(character): return True
    if not character.location: await character.send("You must be in a room to dig."); return True

    parts = args_str.split(" ", 1)
    if len(parts) < 2:
        await character.send("Usage: @dig <direction> <New Room Name>")
        return True

    direction = parts[0].lower()
    new_room_name = parts[1].strip()
    current_room = character.location

    # Validate direction
    if direction not in utils.VALID_DIRECTIONS: # Assume utils.VALID_DIRECTIONS exists
        await character.send(f"Invalid direction '{direction}'. Use north, south, etc."); return True
    if direction in current_room.exits:
        await character.send(f"An exit already exists to the {direction}. Use @delexit first."); return True
    reverse_dir = utils.get_reverse_exit(direction) # Assume utils.get_reverse_exit exists
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
    if not _check_admin(character): return True
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
    reverse_dir = utils.get_reverse_exit(direction)
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
    if not _check_admin(character): return True
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
    reverse_dir = utils.get_reverse_exit(direction)
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