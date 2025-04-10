# game/commands/item.py
"""
Commands related to items, inventory, and equipment.
"""
import logging
from typing import TYPE_CHECKING, Optional, Dict
import json # Needed for parsing item stats

if TYPE_CHECKING:
    from ..character import Character
    from ..world import World
    import aiosqlite

# Import specific things needed
from ..item import Item
from .. import utils # For format_coinage
# Optional: Import slot constants if created
from ..definitions import slots as equip_slots

log = logging.getLogger(__name__)

# --- Helper ---
def get_item_template_from_world(world: 'World', template_id: int) -> Optional[dict]:
    """Gets item template data as a dict, handling potential errors."""
    template_row = world.get_item_template(template_id)
    if not template_row:
        log.error("Could not find template data for ID %d", template_id)
        return None
    return dict(template_row) # Convert row to dict

# --- Commands ---
async def cmd_inventory(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Displays character inventory, equipment, weight, coinage."""
    output = "\r\n" + "=" * 20 + " Inventory " + "=" * 20 + "\r\n"

    # Equipment
    output += "You are wearing:\r\n"
    equipped_items = []
    # Use defined slot order for consistent display if available, else just iterate
    # slot_order = equip_slots.ALL_SLOTS if equip_slots else character.equipment.keys()
    slot_order = character.equipment.keys()
    for slot in slot_order:
        template_id = character.equipment.get(slot)
        if template_id:
            template = get_item_template_from_world(world, template_id)
            item_name = template['name'] if template else f"Unknown Item ({template_id})"
            # Format: <Slot> Item Name
            equipped_items.append(f" <{slot.replace('_',' ').title():<12}> {item_name}")
    if not equipped_items:
        output += "Nothing.\r\n"
    else:
        output += "\r\n".join(equipped_items) + "\r\n"

    output += "-\r\n" #Separator

    #Inventory (Loose items)
    output += "You are carrying:\r\n"
    if not character.inventory:
        output += " Nothing.\r\n"
    else:
        # Group identical items by name/ID? For now, just list by ID.
        item_names = []
        item_counts = {}
        for template_id in character.inventory:
            item_counts[template_id] = item_counts.get(template_id, 0) + 1

        for template_id, count in sorted(item_counts.items()):
            template = get_item_template_from_world(world, template_id)
            item_name = template['name'] if template else f"Unknown Item #{template_id}"
            display_name = f"{item_name}"
            if count > 1:
                display_name += f" (x{count})"
            item_names.append(display_name)
        output += ", ".join(item_names) + ".\r\n"

        output += "-\r\n" # Separator

        # Coinage & Weight
        max_w = character.get_max_weight()
        curr_w = character.get_current_weight(world) # pass world
        formatted_coinage = utils.format_coinage(character.coinage)
        output += f" Coins: {formatted_coinage}\r\n"
        output += f" Weight: {curr_w}/{max_w} stones"
        # Add encumbrance status later?

        output += "=" * (40 + 11) + "r\n"

        await character.send(output)
        return True
    
async def cmd_get(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Gets an item from the room."""
    if not args_str:
        await character.send("Get what?")
        return True
    
    if not character.location:
        await character.send("You can't get items from the void.")
        return True
    
    target_name = args_str.strip().lower()
    item_template_id_to_get = None
    item_template_data = None

    # Find the first item on the ground matching the name
    # Need a mutable list copy if removing during iteration
    items_on_ground = list(character.location.items)
    item_index_in_room = -1
    
    for i, template_id in enumerate(items_on_ground):
        template = get_item_template_from_world(world, template_id)
        if template and template['name'].lower() == target_name:
            item_template_id_to_get = template_id
            item_template_data = template
            item_index_in_room = i
            break # Get the first one found

    if item_template_id_to_get is None or item_template_data is None:
        await character.send(f"You don't see '{target_name}' here.")
        return True
    
    # Instantiate temporary item to get weight (or parse from template data)
    item_weight = 1 # Default
    try:
        stats = json.loads(item_template_data.get('stats','{}'))
        item_weight = stats.get('weight', 1)
    except Exception: pass # Ignore parsing error, use default

    # Check weight
    max_w = character.get_max_weight()
    curr_w = character.get_current_weight(world)
    if curr_w + item_weight > max_w * 2: # Check against double capacity limit
        await character.send("You can't carry that much weight!")
        # Optional: Send different message if already encumbered vs would become encumbered
        return True
    
    # Pick up item
    character.location.items.pop(item_index_in_room) # Remove from room by index
    character.inventory.append(item_template_id_to_get) # Add template ID to inventory

    item_name = item_template_data['name']
    await character.send(f"You get {item_name}.")
    # Announce to room
    await character.location.broadcast(f"\r\n{character.name} gets {item_name}.\r\n", exclude={character})

    # Apply roundtime
    character.roundtime = 2.0

    return True

async def cmd_drop(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Dropds an item from inventory onto the ground."""
    if not args_str:
        await character.send("Drop what?")
        return True

    if not character.location:
        await character.send("You can't drop items into the void.")
        return True
    
    target_name = args_str.strip().lower()
    # Find the item template ID in inventory
    template_id_to_drop = character.find_item_in_inventory_by_name(target_name)

    if template_id_to_drop is None:
        await character.send("You aren't carrying that.")
        return True
    
    # Drop the item
    character.inventory.remove(template_id_to_drop) # Remove first instance from inv
    character.location.items.append(template_id_to_drop) # Add template ID to room items

    template = get_item_template_from_world(world, template_id_to_drop)
    item_name = template['name'] if template else f"Item #{template_id_to_drop}"

    await character.send(f"You drop {item_name}.")
    # Announce to room
    await character.location.broadcast(f"\r\n{character.name} drops {item_name}.\r\n", exclude={character})

    # Apply roundtime
    character.roundtime = 1.0

    return True

async def cmd_wear(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Wears an item from inventory."""
    if not args_str:
        await character.send("Wear what?")
        return True
    
    target_name = args_str.strip().lower()
    template_id = character.find_item_in_inventory_by_name(target_name)

    if template_id is None:
        await character.send("You aren't carrying that.")
        return True
    
    # Get item details
    item = character.get_item_instance(template_id)
    if not item or item.item_type not in ["ARMOR", "CLOTHING", "SHIELD"]: # Add other wearables
        await character.send("You can't wear that.")
        return True
    
    # Determine target slot(s)
    target_slots = item.wear_location
    if not target_slots:
        await character.send("That item doesn't seem to be wearable on a specific location.")
        return True
    
    # Ensure target_slots is a list
    if isinstance(target_slots, str):
        target_slots = [target_slots] # Make single string into a list
    
    # Check if slots are valid and free
    occupied_slots = []
    for slot in target_slots:
        # Optional: Use is_valid_slot(slot) if using contants
        if character.equipment.get(slot) is not None:
            occupied_slots.append(slot)

    if occupied_slots:
        await character.send(f"You already have something worn on your {', '.join(occupied_slots)}.")
        # TODO: Handle removing existing items automatically? More complex.
        return True
    
    # Wear the item
    character.inventory.remove(template_id) # Remove from inventory
    for slot in target_slots:
        character.equipment[slot] = template_id 

    await character.send(f"You wear {item.name}.")
    await character.location.broadcast(f"\r\n{character.name} wears {item.name}.\r\n", exclude={character})

    # Apply roundtime
    character.roundtime = item.speed # Use item's speed, default 1.0

    return True

async def cmd_wield(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Wields a weapon from inventory."""
    if not args_str:
        await character.send("Wield what?")
        return True
    
    target_name = args_str.strip().lower()
    template_id = character.find_item_in_inventory_by_name(target_name)

    if template_id is None:
        await character.send("You aren't carrying that.")
        return True
    
    item = character.get_item_instance(template_id)
    if not item or item.item_type != "WEAPON": # Simple check for now.
        await character.send("You can't wield that.")
        return True
    
    # Check main hand slot (using constant example)
    # slot_to_use = equip_slots.WIELD_MAIN
    slot_to_use = "WIELD_MAIN" # Use string directly if no constants

    # Handle currently wielded item
    currently_wielded_id = character.equipment.get(slot_to_use)
    if currently_wielded_id == template_id:
        await character.send("You are already wielding that!")
        return True
    if currently_wielded_id is not None:
        # Automatically unwield previous item - move it to inventory
        # Check weight first!
        prev_item = character.get_item_instance(currently_wielded_id)
        prev_weight = getattr(prev_item, 'weight', 1) if prev_item else 1
        if character.get_current_weight(world) + prev_weight > character.get_max_weight() * 2:
            await character.send("You don't have enough carrying capacity to unwield your current item first!")
            return True
        character.inventory.append(currently_wielded_id)
        log.debug("Auto-unwielded template_id %d to inventory for %s", currently_wielded_id, character.name)

    # Wield the new item
    character.inventory.remove(template_id)
    character.equipment[slot_to_use] = template_id

    # TODO: Handle off-hand / dual-wield / two-handed later

    await character.send(f"You wield {item.name}.")
    await character.location.broadcast(f"\r\n{character.name} wields {item.name}.\r\n", exclude={character})

    character.roundtime = item.speed

    return True

async def cmd_remove(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Removes a worn/wielded item, placing it in inventory."""
    if not args_str:
        await character.send("Remove what (e.g., remove head, remove wield)?")
        return True
    
    # Target is the slot name or maybe item name? Let's try slot name first.
    target_slot = args_str.strip().upper().replace(" ","_") # Convert "wield main" to WIELD_MAIN

    # Check if it's a valid slot being used
    template_id = character.equipment.get(target_slot)
    if template_id is None:
        # Maybe they typed item name? Try finding by name in equipment
        found = character.find_item_in_equipment_by_name(args_str)
        if found:
            target_slot, template_id = found
        else:
            await character.send("You aren't wearing or wielding anything there or by that name.")
            return True
        
    # Get item details to check weight before moving to inventory
    item = character.get_item_instance(template_id)
    item_weight = getattr(item, 'weight', 1) if item else 1

    # Check weight capacity
    if character.get_current_weight(world) + item_weight > character.get_max_weight() * 2:
        await character.send("You don't have enough carrying capacity free to remove that.")
        return True

    # Remove the item
    removed_item_name = getattr(item, 'name', f"Item #{template_id}")
    del character.equipment[target_slot] # Remove from equipment slot
    character.inventory.append(template_id) # Add back to inventory

    await character.send(f"You remove {removed_item_name}.")
    await character.location.broadcast(f"\r\n{character.name} removes {removed_item_name}.\r\n", exclude={character})

    character.roundtime = 1.5 # Example RT for removing gear

    return True

async def cmd_examine(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Examines an item in inventory, equipment, or on the ground."""
    if not args_str:
        await character.send("Examine what?")
        return True

    target_name = args_str.strip().lower()
    item_location = None # Where was it found? 'inventory', 'equipment', 'ground'
    template_id = None

    # Search Order: Equipment -> Inventory -> Ground
    found_in_eq = character.find_item_in_equipment_by_name(world, target_name)
    if found_in_eq:
        item_location = "equipment"
        template_id = found_in_eq[1]
    else:
        found_in_inv = character.find_item_in_inventory_by_name(world, target_name)
        if found_in_inv:
            item_location = "inventory"
            template_id = found_in_inv
        elif character.location: # Check ground
            items_on_ground = list(character.location.items)
            for t_id in items_on_ground:
                template = get_item_template_from_world(world, t_id)
                if template and template['name'].lower() == target_name:
                    item_location = "ground"
                    template_id = t_id
                    break

    if template_id is None:
        await character.send("You don't see that here.")
        return True

    # Get item instance
    item = character.get_item_instance(template_id)
    if not item:
        await character.send("You look closer, but cannot make out the details.")
        return True

    # Format description
    output = f"\r\n--- {item.name} ---\r\n"
    output += f"{item.description}\r\n"
    output += f"Type: {item.item_type.capitalize()}, Value: {item.value} talons, Weight: {item.weight} lbs\r\n"
    # Show relevant stats
    if item.item_type == "WEAPON":
        output += f"Damage: {item.damage_base} (+1 to {item.damage_rng}), Speed: {item.speed}s, Type: {item.damage_type or 'N/A'}\r\n"
    elif item.item_type == "ARMOR" or item.item_type == "SHIELD":
        output += f"Armor: {item.armor}\r\n"
    # Add display for other types (consumables, etc.) later
    if item.flags:
        output += f"Flags: {', '.join(sorted(item.flags))}\r\n"

    await character.send(output.strip())
    return True