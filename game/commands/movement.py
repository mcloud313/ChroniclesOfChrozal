# game/commands/movement.py
"""
Movement commands.
"""
import logging
from typing import TYPE_CHECKING, Optional, Dict, Any

from .. import utils
from .. import combat as combat_logic

if TYPE_CHECKING:
    from ..character import Character
    from ..world import World
    import aiosqlite
    from ..room import Room

log = logging.getLogger(__name__)


async def _perform_move(character: 'Character', world: 'World', target_room: 'Room', exit_name: str):
    """
    Handles the logic after a valid exit is found: announcements,
    state changes, and sending the new room's description.
    """
    current_room = character.location
    char_name = character.name

    # --- Announce Departure ---
    if current_room:
        departure_msg = f"\r\n{char_name} leaves {exit_name}.\r\n"
        await current_room.broadcast(departure_msg, exclude={character})
        current_room.remove_character(character)

    # --- Update Character State ---
    character.update_location(target_room)
    target_room.add_character(character)

    # --- Announce Arrival (with improved immersion) ---
    opposite_direction = utils.get_opposite_direction(exit_name)
    if opposite_direction:
        arrival_msg = f"\r\n{char_name} arrives from the {opposite_direction}.\r\n"
    else:
        arrival_msg = f"\r\n{char_name} arrives.\r\n"
    await target_room.broadcast(arrival_msg, exclude={character})

    # --- NEW: Group Cohesion Check ---
    # This runs after the move is complete.
    if character.group and character.group.leader != character:
        # Check if the member is now in a different room than their leader
        if character.location != character.group.leader.location:
            group = character.group # Get a reference before leaving
            group.remove_member(character)
            
            await character.send("{yYou have strayed too far from your group and have been removed.{x")
            await group.broadcast(f"{character.name} has strayed from the group.")


    # --- Send new room info to the character ---
    look_string = target_room.get_look_string(character, world)
    await character.send(look_string)

    # Display items and coins on the ground
    ground_items_output = []
    item_counts = {}
    for item_id in target_room.items:
        item_counts[item_id] = item_counts.get(item_id, 0) + 1

    for template_id, count in sorted(item_counts.items()):
        template = world.get_item_template(template_id)
        item_name = template['name'] if template else f"Item #{template_id}"
        display_name = item_name + (f" (x{count})" if count > 1 else "")
        ground_items_output.append(display_name)

    if target_room.coinage > 0:
        ground_items_output.append(utils.format_coinage(target_room.coinage))

    if ground_items_output:
        await character.send("You also see here: " + ", ".join(ground_items_output) + ".")

    # Apply roundtime with armor penalty
    base_rt = 1.0
    rt_penalty = character.get_total_av(world) * 0.05  # +0.05s RT per point of total AV
    character.roundtime = base_rt + rt_penalty
    if rt_penalty > 0:
        await character.send(f"Your armor slows your movement (+{rt_penalty:.1f}s).")


async def cmd_move(character: 'Character', world: 'World', direction: str) -> bool:
    """Handles all cardinal/ordinal directional movement commands."""
    if not character.location:
        await character.send("You cannot seem to move from the void.")
        return True
    if character.stance != "Standing":
        await character.send("You must be standing to move.")
        return True
    if character.roundtime > 0:
        await character.send(f"You are still recovering for {character.roundtime:.1f} seconds.")
        return True

    exit_data = character.location.exits.get(direction.lower())

    # This command now only handles simple, direct exits (where the exit data is an integer).
    # Complex exits with skill checks must be used with the 'go' command.
    if not isinstance(exit_data, int):
        await character.send("You can't go that way.")
        return True

    target_room_id = exit_data
    target_room = world.get_room(target_room_id)

    if target_room is None:
        log.error("Exit '%s' in room %d points to non-existent room %d!",
                direction, character.location.dbid, target_room_id)
        await character.send("The path ahead seems to vanish into nothingness.")
        return True

    await _perform_move(character, world, target_room, direction)
    return True


async def cmd_go(character: 'Character', world: 'World', args_str: str) -> bool:
    """Handles the 'go <target>' command for complex, named exits that may require skill checks."""
    if not character.location:
        await character.send("You cannot seem to go anywhere from the void.")
        return True
    if character.stance != "Standing":
        await character.send("You must be standing to move.")
        return True
    if character.roundtime > 0:
        await character.send(f"You are still recovering for {character.roundtime:.1f} seconds.")
        return True

    exit_name = args_str.strip().lower()
    if not exit_name:
        await character.send("Go where? (e.g., go hole, go climb rope)")
        return True

    exit_data = character.location.exits.get(exit_name)
    if exit_data is None:
        await character.send(f"You see no exit like '{exit_name}' here.")
        return True

    target_room_id: Optional[int] = None
    skill_check_data: Optional[Dict[str, Any]] = None

    # --- Parse Exit Data ---
    if isinstance(exit_data, int):
        target_room_id = exit_data
    elif isinstance(exit_data, dict):
        target_room_id = exit_data.get('target')
        skill_check_data = exit_data.get('skill_check')
    else:
        log.error("Room %d exit '%s' has invalid data type: %r", character.location.dbid, exit_name, exit_data)
        await character.send("The way forward seems confused.")
        return True

    if not isinstance(target_room_id, int):
        log.error("Room %d exit '%s' has invalid target ID: %r", character.location.dbid, exit_name, target_room_id)
        await character.send("The way forward seems broken.")
        return True

    # --- Perform Skill Check if Required ---
    if skill_check_data:
        skill_name = skill_check_data.get('skill')
        dc = skill_check_data.get('dc', 10)
        if not skill_name:
            log.error("Room %d exit '%s' skill_check is missing 'skill' key.", character.location.dbid, exit_name)
            await character.send("The obstacle seems undefined.")
            return True

        check_result = utils.skill_check(character, skill_name, dc=dc)
        
        # Provide verbose feedback to the player
        feedback = (f"You attempt {skill_name.title()}... "
                    f"{{c[Roll: {check_result['roll']} + Skill: {check_result['skill_value']} = {check_result['total_check']} vs DC: {check_result['dc']}]"
                    f"{{x {{gSuccess!{{x" if check_result['success'] else f"{{x {{rFailure!{{x")
        await character.send(feedback)

        if not check_result['success']:
            fail_msg = skill_check_data.get('fail_msg', "You fail to overcome the obstacle.")
            await character.send(fail_msg)
            
            if (fail_damage := skill_check_data.get('fail_damage', 0)) > 0:
                character.hp = max(0.0, character.hp - fail_damage)
                await character.send(f"{{rYou take {int(fail_damage)} damage!{{x")
                if character.hp <= 0:
                    await combat_logic.handle_defeat(character, character, world)
                    return True # Stop if defeated
            
            character.roundtime = 2.0 # Apply failure roundtime
            return True # Stop movement

    # --- Perform Movement ---
    target_room = world.get_room(target_room_id)
    if target_room is None:
        log.error("Exit '%s' in room %d points to non-existent room %d!",
                exit_name, character.location.dbid, target_room_id)
        await character.send(f"You try to go '{exit_name}', but the way seems to vanish.")
        return True

    await _perform_move(character, world, target_room, exit_name)
    return True