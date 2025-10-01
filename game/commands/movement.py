# game/commands/movement.py
"""
Movement commands.
"""
import random
import logging
import json
from typing import TYPE_CHECKING, Optional, Dict, Any

from .. import utils
from .. import resolver as combat_logic

if TYPE_CHECKING:
    from ..character import Character
    from ..world import World
    from ..room import Room

log = logging.getLogger(__name__)

CARDINAL_DIRECTIONS = {"north", "south", "east", "west", "up", "down", "northeast", "northwest", "southeast", "southwest"}


async def _perform_move(character: 'Character', world: 'World', target_room: 'Room', exit_name: str):
    """
    Handles the logic for moving characters between rooms, now with group support.
    """
    # --- 1. Identify Who to Move ---
    chars_to_move = [character]
    is_group_move = character.group and character.group.leader == character
    if is_group_move:
        chars_to_move = list(character.group.members)

    current_room = character.location
    
    # --- 2. Calculate Shared Roundtime ---
    base_rt = 1.0
    leader_penalty = character.total_av * 0.05
    move_rt = base_rt + leader_penalty + character.slow_penalty

    if "ROUGH_TERRAIN" in current_room.flags:
        move_rt *= 2

    if character.location:
        from ..definitions import weather as weather_defs
        area_weather = world.area_weather.get(character.location.area_id, {})
        condition = area_weather.get("condition", "CLEAR")
        weather_effect = weather_defs.WEATHER_EFFECTS.get(condition, {})
        weather_penalty = weather_effect.get("movement_penalty", 0.0)
        move_rt += weather_penalty
    
    final_rt = move_rt
    if is_group_move:
        slowest_member_rt = character.group.get_slowest_member_rt()
        final_rt = max(move_rt, slowest_member_rt)

    # --- 3. Announce Departure & Immediately Update Room State ---
    departure_message = utils.format_departure_message(character.name, exit_name)

    # Broadcast the departure message first.
    if is_group_move:
        await current_room.broadcast(f"\r\n{character.name}'s group leaves {exit_name}.\r\n", exlclude=set(chars_to_move))
    else:
        await current_room.broadcast(f"\r\n{character.name} {departure_message}.\r\n", exclude={character})
    
    for char in chars_to_move:
        current_room.remove_character(char)

    for char in chars_to_move:
        if char != character:
            await char.send(f"Your leader moves the group {exit_name}")

    # --- 4. Update Character State & Add to New Room ---
    for char in chars_to_move:
        char.update_location(target_room)
        target_room.add_character(char)
        char.roundtime = final_rt # Apply the shared roundtime to everyone

    # --- 5. Announce Arrival ---
    opposite_direction = utils.get_opposite_direction(exit_name)

    if is_group_move:
        arrival_msg = f"\r\n{character.name}'s group arrives.\r\n"
    elif opposite_direction:
        # Use the canonical form for display
        canonical_opp = utils.get_canonical_direction(opposite_direction) or opposite_direction
        arrival_msg = f"\r\n{character.name} arrives from the {canonical_opp}.\r\n"
    else:
        arrival_msg = f"\r\n{character.name} arrives from the {canonical_opp}.\r\n"

    await target_room.broadcast(arrival_msg, exclude={character})

    # --- 6. Send Room Info to All Movers ---
    for char in chars_to_move:
        look_string = target_room.get_look_string(char, world)
        await char.send(look_string)

        ground_items_output = []
        item_counts = {}
        for item_id in target_room.item_instance_ids:
            item_obj = world.get_item_object(item_id)
            if item_obj:
                item_counts[item_obj.name] = item_counts.get(item_obj.name, 0) + 1

        for name, count in sorted(item_counts.items()):
            display_name = name + (f" (x{count})" if count > 1 else "")
            ground_items_output.append(display_name)

        if target_room.coinage > 0:
            ground_items_output.append(utils.format_coinage(target_room.coinage))

        # if ground_items_output:
        #     await char.send("You also see here: " + ", ".join(ground_items_output) + ".")

        if leader_penalty > 0 and char == character:
            await character.send(f"Your armor slows your movement (+{leader_penalty:.1f}s).")



async def _perform_drag(dragger: 'Character', target_corpse: 'Character', target_room: 'Room', exit_name: str):
    """Handles the logic of dragging a corpse to another room."""
    current_room = dragger.location
    
    # 1. Apply the heavy roundtime to the dragger
    dragger.roundtime = 10.0
    await dragger.send(f"You begin dragging {target_corpse.name}'s corpse...")

    # 2. Announce Departure
    await current_room.broadcast(
        f"\r\n{dragger.name} drags the corpse of {target_corpse.name} {exit_name}.\r\n",
        exclude={dragger} # Exclude the dragger, who gets their own message
    )

    # 3. Update State for Both Characters
    current_room.remove_character(dragger)
    current_room.remove_character(target_corpse)
    dragger.update_location(target_room)
    target_corpse.update_location(target_room)
    target_room.add_character(dragger)
    target_room.add_character(target_corpse)

    # 4. Announce Arrival
    opposite_direction = utils.get_opposite_direction(exit_name)
    arrival_msg = f"\r\n{dragger.name} arrives, dragging the body of {target_corpse.name} from the {opposite_direction}.\r\n"
    await target_room.broadcast(arrival_msg, exclude={dragger})

    # 5. Send new room info to the dragger
    look_string = target_room.get_look_string(dragger, dragger.world)
    await dragger.send(look_string)

async def cmd_move(character: 'Character', world: 'World', args_str: str, *, direction: str) -> bool:
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
    
    if not character.can_see():
        if random.random() < 0.25: # 25% chance to trip and fail
            await character.send("{rYou stumble in the darkness and fall!<x>")
            await combat_logic.apply_damage(character, 3, "bludgeon", world)
            character.roundtime = 5.0
            character.stance = "Lying"
            if not character.is_alive():
                await combat_logic.handle_defeat(character, character, world)
            return True # Stop movement

    exit_data = character.location.exits.get(direction.lower())

    if not exit_data:
        await character.send("You can't go that way.")
        return True

    # For now, cmd_move only handles simple, non-hidden exits.
    # We can add checks for 'is_hidden' or door states here later.
    target_room_id = exit_data.get('destination_room_id')

    if target_room_id is None:
        log.error("Exit '%s' in room %d is missing a destination_room_id!",
                  direction, character.location.dbid)
        await character.send("The path ahead seems to vanish into nothingness.")
        return True

    target_room = world.get_room(target_room_id)

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
    
    if not character.can_see():
        if random.random() < 0.25: # 25% chance to trip and fail
            await character.send("{rYou stumble in the darkness and fall!<x>")
            await combat_logic.apply_damage(character, 3, "bludgeon", world)
            character.roundtime = 5.0
            character.stance = "Lying"
            if not character.is_alive():
                await combat_logic.handle_defeat(character, character, world)
            return True # Stop movement

    exit_name = args_str.strip().lower()
    if not exit_name:
        await character.send("Go where? (e.g., go hole, go climb rope)")
        return True

    exit_data = character.location.exits.get(exit_name)
    if not exit_data:
        # Also check cardinal directions in case the user types "go north"
        exit_data = character.location.exits.get(utils.get_canonical_direction(exit_name))

    if not exit_data:
        await character.send(f"You see no way to go '{exit_name}' here.")
        return True

    target_room_id = exit_data.get('destination_room_id')
    if target_room_id is None:
        log.error("Room %d exit '%s' has an invalid target ID.", character.location.dbid, exit_name)
        await character.send("The way forward seems broken.")
        return True

    # Extract the exit's 'details' dictionary. This contains all complex exit info.
    exit_details_raw = exit_data.get('details')
    exit_details: Dict[str, Any] = {}
    if isinstance(exit_details_raw, str) and exit_details_raw:
        try:
            exit_details = json.loads(exit_details_raw)
        except json.JSONDecodeError:
            log.warning("Room %d exit '%s' has malformed JSON in details: %s", 
                        character.location.dbid, exit_name, exit_details_raw)
    elif isinstance(exit_details_raw, dict):
        exit_details = exit_details_raw

    # --- Handle Doors and Locks ---
    if exit_details.get("is_door"):
        if not exit_details.get("is_open", True):
            await character.send("The door is closed.")
            return True
        if exit_details.get("is_locked", False):
            await character.send("The door is locked.")
            return True

    #  Get the skill check data *from* the exit details.
    skill_check_data: Optional[Dict[str, Any]] = exit_details.get("skill_check")

    # --- Perform Skill Check if Required ---
    if skill_check_data:
        skill_name = skill_check_data.get('skill')
        dc = skill_check_data.get('dc', 10)
        if not skill_name:
            log.error("Room %d exit '%s' skill_check is missing 'skill' key.", character.location.dbid, exit_name)
            await character.send("The obstacle seems undefined.")
            return True

        # The rest of your skill check logic from here was already perfect.
        check_result = utils.skill_check(character, skill_name, dc=dc)
        
        feedback = (f"You attempt {skill_name.title()}... "
                    f"<c>[Roll: {check_result['roll']} + Skill: {check_result['skill_value']} = {check_result['total_check']} vs DC: {check_result['dc']}]"
                    f"<x> <g>Success!<x>" if check_result['success'] else f"<x> <r>Failure!<x>")
        await character.send(feedback)

        if not check_result['success']:
            fail_msg = skill_check_data.get('fail_msg', "You fail to overcome the obstacle.")
            await character.send(fail_msg)
            
            if (fail_damage := skill_check_data.get('fail_damage', 0)) > 0:
                # Use the resolver to handle damage and concentration checks
                await combat_logic.apply_damage(character, fail_damage)
                await character.send(f"<r>You take {int(fail_damage)} damage!<x>")
                if not character.is_alive():
                    # The resolver doesn't handle defeat, so we check here.
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

    # If all checks pass, initiate the move
    await _perform_move(character, world, target_room, exit_name)
    return True