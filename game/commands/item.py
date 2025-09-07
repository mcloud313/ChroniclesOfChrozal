# game/commands/item.py
"""
Commands related to items, inventory, and equipment.
"""
import logging
from typing import TYPE_CHECKING
import json
import aiosqlite

from .. import combat as combat_logic
from .. import utils
from ..item import Item

if TYPE_CHECKING:
    from ..character import Character
    from ..world import World

log = logging.getLogger(__name__)


async def cmd_inventory(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Displays character inventory, equipment, weight, and coinage."""
    output = ["\r\n========================= Inventory ========================="]

    # --- Equipment ---
    output.append("You are wearing:")
    equipped_items = []
    for slot in character.equipment:
        template_id = character.equipment.get(slot)
        if template_id:
            template = utils.get_item_template_from_world(world, template_id)
            item_name = template['name'] if template else f"Unknown Item ({template_id})"
            slot_display = slot.replace('_', ' ').title()
            equipped_items.append(f" <{slot_display:<12}> {item_name}")
    
    output.extend(equipped_items if equipped_items else [" Nothing."])
    output.append("-")

    # --- Inventory (Loose items) ---
    output.append("You are carrying:")
    if not character.inventory:
        output.append(" Nothing.")
    else:
        item_counts = {}
        for template_id in character.inventory:
            item_counts[template_id] = item_counts.get(template_id, 0) + 1

        item_names = []
        for template_id, count in sorted(item_counts.items()):
            template = utils.get_item_template_from_world(world, template_id)
            item_name = template['name'] if template else f"Unknown Item #{template_id}"
            display_name = item_name + (f" (x{count})" if count > 1 else "")
            item_names.append(display_name)
        output.append(" " + ", ".join(item_names) + ".")
    output.append("-")

    # --- Coinage & Weight ---
    output.append(f" Coins: {utils.format_coinage(character.coinage)}")
    output.append(f" Weight: {character.get_current_weight(world)}/{character.get_max_weight()} stones")
    
    # BUG FIX: Corrected newline typo from "r\n" to "\r\n"
    output.append("=========================================================")
    await character.send("\r\n".join(output))
    return True


async def cmd_get(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Gets an item or coinage from the room."""
    if not args_str:
        await character.send("Get what?")
        return True
    
    if not character.location:
        await character.send("There is nothing to get here.")
        return True
    
    target_name = args_str.strip().lower()

    # Handle getting coins
    if target_name in ["coins", "coin", "money", "talons", "t"]:
        room_coinage = character.location.coinage
        if room_coinage <= 0:
            await character.send("There are no coins here.")
            return True

        if await character.location.add_coinage(-room_coinage, world):
            character.coinage += room_coinage
            await character.send(f"You pick up {utils.format_coinage(room_coinage)}.")
            await character.location.broadcast(f"\r\n{character.name} picks up some coins.\r\n", exclude={character})
            character.roundtime = 1.0
        else:
            await character.send("You try to pick up the coins, but fail.")
        return True

    # Handle getting an item
    item_to_get = None
    for template_id in character.location.items:
        template = utils.get_item_template_from_world(world, template_id)
        if template and target_name in template['name'].lower():
            item_to_get = template
            break

    if not item_to_get:
        await character.send(f"You don't see '{target_name}' here.")
        return True

    item_weight = 1
    try:
        stats = json.loads(item_to_get.get('stats', '{}'))
        item_weight = stats.get('weight', 1)
    except json.JSONDecodeError: pass

    # Weight Check
    max_w = character.get_max_weight()
    curr_w = character.get_current_weight(world)
    # The '2' is a hardcoded encumbrance limit (can carry up to 2x max weight before being unable to pick things up)
    if curr_w + item_weight > max_w * 2:
        log.debug("GET failed for %s: item_weight=%d, curr_w=%d, max_w*2=%d",
                  character.name, item_weight, curr_w, max_w * 2)
        await character.send("You can't carry that much more weight!")
        return True
    
    item_template_id = item_to_get['id']
    if await character.location.remove_item(item_template_id, world):
        character.inventory.append(item_template_id)
        item_name = item_to_get['name']
        await character.send(f"You get {item_name}.")
        await character.location.broadcast(f"\r\n{character.name} gets {item_name}.\r\n", exclude={character})
        character.roundtime = 1.5
    else:
        await character.send(f"You reach for the {item_to_get['name']}, but it's gone!")
    return True


async def cmd_drop(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Drops an item from inventory onto the ground."""
    if not args_str:
        await character.send("Drop what?")
        return True

    template_id_to_drop = character.find_item_in_inventory_by_name(world, args_str)
    if template_id_to_drop is None:
        await character.send("You aren't carrying that.")
        return True
    
    if await character.location.add_item(template_id_to_drop, world):
        character.inventory.remove(template_id_to_drop)
        template = utils.get_item_template_from_world(world, template_id_to_drop)
        item_name = template['name'] if template else f"Item #{template_id_to_drop}"
        await character.send(f"You drop {item_name}.")
        await character.location.broadcast(f"\r\n{character.name} drops {item_name}.\r\n", exclude={character})
        character.roundtime = 1.0
    else:
        await character.send(f"You try to drop the {args_str}, but fumble!")
    return True


async def cmd_wear(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Wears an item from inventory."""
    if not args_str:
        await character.send("Wear what?")
        return True
    
    template_id = character.find_item_in_inventory_by_name(world, args_str)
    if template_id is None:
        await character.send("You aren't carrying that.")
        return True
    
    item = character.get_item_instance(world, template_id)
    if not item or item.item_type not in ["ARMOR", "CLOTHING", "SHIELD"]:
        await character.send("You can't wear that.")
        return True
    
    target_slots = item.wear_location
    if not target_slots:
        await character.send("That item isn't meant to be worn on a specific location.")
        return True
    
    if isinstance(target_slots, str):
        target_slots = [target_slots]
    
    occupied_slots = [slot for slot in target_slots if character.equipment.get(slot) is not None]
    if occupied_slots:
        await character.send(f"You already have something worn on your {', '.join(occupied_slots)}.")
        return True
    
    character.inventory.remove(template_id)
    for slot in target_slots:
        character.equipment[slot] = template_id

    await character.send(f"You wear {item.name}.")
    await character.location.broadcast(f"\r\n{character.name} wears {item.name}.\r\n", exclude={character})
    character.roundtime = item.speed
    return True


async def cmd_wield(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Wields a weapon from inventory."""
    if not args_str:
        await character.send("Wield what?")
        return True
    
    template_id = character.find_item_in_inventory_by_name(world, args_str)
    if template_id is None:
        await character.send("You aren't carrying that.")
        return True
    
    item = character.get_item_instance(world, template_id)
    if not item or item.item_type != "WEAPON":
        await character.send("You can't wield that.")
        return True
    
    slot_to_use = "WIELD_MAIN"
    if currently_wielded_id := character.equipment.get(slot_to_use):
        character.inventory.append(currently_wielded_id)
    
    character.inventory.remove(template_id)
    character.equipment[slot_to_use] = template_id

    await character.send(f"You wield {item.name}.")
    await character.location.broadcast(f"\r\n{character.name} wields {item.name}.\r\n", exclude={character})
    character.roundtime = item.speed
    return True


async def cmd_remove(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Removes a worn/wielded item, placing it in inventory."""
    if not args_str:
        await character.send("Remove what?")
        return True
    
    target_slot, template_id = None, None
    found = character.find_item_in_equipment_by_name(world, args_str)
    if found:
        target_slot, template_id = found
    
    if not (target_slot and template_id):
        await character.send("You aren't wearing or wielding anything by that name.")
        return True
        
    item = character.get_item_instance(world, template_id)
    removed_item_name = getattr(item, 'name', f"Item #{template_id}")
    
    del character.equipment[target_slot]
    character.inventory.append(template_id)

    await character.send(f"You remove {removed_item_name}.")
    await character.location.broadcast(f"\r\n{character.name} removes {removed_item_name}.\r\n", exclude={character})
    character.roundtime = 1.5
    return True


async def cmd_examine(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Examines an item in inventory, equipment, or on the ground."""
    if not args_str:
        await character.send("Examine what?")
        return True

    item_location, template_id = character.find_item_anywhere_by_name(world, args_str) or (None, None)

    if not template_id:
        # Check ground as a last resort
        for t_id in character.location.items:
            template = world.get_item_template(t_id)
            if template and args_str.strip().lower() in template['name'].lower():
                template_id = t_id
                break

    if not template_id:
        await character.send("You don't see that here.")
        return True

    item = character.get_item_instance(world, template_id)
    if not item:
        await character.send("You look closer, but cannot make out the details.")
        return True

    output = [
        f"\r\n--- {item.name} ---",
        item.description,
        f"Type: {item.item_type.capitalize()}, Weight: {item.weight} stones"
    ]
    if item.item_type == "WEAPON":
        output.append(f"Damage: {item.damage_base}-{item.damage_base + item.damage_rng}, Speed: {item.speed}s, Type: {item.damage_type or 'N/A'}")
    elif item.item_type in ["ARMOR", "SHIELD"]:
        output.append(f"Armor: {item.armor}")

    if item.flags:
        output.append(f"Flags: {', '.join(sorted(item.flags))}")

    await character.send("\r\n".join(output))
    return True


async def cmd_drink(character: 'Character', world: 'World', db_conn: aiosqlite.Connection, args_str: str) -> bool:
    """Drinks a consumable item from inventory."""
    if not args_str:
        await character.send("Drink what?")
        return True
    
    template_id = character.find_item_in_inventory_by_name(world, args_str)
    if template_id is None:
        await character.send("You aren't carrying that.")
        return True
    
    template = utils.get_item_template_from_world(world, template_id)
    if not template or template.get('type') != "DRINK":
        await character.send("You can't drink that.")
        return True
    
    if await combat_logic.resolve_consumable_effect(character, template, world):
        character.inventory.remove(template_id)
        character.roundtime = 2.0
    return True


async def cmd_eat(character: 'Character', world: 'World', db_conn: aiosqlite.Connection, args_str: str) -> bool:
    """Eats a consumable item from inventory."""
    if not args_str:
        await character.send("Eat what?")
        return True

    template_id = character.find_item_in_inventory_by_name(world, args_str)
    if template_id is None:
        await character.send("You aren't carrying that.")
        return True

    template = utils.get_item_template_from_world(world, template_id)
    if not template or template.get('type') != "FOOD":
        await character.send("You can't eat that.")
        return True

    if await combat_logic.resolve_consumable_effect(character, template, world):
        character.inventory.remove(template_id)
        character.roundtime = 3.0
    return True