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
    "Gets an item from the room or from a container."""
    if not args_str:
        await character.send("Get what?")
        return True
    
    # Case 1: Get item from a container (e.g., "get sword from bag")
    if " from " in args_str:
        item_name, container_name, = [s.strip() for s in args_str.split(" from ", 1)]

        container = character.find_container_by_name(container_name)
        if not container:
            await character.send(f"You don't have a {container_name}.")
            return True
        
        # Find the item inside the container's contents
        item_to_get = next((item for item in container.contents.values() if item_name.lower() in item.name.lower()), None)
        if not item_to_get:
            await character.send(f"Tehre is no {item_name} in the {container_name}.")
            return True
        
        # Check the two-hand limit
        if len(character._inventory_items) >= 2:
            await character.send("Your hands are full.")
            return True
        
        # Perform the move in memory
        del container.contents[item_to_get.id]
        character._inventory_items[item_to_get.id] = item_to_get
        item_to_get.container_id = None

        # Perform the move in the database (assign to character)
        await world.db_manager.update_item_location(item_to_get.id, owner_char_id=character.dbid)

        await character.send(f"You get the {item_to_get.name} from the {container.name}.")
        return True
    
    # Case 2: Get the item from the room (original logic)
    else:
        item_to_get = character.location.get_item_instance_by_name(args_str, world)
        if not item_to_get:
            await character.send("You don't see that here.")
            return True
        
        # Check the two hand limit
        if len(character._inventory_items) >= 2:
            await character.send("Your hands are full.")
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

async def cmd_put(character: 'Character', world: 'World', args_str: str) -> bool:
    """Puts an item from inventory into a container"""
    if " in " not in args_str:
        await character.send("What do you want to put in what? (e.g., put sword in bag)")
        return True
    
    item_name, container_name = [s.strip() for s in args_str.split(" in ", 1)]

    # 1. Find the item in the character's hands (top-level inventory)
    item_to_put = character.find_item_in_inventory_by_name(item_name)
    if not item_to_put:
        await character.send(f"You aren't holding a {item_name}.")
        return True
    
    # 2. Find the container in hands or equipped
    container = character.find_container_by_name(container_name)
    if not container:
        await character.send(f"You don't have a {container_name}.")
        return True
    
    # 3. Sanity check: can't put a container in itself
    if item_to_put.id == container.id:
        await character.send("You can't put an item inside itself.")
        return True
    
    # 4. Check capacity
    if container.get_current_weight() + item_to_put.weight > container.capacity:
        await character.send(f"The {container.name} is too full.")
        return True
    
    #5. Perform the move in memory
    del character._inventory_items[item_to_put.id]
    container.contents[item_to_put.id] = item_to_put
    item_to_put.container_id = container.id

    #6. Perform the move in the database
    await world.db_manager.update_item_location(item_to_put.id, container_id=container.id)

    await character.send(f"You put the {item_to_put.name} in the {container.name}.")
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

async def cmd_repair(character: 'Character', world: 'World', args_str: str) -> bool:
    """Repairs a damaged item at a repair shop."""
    if not args_str:
        await character.send("What do you want to repair?")
        return True
    
    if "REPAIRER" not in character.location.flags:
        await character.send("You can't get anything repaired here.")
        return True
    
    item_to_repair = character.find_item_in_inventory_by_name(args_str)
    if not item_to_repair:
        await character.send("You aren't holding that.")
        return True
    
    if item_to_repair.condition >= 100:
        await character.send(f"The {item_to_repair.name} is already in perfect condition.")
        return True
    
    #Calculate the cost (100 - condition) / 100 * (value * 0.25)
    # Simplified: (100 - condition) * value * 0.0025
    depletion = 100 - item_to_repair.condition
    cost = int(depletion * item_to_repair.value * 0.0025)
    # Ensure a minimum cost of 1 coin for any repair
    cost = max(1, cost)

    if character.coinage < cost:
        await character.send(f"You can't afford the {utils.format_coinage(cost)} repair cost.")
        return True
    
    # Perform transaction
    character.coinage -= cost
    item_to_repair.condition = 100

    # Update the database
    await world.db_manager.update_item_condition(item_to_repair.id, 100)

    await character.send(f"You pay {utils.format_coinage(cost)} and the smith repairs your {item_to_repair.name} to perfect condition.")
    return True