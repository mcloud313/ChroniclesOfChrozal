# game/commands/movement.py
"""
Movement commands.
"""
import logging
from typing import TYPE_CHECKING, Optional, Dict, Any

from .. import utils
from .. import resolver as combat_logic

if TYPE_CHECKING:
    from ..character import Character
    from ..world import World
    import aiosqlite
    from ..room import Room

log = logging.getLogger(__name__)


async def _perform_move(character: 'Character', world: 'World', target_room: 'Room', exit_name: str):
    """
    Handles the logic for moving characters between rooms, now with group support.
    """
    # --- 1. Identify Who to Move ---
    # Start with just the character, but expand to the whole group if they are the leader.
    chars_to_move = [character]
    is_group_move = character.group and character.group.leader == character
    if is_group_move:
        # Get a stable list of members to move
        chars_to_move = list(character.group.members)

    current_room = character.location
    
    # --- 2. Calculate Shared Roundtime ---
    base_rt = 1.0
    # The leader's armor penalty affects the whole group's base move time
    leader_penalty = character.total_av * 0.05
    move_rt = base_rt + leader_penalty + character.slow_penalty
    
    # Final roundtime is the greater of the move time or anyone's current roundtime
    final_rt = move_rt
    if is_group_move:
        slowest_member_rt = character.group.get_slowest_member_rt()
        final_rt = max(move_rt, slowest_member_rt)

    # --- 3. Announce Departure ---
    if current_room:
        if is_group_move:
            # A single message for the whole group leaving
            await current_room.broadcast(f"\r\n{character.name}'s group leaves {exit_name}.\r\n")
        else:
            await current_room.broadcast(f"\r\n{character.name} leaves {exit_name}.\r\n", exclude={character})
        
        # Remove all moving characters from the old room
        for char in chars_to_move:
            current_room.remove_character(char)

    # --- 4. Update State for All Movers ---
    for char in chars_to_move:
        char.update_location(target_room)
        target_room.add_character(char)
        char.roundtime = final_rt # Apply the shared roundtime to everyone

    # --- 5. Announce Arrival ---
    opposite_direction = utils.get_opposite_direction(exit_name)
    arrival_msg = ""
    if is_group_move:
        arrival_msg = f"\r\n{character.name}'s group arrives.\r\n"
    elif opposite_direction:
        arrival_msg = f"\r\n{character.name} arrives from the {opposite_direction}.\r\n"
    else:
        arrival_msg = f"\r\n{character.name} arrives.\r\n"
    
    await target_room.broadcast(arrival_msg)

    # --- 6. Send Room Info to All Movers ---
    for char in chars_to_move:
        # We broadcast the look string to the mover(s)
        look_string = target_room.get_look_string(char, world)
        await char.send(look_string)

        # Check for items on the ground individually
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

        if ground_items_output:
            await char.send("You also see here: " + ", ".join(ground_items_output) + ".")
        
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

    exit_name = args_str.strip().lower()
    if not exit_name:
        await character.send("Go where? (e.g., go hole, go climb rope)")
        return True

    # --- FIX: Simplified Exit Data Parsing ---
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

    skill_check_data: Optional[Dict[str, Any]] = None

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