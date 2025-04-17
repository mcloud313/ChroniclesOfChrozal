#game/commands/combat.py
"""
Combat related commands like attack
"""
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..character import Character
    from ..world import World
    import aiosqlite

# Import combat logic handler
from .. import combat as combat_logic
#Import Item class if needed for weapon check
from ..item import Item
from ..mob import Mob
from ..character import Character


log = logging.getLogger(__name__)

async def cmd_attack(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Handles the 'attack <target>' command."""
    if character.stance != "Standing":
        await character.send("You must be standing to attack.")
        return True
    if not args_str:
        await character.send("Attack whom?")
        return True
    
    if not character.location:
        await character.send("You cannot attack from the void.")
        return True
    
    if character.roundtime > 0:
        # this checkis redundant if handler checks first, but good safety
        await character.send(f"You are still recovering for {character.roundtime:.1f} seconds.")
        return True
    
    if character.status == "DYING" or character.status == "DEAD":
        await character.send("You cannot attack in your current state.")
        return True
    

    target_name = args_str.strip().lower()

    # Find target (Mobs first, then other Players)
    target = None
    # Check mobs in room
    for mob in character.location.mobs:
        # Basic name check - allow targeting "rat" for "a giant rat" etc.
        # Need more robust target parsing later (e.g., 2.rat)
        mob_name_parts = mob.name.lower().split()
        if target_name in mob_name_parts and mob.is_alive():
            target = mob
            break

    # Check players in room if no mob found
    if target is None:
        target_char = character.location.get_character_by_name(target_name) # Uses first name check
        if target_char and target_char != character and target_char.is_alive():
            # PVP Check? For now, allow attacking players. Add flags later.
            log.warning("PVP initiated: %s attacking %s", character.name, target_char.name)
            target = target_char
        elif target_char == character:
            await character.send("You contemplate attacking yourself, but decide against it.")
            return True
        
    if target is None:
        await character.send(f"You don't see {target_name}' here to attack.")
        return True
    
    if not target.is_alive():
        await character.send(f"{target.name.capitalize()} is already defeated.")
        return True
    
    # Set target and flag
    character.target = target
    character.is_fighting = True
    # If target is a Mob that wasn't fighting, make it retaliate
    if isinstance(target, Mob) and not target.is_fighting:
        target.target = character
        target.is_fighting = True
        log.info("%s is now fighting %s after being attacked.", target.name, character.name)

    await character.send(f"You attack {target.name}!")

    # Get weapon
    weapon = None
    weapon_template_id = character.equipment.get("WIELD_MAIN") # Assumes slot name
    if weapon_template_id:
        # Pass world to get instance
        weapon = character.get_item_instance(world, weapon_template_id)
        if weapon and weapon.item_type != "WEAPON":
            weapon = None # Can't attack with non-weapon
    
    # Resolve the attack
    await combat_logic.resolve_physical_attack(character, target, weapon, world)

    return True # Keep connction active
