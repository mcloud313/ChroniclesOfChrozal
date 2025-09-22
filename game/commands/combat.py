# game/commands/combat.py
"""
Combat related commands like attack and shoot.
"""
import logging
from typing import TYPE_CHECKING

# Cleaned imports
from .. import resolver
from ..character import Character
from ..world import World
from ..definitions import item_defs

log = logging.getLogger(__name__)


async def cmd_attack(character: Character, world: World, args_str: str) -> bool:
    """Handles the 'attack <target>' command."""
    if character.stance != "Standing":
        await character.send("You must be standing to attack.")
        return True
    
    if not args_str:
        await character.send("Attack whom?")
        return True
        
    if not character.location:
        # This case should ideally never happen, but it's a good safeguard.
        return True
        
    target = character.location.get_mob_by_name(args_str)

    if not target:
        await character.send(f"You don't see '{args_str}' here to attack.")
        return True
    
    if "FLYING" in target.flags:
        await character.send(f"You can't reach the {target.name}, it's flying too high!")
        return True
    
    weapon = character._equipped_items.get("main_hand")
    if weapon and weapon.item_type == item_defs.RANGED_WEAPON:
        await character.send(f"You can't attack with {weapon.name}, you should try to <shoot> it instead.")
        return True
    
    # --- NEW: Check for two-handed weapon rules ---
    # The character might be holding something they picked up after wielding.
    if weapon and weapon.item_type == item_defs.TWO_HANDED_WEAPON:
        if character._inventory_items: # If there's anything in inventory, a hand is full.
            await character.send(f"You need two hands free to swing {weapon.name} effectively!")
            return True
        
    log.info("%s is initiating combat with %s.", character.name, target.name)

    # Set combat states for both character and mob
    character.target = target
    character.is_fighting = True

    if not target.is_fighting:
        target.target = character
        target.is_fighting = True

    await character.send(f"You attack {target.name}!")

    # Determine if the character is using a weapon or is unarmed
    weapon = character._equipped_items.get("main_hand")
    valid_weapon_types = {item_defs.WEAPON, item_defs.TWO_HANDED_WEAPON}
    if weapon and weapon.item_type not in valid_weapon_types:
        # If the wielded item is not a valid weapon, treat the attack as unarmed.
        weapon = None
        
    # Call the resolver with the correct, direct import
    await resolver.resolve_physical_attack(character, target, weapon, world)
    return True

async def cmd_shoot(character: Character, world: World, args: str) -> bool:
    """Initiates a ranged attack against a target."""
    # Added stance check for consistency
    if character.stance != "Standing":
        await character.send("You must be standing to shoot.")
        return True

    if not args:
        await character.send("Who do you want to shoot at?")
        return True

    if not character.location:
        return True

    target = character.location.get_mob_by_name(args)
    if not target:
        await character.send("You don't see them here.")
        return True
        
    # 1. Check for Ranged Weapon
    weapon = character._equipped_items.get("main_hand")
    if not weapon or weapon.item_type != "RANGED_WEAPON":
        await character.send("You aren't wielding a ranged weapon.")
        return True

    # 2. Find a suitable quiver
    required_ammo_type = weapon.stats.get("uses_ammo_type")
    if not required_ammo_type:
        await character.send(f"Your {weapon.name} doesn't seem to use any ammunition.")
        return True
    
    # --- NEW: Check for free hands before shooting ---
    # A character can't shoot if they have a shield equipped or are holding an item.
    if character._equipped_items.get("off_hand"):
        await character.send("You can't shoot while using a shield.")
        return True
    if character._inventory_items:
        await character.send("You need a free hand to load and fire your weapon.")
        return True

    quiver = None
    # Check equipped items first, then inventory
    search_locations = list(character._equipped_items.values()) + list(character._inventory_items.values())
    for item in search_locations:
        if item and item.item_type == "QUIVER" and item.stats.get("holds_ammo_type") == required_ammo_type:
            quiver = item
            break
            
    if not quiver:
        await character.send(f"You need a quiver that holds {required_ammo_type}s.")
        return True

    # 3. Find ammunition in the quiver
    ammo_stack = None
    for item in quiver.contents.values():
        if item.item_type == "AMMO" and item.instance_stats.get("ammo_type") == required_ammo_type:
            ammo_stack = item
            break

    if not ammo_stack or ammo_stack.instance_stats.get("quantity", 0) <= 0:
        await character.send(f"You don't have any {required_ammo_type}s in your {quiver.name}.")
        return True

    # 4. We have a weapon, quiver, and ammo. Resolve the attack.
    character.target = target
    character.is_fighting = True
    # Call the resolver with the correct, direct import
    await resolver.resolve_ranged_attack(character, target, weapon, ammo_stack, world)

    # 5. Consume ammunition
    current_quantity = ammo_stack.instance_stats.get("quantity", 1)
    ammo_stack.instance_stats["quantity"] = current_quantity - 1

    if ammo_stack.instance_stats["quantity"] <= 0:
        await character.send(f"You have used your last {required_ammo_type}.")
        # Remove from quiver and world
        del quiver.contents[ammo_stack.id]
        if ammo_stack.id in world._all_item_instances:
            del world._all_item_instances[ammo_stack.id]
        # Persist deletion in DB
        await world.db_manager.delete_item_instance(ammo_stack.id)
    else:
        # Persist quantity change
        await world.db_manager.update_item_instance_stats(ammo_stack.id, ammo_stack.instance_stats)

    return True