#game/commands/social.py
import logging
from typing import TYPE_CHECKING
from . import movement as movement_logic
from ..group import Group

if TYPE_CHECKING:
    from ..character import Character
    from ..world import World

log = logging.getLogger(__name__)

async def cmd_drag(character: 'Character', world: 'World', args_str: str) -> bool:
    """drags a corpse to an adjacent room."""
    if not args_str:
        await character.send("Who do you want to drag and where? (e.g. drag frodo).")
        return True
    
    try:
        target_name, exit_name = args_str.strip().split(" ", 1)
    except ValueError:
        await character.send("Invalid syntax. (e.g., drag frodo north)")
        return True
    
    #Find the target corpse in the room
    target_corpse = None
    for char in character.location.characters:
        if target_name.lower() in char.name.lower() and char.status == "DEAD" or char.status == "DYING":
            target_corpse = char
            break

    if not target_corpse:
        await character.send("You don't see that body here.")
        return True
    
    # Find the exit this logic is similar to the move command
    exit_data = character.location.exits.get(exit_name.lower())
    if not isinstance(exit_data, int):
        await character.send("You can't drag a body that way.")
        return True
    
    target_room = world.get_room(exit_data)
    if not target_room:
        await character.send("The path seems to vanish into nothingness.")
        return True
    
    # Call the new helper function to perform the move
    await movement_logic._perform_drag(character, target_corpse, target_room, exit_name)
    return True

async def cmd_group(character: 'Character', world: 'World', args_str: str) -> bool:
    """Forms or joins a group with another creature."""
    if not args_str:
        # Display current group info if no target is given
        if not character.group:
            await character.send("You are not in a group. Who do you want to group with?")
        else:
            member_names = [m.name for m in character.group.members]
            output = [
                f"\n\r--- Group Members (Leader: {character.group.leader.name}) ---",
                ", ".join(member_names)
            ]
            await character.send("\n\r".join(output))
            return True
    
    target_char = character.location.get_character_by_name(args_str)

    # --- Pre-condition Checks ---
    if not target_char:
        await character.send("You don't see them here.")
        return True
    if target_char == character:
        await character.send("You can't group with yourself.")
        return True
    if target_char.group:
        await character.send(f"{target_char} is already in a group.")
        return True
    
    # --- Grouping logic ----
    if not character.group:
        # Case 1: You are not in a group so you form one.
        new_group = Group(leader=character)
        new_group.add_member(target_char)
        world.add_active_group(new_group)
        await new_group.broadcast(f"{character.name} has formed a group with {target_char}")
    else:
        # Case 2: You are already in a group.
        if character.group.leader != character:
            await character.send("Only the group leader can invite new members.")
            return True
        if len(character.group.members) >= 4:
            await character.send("Your group is full.")
            return True
        
        character.group.add_member(target_char)
        await character.group.broadcast(f"{target_char.name} has joined the group.")

    return True

async def cmd_disband(character: 'Character', world: ' World', args_str: str) -> bool:
    """Disbands the group you are leading."""
    if not character.group:
        await character.send("You are not in a group.")
        return True
    if character.group.leader != character:
        await character.send("Only the group leader can disband the group.")
        return True
    
    world.remove_active_group(character.group.id)
    await character.group.disband() # This notifies members and clears their group
    return True

async def cmd_leave(character: 'Character', world: 'World', args_str: str) -> bool:
    """Leaves your current group."""
    if not character.group:
        await character.send("You are not in a group.")
        return True

    if character.group.leader == character:
        await character.send("You are the group leader. Use 'disband' to dissolve the group.")
        return True

    # Get a reference to the group before leaving
    group = character.group
    
    # Remove the character from the group in memory
    group.remove_member(character)
    
    await character.send("You have left the group.")
    await group.broadcast(f"{character.name} has left the group.")
    return True

async def cmd_kick(character: 'Character', world: 'World', args_str: str) -> bool:
    """Kicks a member from your group."""
    if not args_str:
        await character.send("Who do you want to kick from the group?")
        return True
    if not character.group:
        await character.send("You are not in a group.")
        return True
    if character.group.leader != character:
        await character.send("Only the group leader can kick members.")
        return True
    
    target_to_kick = None
    for member in character.group.members:
        if args_str.lower() in member.name.lower():
            target_to_kick = member
            break

    if not target_to_kick:
        await character.send("That person is not in your group.")
        return True
    if target_to_kick == character:
        await character.send("You can kick yourself. Use 'disband' instead.")
        return True
    
    # Perform the kick
    character.group.remove_member(target_to_kick)
    await target_to_kick.send("{RYou have been kicked from the group.{x")
    await character.group.broadcast(f"{target_to_kick.name} has been kicked from the group.", exclude={target_to_kick})
    return True