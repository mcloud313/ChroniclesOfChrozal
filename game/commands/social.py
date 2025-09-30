#game/commands/social.py
import logging
from typing import TYPE_CHECKING
from . import movement as movement_logic
from ..group import Group
from .. import utils

if TYPE_CHECKING:
    from ..character import Character
    from ..world import World

log = logging.getLogger(__name__)

async def cmd_drag(character: 'Character', world: 'World', args_str: str) -> bool:
    """Drags a corpse to an adjacent room."""
    if not args_str:
        await character.send("Who do you want to drag, and where? (e.g., drag frodo north)")
        return True
    
    try:
        target_name, exit_name = args_str.strip().split(" ", 1)
    except ValueError:
        await character.send("Invalid syntax. (e.g., drag frodo north)")
        return True
    
    # Find the target corpse in the room
    target_corpse = None
    for char in character.location.characters:
        if target_name.lower() in char.first_name.lower() and (char.status == "DEAD" or char.status == "DYING"):
            target_corpse = char
            break

    if not target_corpse:
        await character.send("You don't see that body here.")
        return True
    
    # --- FIX: Correctly find the exit and its destination ID ---
    exit_data = character.location.exits.get(exit_name.lower())
    if not exit_data:
        await character.send("You can't drag a body that way.")
        return True

    destination_id = exit_data.get('destination_room_id')
    if not destination_id:
        await character.send("The path seems to vanish into nothingness.")
        return True
    
    target_room = world.get_room(destination_id)
    if not target_room:
        await character.send("The path seems to vanish into nothingness.")
        log.error(f"Drag command failed: Exit '{exit_name}' in room {character.location.dbid} points to non-existent room {destination_id}.")
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
        await character.send(f"{target_char.name} is already in a group.")
        return True
    
    # --- MODIFIED: Check for invites in the new world dictionary ---
    if target_char.dbid in world.pending_invites:
        await character.send(f"{target_char.name} already has a pending group invitation.")
        return True

    if character.group and character.group.leader != character:
        await character.send("Only the group leader can invite new members.")
        return True
    if character.group and len(character.group.members) >= 4:
        await character.send("Your group is full.")
        return True

    # --- MODIFIED: Store the invitation in the world state ---
    world.pending_invites[target_char.dbid] = character.dbid
    
    await character.send(f"You have invited {target_char.name} to join your group.")
    await target_char.send(f"\r\n{character.name} has invited you to join their group.\r\nType <accept group> or <decline group>.")
    return True

async def cmd_accept(character: 'Character', world: 'World', args_str: str) -> bool:
    """Unified accept handler for groups and trades."""

    # --- Group invite logic
    inviter_id = world.pending_invites.get(character.dbid)
    if inviter_id and ("group" in args_str.lower() or not args_str):
        # Fetch teh actual inviter character object
        inviter = world.get_active_character(inviter_id)

        #Clear the invite immediately
        del world.pending_invites[character.dibd]

        # Validate inviter is still available
        if not inviter or not inviter.is_alive() or inviter.location != character.location:
            await character.send("The person who invited you is no longer available.")
            return True
        
        # case #1 Inviter is not in a group, so a new one is formed.
        if not inviter.group:
            new_group = Group(leader=inviter)
            new_group.add_member(character)
            world.add_active_group(new_group)
            await new_group.broadcast(f"{character.name} has joined the group, which is now led by {inviter.name}.")
        else:
            if len(inviter.group.members) >= 4:
                await character.send("The group is now full.")
                await inviter.send(f"{character.name} tried to join, but your group is full.")
                return True
            inviter.group.add_member(character)
            await inviter.group.broadcast(f"{character.name} has joined the group.")

        return True
    
    # TRADE OFFER LOGIC
    elif character.pending_give_offer:
        offer = character.pending_give_offer
        giver = offer["from_char"]
        item_to_receive = offer["item"]
        coinage_to_receive = offer["coinage"]

        # Clear the offer immediately to prevent race conditions
        character.pending_give_offer = None

        # Re-validate the conditions
        if not giver or giver.location != character.location:
            await character.send(f"{giver.name} is no longer here.")
            return True
        
        if item_to_receive:
            if len(character._inventory_items) >= 2:
                await character.send("Your hands are full. You cannot accept the item.")
                await giver.send(f"{character.name}'s hands are now full; they could not accept your {item_to_receive.name}.")
                return True
            if item_to_receive.id not in giver._inventory_items:
                await character.send("The item is no longer available.")
                return True
            
            #Perform item transfer
            del giver._inventory_items[item_to_receive.id]
            character._inventory_items[item_to_receive.id] = item_to_receive
            await world.db_manager.update_item_location(item_to_receive.id, owner_char_id=character.dbid)

            await character.send(f"You accept the {item_to_receive.name} from {giver.name}.")
            await giver.send(f"{character.name} accepts your {item_to_receive.name}.")

        elif coinage_to_receive > 0:
            if giver.coinage < coinage_to_receive:
                await character.send("The coinage is no longer available.")

            # Peform coin transfer
            giver.coinage -= coinage_to_receive
            character.coinage += coinage_to_receive

            await character.send(f"You accept {utils.format_coinage(coinage_to_receive)} from {giver.name}.")
            await giver.send(f"{character.name} accepts your {utils.format_coinage(coinage_to_receive)}.")

        return True
    else:
        await character.send("You don't have any pending offers to accept.")
        return True

async def cmd_decline(character: 'Character', world: 'World', args_str: str) -> bool:
    """Unified decline handler for groups and trades."""
    
    # --- GROUP INVITE LOGIC ---
    inviter_id = world.pending_invites.get(character.dbid)
    if inviter_id and ("group" in args_str.lower() or not args_str):
        # Clear the invite
        del world.pending_invites[character.dbid]
        
        await character.send("You have declined the group invitation.")
        
        # Notify the inviter if they are still around
        inviter = world.get_active_character(inviter_id)
        if inviter and inviter.is_alive():
            await inviter.send(f"{character.name} has declined your group invitation.")
        
        return True
    
    # --- TRADE OFFER LOGIC ---
    elif character.pending_give_offer:
        offer = character.pending_give_offer
        giver = offer["from_char"]
        
        # Clear the offer
        character.pending_give_offer = None
        
        await character.send("You decline the offer.")
        if giver and giver.location == character.location:
            await giver.send(f"{character.name} has declined your offer.")
        
        return True
    
    # --- NO PENDING OFFERS ---
    else:
        await character.send("You don't have any pending offers to decline.")
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

