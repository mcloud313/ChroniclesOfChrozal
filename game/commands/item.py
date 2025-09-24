# game/commands/item.py
import logging
import json
from typing import TYPE_CHECKING
from ..item import Item
from .. import utils
from ..definitions import item_defs
from ..combat import outcome_handler


if TYPE_CHECKING:
    from ..character import Character
    from ..world import World

log = logging.getLogger(__name__)

COINAGE_KEYWORDS = {"coins", "coin", "money", "coinage", "talons", "shards", "orbs", "crowns"}

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
    
    if args_str.lower() in COINAGE_KEYWORDS:
        if character.location.coinage > 0:
            amount = character.location.coinage
            # Remove coinage from the room (this also updates the database)
            await character.location.add_coinage(-amount, world)
            # Add coinage to the character
            character.coinage += amount
            
            await character.send(f"You pick up {utils.format_coinage(amount)}.")
            await character.location.broadcast(
                f"\r\n{character.name} picks up some coins.\r\n",
                exclude={character}
            )
            return True
        else:
            await character.send("There is no money here to pick up.")
            return True
     
    # Case 1: Get item from a container (e.g., "get sword from bag")
    if " from " in args_str:
        item_name, container_name = [s.strip() for s in args_str.split(" from ", 1)]

        container = character.find_container_by_name(container_name)
        if not container:
            await character.send(f"You don't have a {container_name}.")
            return True
        
        if not container.is_open:
            await character.send(f"You must open the {container.name} first.")
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
        item_to_get.room = None
        
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

    item_to_drop.room = character.location

    # Move item in memory
    del character._inventory_items[item_to_drop.id]
    character.location.item_instance_ids.append(item_to_drop.id)

    world.mark_room_dirty(character.location)

    await character.send(f"You drop {item_to_drop.name}.")
    await character.location.broadcast(f"\r\n{character.name} drops {item_to_drop.name}.\r\n", exclude={character})
    return True

async def cmd_wear(character: 'Character', world: 'World', args_str: str) -> bool:
    """Handles wearing armor and wielding weapons."""
    if not args_str:
        await character.send("Wear or wield what?")
        return True

    item_to_equip = character.find_item_in_inventory_by_name(args_str)
    if not item_to_equip:
        await character.send("You aren't carrying that.")
        return True
    
    target_slots = item_to_equip.wear_location
    if not target_slots:
        await character.send("You can't equip that.")
        return True
    
    if isinstance(target_slots, str):
        target_slots = [target_slots]
    
    # Check if slots are occupied
    for slot in target_slots:
        if slot in character._equipped_items and character._equipped_items[slot] is not None:
            await character.send(f"You are already using your {slot.replace('_', ' ')}.")
            return True
    
    # --- NEW: Two-Handed Wielding Logic ---
    if item_to_equip.item_type == item_defs.TWO_HANDED_WEAPON:
        if character._equipped_items.get("main_hand") or character._equipped_items.get("off_hand"):
            await character.send("You must have both hands free to wield that weapon.")
            return True
        
        # Equip in both hands
        del character._inventory_items[item_to_equip.id]
        character._equipped_items["main_hand"] = item_to_equip
        character._equipped_items["off_hand"] = item_to_equip # Use same item as a placeholder
        
        await character.send(f"You heft {item_to_equip.name} with both hands.")
        await character.location.broadcast(f"\r\n{character.name} hefts {item_to_equip.name} with both hands.\r\n", exclude={character})
        return True
    
    # --- FIX: LOGIC UPDATE ---
    del character._inventory_items[item_to_equip.id]
    for slot in target_slots:
        character._equipped_items[slot] = item_to_equip

    verb = "wield" if item_to_equip.item_type == "WEAPON" else "wear"
    await character.send(f"You {verb} {item_to_equip.name}.")
    await character.location.broadcast(f"\r\n{character.name} {verb}s {item_to_equip.name}.\r\n", exclude={character})
    return True

async def cmd_remove(character: 'Character', world: 'World', args_str: str) -> bool:
    """Removes an equipped item, correctly handling multi-slot items."""
    if not args_str:
        await character.send("Remove what?")
        return True

    item_to_remove = None
    # Find the item in the equipped items dict by name
    for item in character._equipped_items.values():
        if item and args_str.lower() in item.name.lower():
            item_to_remove = item
            break
            
    if not item_to_remove:
        await character.send("You are not wearing that.")
        return True

    # --- THE FIX IS HERE ---
    # Determine which slots the item actually occupies from its wear_location
    slots_to_clear = []
    wear_loc = item_to_remove.wear_location
    if isinstance(wear_loc, str):
        slots_to_clear = [wear_loc]
    elif isinstance(wear_loc, list):
        slots_to_clear = wear_loc
    
    # Remove the item from all of its associated slots
    for slot in slots_to_clear:
        if slot in character._equipped_items:
            # We only delete the key if the item matches, to prevent bugs
            if character._equipped_items[slot].id == item_to_remove.id:
                del character._equipped_items[slot]
    
    # Place the item back in inventory
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
    
    if not container.is_open:
        await character.send(f"You must open the {container.name} first.")
        return True
    
    # 3. Sanity check: can't put a container in itself
    if item_to_put.id == container.id:
        await character.send("You can't put an item inside itself.")
        return True
    
    # 4. Check capacity
    if container.get_total_contents_weight() + item_to_put.get_total_weight() > container.capacity:
        await character.send(f"The {container.name} is too full.")
        return True
    
    #5. Perform the move in memory
    del character._inventory_items[item_to_put.id]
    container.contents[item_to_put.id] = item_to_put
    item_to_put.container_id = container.id

    #6. Perform the move in the database
    await world.db_manager.update_item_location(item_to_put.id, container_id=container.id)

    item_to_put.room = None

    await character.send(f"You put the {item_to_put.name} in the {container.name}.")
    return True

async def cmd_examine(character: ' Character', world: 'World', args_str: str) -> bool:
    if not args_str:
        await character.send("Examine what?")
        return True
    
    # This logic correctly finds an item in hands, equippped or on the ground.
    item_to_examine = (character.find_item_in_inventory_by_name(args_str) or 
                       next((item for item in character._equipped_items.values() if args_str.lower() in item.name.lower()), None) or 
                       character.location.get_item_instance_by_name(args_str, world))
    if not item_to_examine:
        await character.send("You don't see that here.")
        return True
    
    # --- Use color codes for italics on the UUID and call our new helper
    uuid_str = f"{{i({item_to_examine.id}){{x"

    output = [
        f"\n\r--- {item_to_examine.name} {uuid_str} ---",
        item_to_examine.description,
        utils.get_condition_desc(item_to_examine.condition), # <-- New condition description
        f"Type: {item_to_examine.item_type.capitalize()}, Weight: {item_to_examine.weight} stones"
    ]
    await character.send("\n\r".join(output))
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

async def _handle_consume(character: 'Character', world: 'World', args_str: str, consume_type: str) -> bool:
    """Private helper to handle the logic for eating or drinking."""
    if not args_str:
        await character.send(f"{consume_type.capitalize()} what?")
        return True
    
    item_to_consume = character.find_item_in_inventory_by_name(args_str)
    if not item_to_consume:
        await character.send("You aren't carrying that.")
        return True
    
    # Check if the item is of the correct type (FOOD for eat, DRINK/POTION for drink)
    valid_types = {"FOOD"} if consume_type == "eat" else {"DRINK", "POTION"}
    if item_to_consume.item_type not in valid_types:
        await character.send(f"You can't {consume_type} that.")
        return True
    
    # Get the effect from the item's template stats
    template = world.get_item_template(item_to_consume.template_id)
    if not template: return True # should not happen

    try:
        stats = json.loads(template.get('stats', '{}') or '{}')
        effect = stats.get("effect")
        amount = stats.get("amount", 0)
    except (json.JSONDecodeError, TypeError):
        effect, amount = None, 0

    if not effect:
        await character.send(f"You {consume_type} the {item_to_consume.name}, but nothing seems to happen.")

    # apply the effect
    if effect == "heal_hp":
        healed_amount = min(amount, character.max_hp - character.hp)
        character.hp += healed_amount
        await character.send(f"You {consume_type} the {item_to_consume.name} and heal {int(healed_amount)} hit points.")

    elif effect == "heal_essence":
        healed_amount = min(amount, character.max_essence - character.essence)
        character.essence += healed_amount
        await character.send(f"You {consume_type} the {item_to_consume.name} and restore {int(healed_amount)} essence.")

    # Destroy the item instance
    await world.db_manager.delete_item_instance(item_to_consume.id)
    del character._inventory_items[item_to_consume.id]
    del world._all_item_instances[item_to_consume.id]

    # Broadcast to the room
    await character.location.broadcast(f"\r\n{character.name} {consume_type}s a {item_to_consume.name}.\r\n", exclude={character})
    return True

async def cmd_eat(character: 'Character', world: 'World', args_str: str) -> bool:
    """Eats a food item from inventory."""
    return await _handle_consume(character, world, args_str, "eat")

async def cmd_drink(character: 'Character', world: 'World', args_str: str) -> bool:
    """Drinks a potion or beverage from inventory."""
    return await _handle_consume(character, world, args_str, "drink")

async def cmd_open(character: 'Character', world: 'World', args_str: str) -> bool:
    """Opens a container."""
    if not args_str:
        await character.send("Open what?")
        return True

    container = character.find_item_in_inventory_by_name(args_str)
    if not container:
        container = character.location.get_item_instance_by_name(args_str, world)
    
    if not container or container.capacity <= 0:
        await character.send("You can't open that.")
        return True
    
    if container.is_open:
        await character.send(f"The {container.name} is already open.")
        return True

    if container.instance_stats.get("is_locked"):
        await character.send(f"The {container.name} is locked.")
        return True
    
    # --- IMPROVED TRAP LOGIC ---
    # We check for a 'trap' key in the instance_stats, which holds the trap's details.
    if trap_data := container.instance_stats.get("trap"):
        if trap_data.get("is_active"):
            await character.send(f"{{RYou open the {container.name} and trigger a trap!{{x")
            
            # Apply damage or other effects from the trap
            if damage := trap_data.get("damage", 0):
                await outcome_handler.apply_damage(character, damage)
                await character.send(f"{{rYou take {damage} damage!{{x")

            # Deactivate the trap so it doesn't fire again
            trap_data["is_active"] = False
            await world.db_manager.update_item_instance_stats(container.id, container.instance_stats)

            # If the character was killed by the trap, handle defeat
            if not character.is_alive():
                await outcome_handler.handle_defeat(character, character, world)

            # Stop the command here. The trap interrupts the action.
            return True
    # --- END IMPROVED TRAP LOGIC ---

    container.instance_stats["is_open"] = True
    await world.db_manager.update_item_instance_stats(container.id, container.instance_stats)
    await character.send(f"You open the {container.name}.")

    # --- Generate Loot if it's the first time opening ---
    if not container.instance_stats.get("has_been_looted"):
        template = world.get_item_template(container.template_id)
        # Note: 'loot_table_id' on an item template corresponds to a mob_template_id
        # whose loot table we want to use.
        if template and (loot_table_id := template.get('loot_table_id')):
            log.info(f"Generating loot for container {container.id} from table {loot_table_id}.")
            await world.generate_loot_for_container(container, loot_table_id, character)
            
            # Mark as looted so it doesn't generate again
            container.instance_stats["has_been_looted"] = True
            await world.db_manager.update_item_instance_stats(container.id, container.instance_stats)

    return True

async def cmd_close(character: 'Character', world: 'World', args_str: str) -> bool:
    """Closes a container in inventory, equipped, or in the room."""
    if not args_str:
        await character.send("Close what?")
        return True
    
    # Search for the container in inventory, then equipped, then the room.
    target_item = (character.find_item_in_inventory_by_name(args_str) or
                   character.find_item_in_equipment_by_name(args_str) or
                   character.location.get_item_instance_by_name(args_str, world))
    
    if not target_item or target_item.capacity <= 0:
        await character.send("You don't see that here.")
        return True
    
    if not target_item.is_open:
        await character.send("It's already closed.")
        return True
    
    # Close the container in memory
    target_item.instance_stats['is_open'] = False
    await world.db_manager.update_item_instance_stats(target_item.id, target_item.instance_stats)
        
    await character.send(f"You close the {target_item.name}.")
    return True

async def cmd_unlock(character: 'Character', world: 'World', args_str: str) -> bool:
    """Unlocks a target object with a key from inventory."""
    if " with " not in args_str:
        await character.send("What do you want to unlock with that? (e.g., unlock chest with iron key)")
        return True
    
    target_name, key_name = [s.strip() for s in args_str.split(" with ", 1)]
    
    # 1. Find the target object in the room
    target_obj = character.location.get_item_instance_by_name(target_name, world)
    if not target_obj:
        await character.send(f"You don't see a '{target_name}' here.")
        return True
    
    # 2. Find the key in the character's hands
    key_obj = character.find_item_in_inventory_by_name(key_name)
    if not key_obj:
        await character.send(f"You aren't holding a '{key_name}'.")
        return True
    
    # 3. Check if the target is actually locked
    if not target_obj.instance_stats.get('is_locked', False):
        await character.send(f"The {target_obj.name} is already unlocked.")
        return True
    
    # 4. The unlock check
    lock_id = target_obj.instance_stats.get('lock_id')
    if not lock_id:
        await character.send(f"The {target_obj.name} doesn't seem to have a keyhole.")
        return True
    
    if lock_id in key_obj.unlocks:
        #Success!
        target_obj.instance_stats['is_locked'] = False
        # Save the change to the database
        await world.db_manager.update_item_instance_stats(target_obj.id, target_obj.instance_stats)
        
        await character.send(f"You unlock the {target_obj.name} with the {key_obj.name}.")
    else:
        # Failure
        await character.send("The key doesn't seem to fit in the lock.")
        
    return True

async def cmd_lock(character: 'Character', world: 'World', args_str: str) -> bool:
    """Locks a target object with a key from inventory."""
    if " with " not in args_str:
        await character.send("What do you want to lock with what? (e.g., lock chest with iron key)")
        return True

    target_name, key_name = [s.strip() for s in args_str.split(" with ", 1)]

    # Find the key in the character's hands first
    key_obj = character.find_item_in_inventory_by_name(key_name)
    if not key_obj:
        await character.send(f"You aren't holding a '{key_name}'.")
        return True

    # --- Try to find a door (exit) to lock ---
    for exit_name, exit_data in character.location.exits.items():
        if target_name in exit_name.lower() and isinstance(exit_data, dict):
            if exit_data.get('is_locked'):
                await character.send("That is already locked.")
                return True
            
            lock_id = exit_data.get('lock_id')
            if not lock_id:
                await character.send("That cannot be locked.")
                return True

            if lock_id in key_obj.unlocks:
                exit_data['is_locked'] = True
                await world.db_manager.update_room_exits(character.location.dbid, character.location.exits)
                await character.send(f"You lock the {exit_name} with the {key_obj.name}.")
            else:
                await character.send("The key doesn't fit that lock.")
            return True
    
    # --- If not a door, try to find an item (chest) ---
    target_item = character.location.get_item_instance_by_name(target_name, world)
    if target_item:
        if target_item.instance_stats.get('is_locked'):
            await character.send("That is already locked.")
            return True
        
        lock_id = target_item.instance_stats.get('lock_id')
        if not lock_id:
            await character.send("That cannot be locked.")
            return True

        if lock_id in key_obj.unlocks:
            target_item.instance_stats['is_locked'] = True
            await world.db_manager.update_item_instance_stats(target_item.id, target_item.instance_stats)
            await character.send(f"You lock the {target_item.name} with the {key_obj.name}.")
        else:
            await character.send("The key doesn't fit that lock.")
        return True

    await character.send(f"You don't see a '{target_name}' here to lock.")
    return True

async def cmd_light(character: 'Character', world: 'World', args_str: str) -> bool:
    """Lights an item that is a light source."""
    if not args_str:
        await character.send("Light what?")
        return True

    item_to_light = character.find_item_in_inventory_by_name(args_str)
    if not item_to_light:
        await character.send("You aren't carrying that.")
        return True

    if item_to_light.item_type != item_defs.LIGHT_SOURCE:
        await character.send("You can't light that.")
        return True

    if item_to_light.instance_stats.get("is_lit"):
        await character.send(f"The {item_to_light.name} is already lit.")
        return True

    # Update the item's state in memory and save to DB
    item_to_light.instance_stats["is_lit"] = True
    await world.db_manager.update_item_instance_stats(item_to_light.id, item_to_light.instance_stats)

    await character.send(f"You light the {item_to_light.name}, casting a warm glow.")
    await character.location.broadcast(
        f"\r\n{character.name} lights a {item_to_light.name}.\r\n",
        exclude={character}
    )
    return True

async def cmd_snuff(character: 'Character', world: 'World', args_str: str) -> bool:
    """Extinguishes a lit light source."""
    if not args_str:
        await character.send("Snuff what?")
        return True

    # A light source could be in hands or equipped (e.g., a lantern on a belt)
    item_to_snuff = (character.find_item_in_inventory_by_name(args_str) or
                     character.find_item_in_equipment_by_name(args_str))

    if not item_to_snuff:
        await character.send("You don't have that.")
        return True

    if item_to_snuff.item_type != item_defs.LIGHT_SOURCE:
        await character.send("That is not a light source.")
        return True

    if not item_to_snuff.instance_stats.get("is_lit"):
        await character.send(f"The {item_to_snuff.name} is not lit.")
        return True

    # Update the item's state
    item_to_snuff.instance_stats["is_lit"] = False
    await world.db_manager.update_item_instance_stats(item_to_snuff.id, item_to_snuff.instance_stats)

    await character.send(f"You snuff out the {item_to_snuff.name}.")
    await character.location.broadcast(
        f"\r\n{character.name} snuffs out their {item_to_snuff.name}.\r\n",
        exclude={character}
    )
    return True
        