# game/commands/item.py
import logging
from typing import TYPE_CHECKING
from ..item import Item
from .. import utils

if TYPE_CHECKING:
    from ..character import Character
    from ..world import World

log = logging.getLogger(__name__)

async def cmd_inventory(character: 'Character', world: 'World', args_str: str) -> bool:
    """Displays character's unique item instances."""
    output = ["\r\n{c========================= Inventory ========================{x"]
    output.append("{cYou are wearing:{x")
    if not character._equipped_items:
        output.append(" Nothing.")
    else:
        # Sort by slot name for consistent display
        for slot, item in sorted(character._equipped_items.items()):
            slot_display = slot.replace('_', ' ').title()
            output.append(f" <{slot_display:<12}> {item.name}")
    
    output.append("\r\n{cYou are carrying:{x")
    if not character._inventory_items:
        output.append(" Nothing.")
    else:
        item_names = [item.name for item in character._inventory_items.values()]
        output.append(" " + ", ".join(sorted(item_names)) + ".")

    output.append(f"\r\nCoins: {utils.format_coinage(character.coinage)}")
    output.append(f"Weight: {character.get_current_weight()}/{character.get_max_weight()} stones")
    output.append("{c========================================================={x")
    await character.send("\r\n".join(output))
    return True

async def cmd_get(character: 'Character', world: 'World', args_str: str) -> bool:
    """Gets a unique item instance from the room."""
    if not args_str:
        await character.send("Get what?")
        return True
    
    item_to_get = character.location.get_item_instance_by_name(args_str, world)
    
    if not item_to_get:
        await character.send("You don't see that here.")
        return True

    # Move item in the database
    await world.db_manager.update_item_location(item_to_get.id, owner_char_id=character.dbid)

    # Move item in memory
    character.location.item_instance_ids.remove(item_to_get.id)
    character._inventory_items[item_to_get.id] = item_to_get
    
    await character.send(f"You get {item_to_get.name}.")
    await character.location.broadcast(f"\r\n{character.name} gets {item_to_get.name}.\r\n", exclude={character})
    return True

async def cmd_drop(character: 'Character', world: 'World', args_str: str) -> bool:
    """Drops a unique item instance onto the ground."""
    if not args_str:
        await character.send("Drop what?")
        return True

    item_to_drop = character.find_item_in_inventory_by_name(args_str)
    if not item_to_drop:
        await character.send("You aren't carrying that.")
        return True
    
    # Move item in the database
    await world.db_manager.update_item_location(item_to_drop.id, room_id=character.location_id)

    # Move item in memory
    del character._inventory_items[item_to_drop.id]
    character.location.item_instance_ids.append(item_to_drop.id)

    await character.send(f"You drop {item_to_drop.name}.")
    await character.location.broadcast(f"\r\n{character.name} drops {item_to_drop.name}.\r\n", exclude={character})
    return True

async def cmd_wear(character: 'Character', world: 'World', args_str: str) -> bool:
    item_to_wear = character.find_item_in_inventory_by_name(args_str)
    if not item_to_wear:
        await character.send("You aren't carrying that.")
        return True
    
    target_slots = item_to_wear.wear_location
    if not target_slots:
        await character.send("You can't wear that.")
        return True
    
    if isinstance(target_slots, str): target_slots = [target_slots]
    
    for slot in target_slots:
        if slot in character._equipped_items:
            await character.send(f"You are already wearing something on your {slot.lower()}.")
            return True
            
    del character._inventory_items[item_to_wear.id]
    for slot in target_slots:
        character._equipped_items[slot] = item_to_wear
    
    await character.send(f"You wear {item_to_wear.name}.")
    await character.location.broadcast(f"\r\n{character.name} wears {item_to_wear.name}.\r\n", exclude={character})
    return True

async def cmd_remove(character: 'Character', world: 'World', args_str: str) -> bool:
    item_to_remove, found_slot = None, None
    for slot, item in character._equipped_items.items():
        if args_str.lower() in item.name.lower():
            item_to_remove, found_slot = item, slot
            break
            
    if not item_to_remove:
        await character.send("You are not wearing that.")
        return True

    del character._equipped_items[found_slot]
    character._inventory_items[item_to_remove.id] = item_to_remove

    await character.send(f"You remove {item_to_remove.name}.")
    await character.location.broadcast(f"\r\n{character.name} removes {item_to_remove.name}.\r\n", exclude={character})
    return True

async def cmd_examine(character: 'Character', world: 'World', args_str: str) -> bool:
    if not args_str:
        await character.send("Examine what?")
        return True
    
    item_to_examine = (character.find_item_in_inventory_by_name(args_str) or 
                       next((item for item in character._equipped_items.values() if args_str.lower() in item.name.lower()), None) or 
                       character.location.get_item_instance_by_name(args_str, world))

    if not item_to_examine:
        await character.send("You don't see that here.")
        return True
        
    output = [
        f"\r\n--- {item_to_examine.name} ---",
        item_to_examine.description,
        f"It is in {item_to_examine.condition}% condition.",
        f"Type: {item_to_examine.item_type.capitalize()}, Weight: {item_to_examine.weight} stones"
    ]
    await character.send("\r\n".join(output))
    return True