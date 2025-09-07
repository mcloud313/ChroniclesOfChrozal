# game/commands/admin.py
"""
Admin-only commands for in-game debugging and server management.
World-building commands are handled by a separate GUI tool.
"""
import logging
import json
from typing import TYPE_CHECKING, Optional

from .. import database
from .. import utils
from ..room import Room

if TYPE_CHECKING:
    from ..character import Character
    from ..world import World
    import aiosqlite

log = logging.getLogger(__name__)


async def cmd_teleport(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Admin: Teleports the admin to a specified room ID. Usage: @teleport <room_id>"""
    if not args_str.isdigit():
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

    current_room = character.location
    await character.send(f"Teleporting to Room {target_room_id}...")

    if current_room:
        await current_room.broadcast(f"\r\n{character.name} vanishes in a puff of smoke.\r\n", exclude={character})
        current_room.remove_character(character)

    character.update_location(target_room)
    target_room.add_character(character)
    await target_room.broadcast(f"\r\n{character.name} appears in a flash of light.\r\n", exclude={character})

    # Reuse the 'look' command's logic to show the new room completely
    from .general import cmd_look
    await cmd_look(character, world, db_conn, "")
    return True


async def cmd_roomstat(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Admin: Shows detailed stats for the current or specified room. Usage: @roomstat [room_id]"""
    room_to_stat = None
    if not args_str:
        room_to_stat = character.location
    elif args_str.isdigit():
        room_to_stat = world.get_room(int(args_str))
    
    if not room_to_stat:
        await character.send("Could not find the specified room.")
        return True
    
    area_name = world.get_area(room_to_stat.area_id)['name'] or "Unknown"
    obj_names = [obj.get('name', '?') for obj in room_to_stat.objects]

    output = [
        f"\r\n--- Room Stats [ID: {room_to_stat.dbid}] ---",
        f"Name       : {room_to_stat.name}",
        f"Area       : {area_name} [ID: {room_to_stat.area_id}]",
        f"Description: {room_to_stat.description}",
        f"Flags      : {sorted(list(room_to_stat.flags)) if room_to_stat.flags else 'None'}",
        f"Exits      : {json.dumps(room_to_stat.exits)}",
        f"Spawners   : {json.dumps(room_to_stat.spawners)}",
        f"Objects ({len(obj_names)}): {', '.join(obj_names) if obj_names else 'None'}",
        f"Coinage    : {utils.format_coinage(room_to_stat.coinage)}",
        "--------------------------------"
    ]
    await character.send("\r\n".join(output))
    return True


async def cmd_examine(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Admin: Shows debug info about world objects. Usage: @examine <type> <id/name>"""
    parts = args_str.lower().split(" ", 1)
    if len(parts) != 2:
        await character.send("Usage: @examine <char|mob|item_template|room> <id>")
        return True

    obj_type, identifier = parts
    output = [f"--- Examining {obj_type} '{identifier}' ---"]
    found = False

    try:
        if obj_type == "char" and identifier.isdigit():
            target_char = world.get_active_character(int(identifier))
            if target_char:
                output.append(f" Status: {target_char.status}, Stance: {target_char.stance}")
                output.append(f" Location: {target_char.location_id} ({getattr(target_char.location, 'name', 'None')})")
                output.append(f" HP/Ess: {target_char.hp:.1f}/{target_char.max_hp:.1f} | {target_char.essence:.1f}/{target_char.max_essence:.1f}")
                output.append(f" Stats: {json.dumps(target_char.stats)}")
                output.append(f" Effects: {json.dumps(target_char.effects)}")
                found = True
        elif obj_type == "mob" and identifier.isdigit():
            mob_instance_id = int(identifier)
            target_mob = next((m for r in world.rooms.values() for m in r.mobs if m.instance_id == mob_instance_id), None)
            if target_mob:
                output.append(f" Template ID: {target_mob.template_id}, Instance ID: {target_mob.instance_id}")
                output.append(f" Location: Room {getattr(target_mob.location, 'dbid', '?')}")
                output.append(f" HP: {target_mob.hp}/{target_mob.max_hp}")
                output.append(f" Target: {getattr(target_mob.target, 'name', 'None')}, Fighting: {target_mob.is_fighting}")
                output.append(f" Stats: {json.dumps(target_mob.stats)}")
                found = True
        elif obj_type in ["item_template", "item"] and identifier.isdigit():
            template_data = world.get_item_template(int(identifier))
            if template_data:
                output.append(json.dumps(dict(template_data), indent=2))
                found = True

    except Exception as e:
        log.exception("Error during @examine")
        output.append(f"An error occurred: {e}")

    if not found:
        output.append("Object not found or type invalid.")
    
    await character.send("\r\n".join(output))
    return True


async def cmd_setstat(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Admin: Sets your base stat for testing. Usage: @setstat <stat> <value>"""
    parts = args_str.lower().split()
    if len(parts) != 2:
        await character.send("Usage: @setstat <might|vitality|etc> <value>")
        return True

    stat_name, value_str = parts
    if stat_name not in ["might", "vitality", "agility", "intellect", "aura", "persona"]:
        await character.send(f"Invalid stat name '{stat_name}'.")
        return True

    try:
        value = int(value_str)
        character.stats[stat_name] = max(1, value)
        
        # BUG FIX: Call the correctly renamed function from character.py
        character.recalculate_max_vitals()
        character.hp = min(character.hp, character.max_hp)
        character.essence = min(character.essence, character.max_essence)

        await character.send(f"Set {stat_name.capitalize()} to {value}. Max HP/Essence recalculated.")
        await character.send("(Note: Stat change is temporary until next save.)")
    except ValueError:
        await character.send("Invalid value. Must be an integer.")
    return True